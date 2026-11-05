"""Batch raw-to-lakehouse ETL for the SentinelPay synthetic portfolio.

The job processes exactly one completed S3 batch (ingest_date + batch_id).
Bronze remains the raw JSONL data exposed by the existing Glue Catalog tables.
Invalid records go to S3 quarantine; valid, deduplicated rows are MERGEd into
the Silver Iceberg tables, then Gold training/metrics and batch audit are
refreshed. This script is intended to run inside AWS Glue 5.x, not locally.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark import SparkContext
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)


EVENTS: dict[str, dict[str, Any]] = {
    "payments": {
    "bronze": "payments_bronze",
        "silver": "payments_iceberg",
        "key": "event_id",
        "order": "received_at",
        "fields": [
            ("data_classification", StringType()), ("schema_version", IntegerType()),
            ("event_id", StringType()), ("payment_id", StringType()),
            ("idempotency_key", StringType()), ("event_time", StringType()),
            ("received_at", StringType()), ("payment_token", StringType()),
            ("account_token", StringType()), ("merchant_id", StringType()),
            ("device_token", StringType()), ("amount", DoubleType()),
            ("currency", StringType()), ("channel", StringType()),
            ("country_code", StringType()), ("device_first_seen_days", IntegerType()),
            ("source_region", StringType()), ("trace_id", StringType()),
            ("ingest_date", StringType()), ("batch_id", StringType()),
        ],
    },
    "feature_updates": {
    "bronze": "feature_updates_bronze",
        "silver": "feature_updates_iceberg",
        "key": "feature_event_id",
        "order": "computed_at",
        "fields": [
            ("data_classification", StringType()), ("schema_version", IntegerType()),
            ("feature_event_id", StringType()), ("entity_type", StringType()),
            ("entity_token", StringType()), ("feature_version", IntegerType()),
            ("window_start", StringType()), ("window_end", StringType()),
            ("window_seconds", IntegerType()), ("transaction_count", IntegerType()),
            ("amount_sum", DoubleType()), ("currency", StringType()),
            ("distinct_merchant_count", IntegerType()), ("new_device_count", IntegerType()),
            ("computed_at", StringType()), ("source_region", StringType()),
            ("ingest_date", StringType()), ("batch_id", StringType()),
        ],
    },
    "fraud_decisions": {
    "bronze": "fraud_decisions_bronze",
        "silver": "fraud_decisions_iceberg",
        "key": "decision_id",
        "order": "decision_time",
        "fields": [
            ("data_classification", StringType()), ("schema_version", IntegerType()),
            ("decision_id", StringType()), ("event_id", StringType()),
            ("payment_id", StringType()), ("decision", StringType()),
            ("risk_score", DoubleType()), ("reason_codes", ArrayType(StringType())),
            ("model_id", StringType()), ("model_version", StringType()),
            ("policy_version", StringType()), ("feature_age_ms", LongType()),
            ("fallback_used", BooleanType()), ("decision_time", StringType()),
            ("source_region", StringType()), ("trace_id", StringType()),
            ("ingest_date", StringType()), ("batch_id", StringType()),
        ],
    },
    "chargeback_outcomes": {
    "bronze": "chargeback_outcomes_bronze",
        "silver": "chargeback_outcomes_iceberg",
        "key": "outcome_event_id",
        "order": "label_observed_at",
        "fields": [
            ("data_classification", StringType()), ("schema_version", IntegerType()),
            ("outcome_event_id", StringType()), ("payment_id", StringType()),
            ("outcome", StringType()), ("outcome_source", StringType()),
            ("payment_event_time", StringType()), ("label_observed_at", StringType()),
            ("source_region", StringType()), ("trace_id", StringType()),
            ("ingest_date", StringType()), ("batch_id", StringType()),
        ],
    },
}

ID_PATTERNS = {
    "event_id": r"^evt_[A-Za-z0-9_-]+$",
    "payment_id": r"^pay_[A-Za-z0-9_-]+$",
    "idempotency_key": r"^idem_[A-Za-z0-9_-]+$",
    "payment_token": r"^ptok_[A-Za-z0-9_-]+$",
    "account_token": r"^atok_[A-Za-z0-9_-]+$",
    "merchant_id": r"^mer_[A-Za-z0-9_-]+$",
    "device_token": r"^dtok_[A-Za-z0-9_-]+$",
    "source_region": r"^[a-z]{2}(-gov)?-[a-z]+-\d$",
    "trace_id": r"^[a-f0-9]{32}$",
}

NAMESPACE_PREFIX = {
    "payment_id": ("pay_", 5),
    "idempotency_key": ("idem_", 6),
    "payment_token": ("ptok_", 6),
    "account_token": ("atok_", 6),
    "merchant_id": ("mer_", 5),
    "device_token": ("dtok_", 6),
}


def options() -> dict[str, str]:
    return getResolvedOptions(sys.argv, [
        "JOB_NAME", "JOB_RUN_ID", "bucket", "database", "ingest_date", "batch_id",
        "namespace_batches", "quarantine_prefix", "export_prefix", "train_cutoff",
        "validation_cutoff", "max_invalid_fraction",
    ])


def valid_token(value: str, regex: str) -> F.Column:
    return F.col(value).isNotNull() & F.col(value).rlike(regex)


def validation_rules(event_type: str) -> list[tuple[str, F.Column]]:
    rules: list[tuple[str, F.Column]] = [
        ("MALFORMED_JSON", F.col("_corrupt_record").isNotNull()),
        ("NOT_SYNTHETIC", F.col("data_classification").isNull() | (F.col("data_classification") != F.lit("SYNTHETIC"))),
        ("UNSUPPORTED_SCHEMA_VERSION", F.col("schema_version").isNull() | (F.col("schema_version") != F.lit(1))),
        ("INVALID_SOURCE_REGION", ~valid_token("source_region", ID_PATTERNS["source_region"])),
        ("INVALID_TRACE_ID", ~valid_token("trace_id", ID_PATTERNS["trace_id"])),
    ]
    for field_name, _ in EVENTS[event_type]["fields"]:
        if field_name not in ("ingest_date", "batch_id", "data_classification", "schema_version"):
            rules.append((f"MISSING_{field_name.upper()}", F.col(field_name).isNull()))
    if event_type == "payments":
        rules += [
            ("INVALID_EVENT_ID", ~valid_token("event_id", ID_PATTERNS["event_id"])),
            ("INVALID_PAYMENT_ID", ~valid_token("payment_id", ID_PATTERNS["payment_id"])),
            ("INVALID_IDEMPOTENCY_KEY", ~valid_token("idempotency_key", ID_PATTERNS["idempotency_key"])),
            ("INVALID_PAYMENT_TOKEN", ~valid_token("payment_token", ID_PATTERNS["payment_token"])),
            ("INVALID_ACCOUNT_TOKEN", ~valid_token("account_token", ID_PATTERNS["account_token"])),
            ("INVALID_MERCHANT_ID", ~valid_token("merchant_id", ID_PATTERNS["merchant_id"])),
            ("INVALID_DEVICE_TOKEN", ~valid_token("device_token", ID_PATTERNS["device_token"])),
            ("INVALID_AMOUNT", F.col("amount").isNull() | F.isnan("amount") | (F.col("amount") < 0) | (F.col("amount") > 1000000)),
            ("INVALID_CURRENCY", F.col("currency").isNull() | ~F.col("currency").rlike(r"^[A-Z]{3}$")),
            ("INVALID_CHANNEL", F.col("channel") != F.lit("CARD_NOT_PRESENT")),
            ("INVALID_COUNTRY", ~F.col("country_code").rlike(r"^[A-Z]{2}$")),
            ("INVALID_DEVICE_AGE", F.col("device_first_seen_days").isNull() | (F.col("device_first_seen_days") < 0) | (F.col("device_first_seen_days") > 3650)),
            ("INVALID_EVENT_TIME", F.expr("try_to_timestamp(event_time) IS NULL")),
            ("INVALID_RECEIVED_AT", F.expr("try_to_timestamp(received_at) IS NULL")),
        ]
    elif event_type == "feature_updates":
        rules += [
            ("INVALID_FEATURE_ID", ~F.col("feature_event_id").rlike(r"^feat_[A-Za-z0-9_-]+$")),
            ("INVALID_ENTITY_TYPE", F.col("entity_type").isNull() | ~F.col("entity_type").isin("ACCOUNT", "PAYMENT_TOKEN", "DEVICE", "MERCHANT")),
            ("MISSING_ENTITY_TOKEN", F.col("entity_token").isNull() | (F.length("entity_token") == 0)),
            ("INVALID_FEATURE_VERSION", F.col("feature_version").isNull() | (F.col("feature_version") < 1)),
            ("INVALID_WINDOW", F.col("window_seconds").isNull() | (F.col("window_seconds") < 1) | (F.col("window_seconds") > 604800)),
            ("INVALID_FEATURE_COUNTS", F.col("transaction_count").isNull() | (F.col("transaction_count") < 0) | F.col("distinct_merchant_count").isNull() | (F.col("distinct_merchant_count") < 0) | F.col("new_device_count").isNull() | (F.col("new_device_count") < 0)),
            ("INVALID_FEATURE_AMOUNT", F.col("amount_sum").isNull() | F.isnan("amount_sum") | (F.col("amount_sum") < 0)),
            ("INVALID_CURRENCY", F.col("currency").isNull() | ~F.col("currency").rlike(r"^[A-Z]{3}$")),
            ("INVALID_FEATURE_TIME", F.expr("try_to_timestamp(window_start) IS NULL OR try_to_timestamp(window_end) IS NULL OR try_to_timestamp(computed_at) IS NULL")),
        ]
    elif event_type == "fraud_decisions":
        rules += [
            ("INVALID_DECISION_ID", ~F.col("decision_id").rlike(r"^dec_[A-Za-z0-9_-]+$")),
            ("INVALID_EVENT_ID", ~F.col("event_id").rlike(ID_PATTERNS["event_id"])),
            ("INVALID_PAYMENT_ID", ~F.col("payment_id").rlike(ID_PATTERNS["payment_id"])),
            ("INVALID_DECISION", F.col("decision").isNull() | ~F.col("decision").isin("APPROVE", "STEP_UP", "REVIEW", "DECLINE")),
            ("INVALID_RISK_SCORE", F.col("risk_score").isNull() | F.isnan("risk_score") | (F.col("risk_score") < 0) | (F.col("risk_score") > 1)),
            ("INVALID_REASON_CODES", F.col("reason_codes").isNull() | (F.size("reason_codes") == 0)),
            ("INVALID_DECISION_TIME", F.expr("try_to_timestamp(decision_time) IS NULL")),
            ("INVALID_FEATURE_AGE", F.col("feature_age_ms").isNull() | (F.col("feature_age_ms") < 0)),
        ]
    else:
        rules += [
            ("INVALID_OUTCOME_ID", ~F.col("outcome_event_id").rlike(r"^out_[A-Za-z0-9_-]+$")),
            ("INVALID_PAYMENT_ID", ~F.col("payment_id").rlike(ID_PATTERNS["payment_id"])),
            ("INVALID_OUTCOME", F.col("outcome").isNull() | ~F.col("outcome").isin("CONFIRMED_FRAUD", "NO_FRAUD")),
            ("INVALID_OUTCOME_SOURCE", F.col("outcome_source").isNull() | (F.col("outcome_source") != F.lit("SYNTHETIC_LABEL_GENERATOR"))),
            ("INVALID_OUTCOME_TIME", F.expr("try_to_timestamp(payment_event_time) IS NULL OR try_to_timestamp(label_observed_at) IS NULL")),
            ("LABEL_BEFORE_PAYMENT", F.expr("try_to_timestamp(label_observed_at) < try_to_timestamp(payment_event_time)")),
        ]
    return rules


def raw_schema(event_type: str) -> StructType:
    fields = [StructField(name, data_type, True) for name, data_type in EVENTS[event_type]["fields"]]
    return StructType(fields + [StructField("_corrupt_record", StringType(), True)])


def list_source_paths(s3: Any, bucket: str, event_type: str, ingest_date: str, batch_id: str) -> list[str]:
    prefix = f"raw/{event_type}/ingest_date={ingest_date}/batch_id={batch_id}/"
    paginator = s3.get_paginator("list_objects_v2")
    keys = [
        item["Key"]
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for item in page.get("Contents", [])
        if item["Key"].endswith((".jsonl.gz", ".jsonl"))
    ]
    return [f"s3://{bucket}/{key}" for key in sorted(keys)]


def parse_and_validate(
    spark: Any,
    paths: list[str],
    event_type: str,
    ingest_date: str,
    batch_id: str,
) -> tuple[DataFrame, DataFrame, int, int, int]:
    raw = (
        spark.read.text(paths)
        .withColumnRenamed("value", "raw_record")
        .withColumn("source_s3_uri", F.input_file_name())
    )
    parsed = raw.withColumn(
        "_event",
        F.from_json(
            F.col("raw_record"),
            raw_schema(event_type),
            {"mode": "PERMISSIVE", "columnNameOfCorruptRecord": "_corrupt_record"},
        ),
    ).select("raw_record", "source_s3_uri", "_event.*")

    error_exprs = [
        F.when(condition, F.lit(reason)).otherwise(F.lit(None).cast(StringType()))
        for reason, condition in validation_rules(event_type)
    ]
    checked = (
        parsed
        .withColumn("_validation_errors", F.array(*error_exprs))
        .withColumn("validation_errors", F.expr("filter(_validation_errors, x -> x IS NOT NULL)"))
        .drop("_validation_errors")
        .withColumn("event_type", F.lit(event_type))
        .withColumn("ingest_date", F.lit(ingest_date))
        .withColumn("batch_id", F.lit(batch_id))
    )
    checked.cache()
    total_count = checked.count()
    invalid = checked.where(F.size("validation_errors") > 0)
    valid = checked.where(F.size("validation_errors") == 0)
    invalid_count = invalid.count()
    valid_count = total_count - invalid_count
    return valid, invalid, total_count, valid_count, invalid_count


def quarantine(invalid: DataFrame, bucket: str, prefix: str, run_id: str) -> None:
    if invalid.limit(1).count() == 0:
        return
    destination = f"s3://{bucket}/{prefix.strip('/')}/run_id={run_id}/"
    (
        invalid.select(
            "event_type", "ingest_date", "batch_id", "source_s3_uri",
            "raw_record", "validation_errors",
        )
        .write.mode("append")
        .json(destination)
    )


def namespace_synthetic_ids(df: DataFrame, event_type: str, namespace_batches: set[str]) -> DataFrame:
    if not namespace_batches:
        return df
    needs_namespace = F.col("batch_id").isin(sorted(namespace_batches))
    if event_type == "payments":
        for name, (prefix, start) in NAMESPACE_PREFIX.items():
            df = df.withColumn(
                name,
                F.when(needs_namespace, F.concat(F.lit(prefix), F.col("batch_id"), F.lit("_"), F.substring(F.col(name), start, 1024)))
                .otherwise(F.col(name)),
            )
    elif event_type in ("fraud_decisions", "chargeback_outcomes"):
        name = "payment_id"
        prefix, start = NAMESPACE_PREFIX[name]
        df = df.withColumn(
            name,
            F.when(needs_namespace, F.concat(F.lit(prefix), F.col("batch_id"), F.lit("_"), F.substring(F.col(name), start, 1024)))
            .otherwise(F.col(name)),
        )
    elif event_type == "feature_updates":
        name = "entity_token"
        prefix, start = NAMESPACE_PREFIX["account_token"]
        df = df.withColumn(
            name,
            F.when(needs_namespace & (F.col("entity_type") == "ACCOUNT"), F.concat(F.lit(prefix), F.col("batch_id"), F.lit("_"), F.substring(F.col(name), start, 1024)))
            .otherwise(F.col(name)),
        )
    return df


def merge_into_iceberg(spark: Any, df: DataFrame, database: str, event_type: str) -> int:
    spec = EVENTS[event_type]
    key = spec["key"]
    columns = [name for name, _ in spec["fields"]]
    ready = df.select(*columns)
    dedupe_window = Window.partitionBy(key).orderBy(
        F.col(spec["order"]).asc_nulls_last(), F.col("source_s3_uri").asc_nulls_last()
    ) if "source_s3_uri" in df.columns else Window.partitionBy(key).orderBy(F.col(spec["order"]).asc_nulls_last())
    if "source_s3_uri" not in ready.columns and "source_s3_uri" in df.columns:
        deduped = df.withColumn("_dedupe_rank", F.row_number().over(dedupe_window)).where(F.col("_dedupe_rank") == 1).drop("_dedupe_rank").select(*columns)
    else:
        deduped = ready.dropDuplicates([key])
    source_count = deduped.count()
    if source_count == 0:
        return 0
    view = f"source_{event_type}"
    deduped.createOrReplaceTempView(view)
    target = f"glue_catalog.{database}.{spec['silver']}"
    update_list = ",\n            ".join(f"t.`{c}` = s.`{c}`" for c in columns if c != key)
    insert_columns = ", ".join(f"`{c}`" for c in columns)
    insert_values = ", ".join(f"s.`{c}`" for c in columns)
    spark.sql(f"""
        MERGE INTO {target} AS t
        USING {view} AS s
        ON t.`{key}` = s.`{key}`
        WHEN MATCHED THEN UPDATE SET {update_list}
        WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
    """)
    return source_count


def audit_status(valid_count: int, invalid_count: int, duplicate_count: int, max_invalid_fraction: float) -> str:
    if valid_count == 0:
        return "FAIL"
    if invalid_count / max(1, valid_count + invalid_count) > max_invalid_fraction:
        return "FAIL"
    if invalid_count and duplicate_count:
        return "PASS_WITH_QUARANTINE_AND_DEDUP"
    if invalid_count:
        return "PASS_WITH_QUARANTINE"
    if duplicate_count:
        return "PASS_WITH_DEDUP"
    return "PASS"


def merge_audit(spark: Any, database: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    schema = StructType([
        StructField("ingest_date", StringType(), False),
        StructField("batch_id", StringType(), False),
        StructField("event_type", StringType(), False),
        StructField("bronze_record_count", LongType(), False),
        StructField("unique_business_ids", LongType(), False),
        StructField("duplicate_delivery_count", LongType(), False),
        StructField("reconciliation_status", StringType(), False),
        StructField("evaluated_at", StringType(), False),
    ])
    spark.createDataFrame(rows, schema).createOrReplaceTempView("batch_audit_updates")
    spark.sql(f"""
        MERGE INTO glue_catalog.{database}.pipeline_audit AS t
        USING batch_audit_updates AS s
          ON t.ingest_date = s.ingest_date
         AND t.batch_id = s.batch_id
         AND t.event_type = s.event_type
        WHEN MATCHED THEN UPDATE SET
            t.bronze_record_count = s.bronze_record_count,
            t.unique_business_ids = s.unique_business_ids,
            t.duplicate_delivery_count = s.duplicate_delivery_count,
            t.reconciliation_status = s.reconciliation_status,
            t.evaluated_at = s.evaluated_at
        WHEN NOT MATCHED THEN INSERT (
            ingest_date, batch_id, event_type, bronze_record_count,
            unique_business_ids, duplicate_delivery_count,
            reconciliation_status, evaluated_at
        ) VALUES (
            s.ingest_date, s.batch_id, s.event_type, s.bronze_record_count,
            s.unique_business_ids, s.duplicate_delivery_count,
            s.reconciliation_status, s.evaluated_at
        )
    """)


def refresh_gold(
    spark: Any,
    database: str,
    bucket: str,
    export_prefix: str,
    export_id: str,
    train_cutoff: str,
    validation_cutoff: str,
) -> dict[str, Any]:
    spark.sql(f"""
        CREATE OR REPLACE TEMP VIEW gold_training_source AS
        SELECT p.data_classification,
               '{export_id}' AS dataset_version,
               p.payment_id,
               p.event_id,
               to_date(substring(p.event_time, 1, 10)) AS event_date,
               p.event_time,
               p.received_at,
               p.amount,
               p.currency,
               p.channel,
               p.country_code,
               p.device_first_seen_days,
               f.transaction_count AS transaction_count_1h,
               f.amount_sum AS amount_sum_1h,
               f.distinct_merchant_count AS distinct_merchant_count_1h,
               f.new_device_count AS new_device_count_1h,
               f.computed_at AS feature_computed_at,
               o.outcome AS label,
               CASE WHEN o.outcome = 'CONFIRMED_FRAUD' THEN 1 ELSE 0 END AS label_fraud,
               o.label_observed_at,
               datediff(to_date(o.label_observed_at), to_date(p.event_time)) AS label_delay_days,
               CASE
                   WHEN to_date(p.event_time) < DATE '{train_cutoff}' THEN 'TRAIN'
                   WHEN to_date(p.event_time) < DATE '{validation_cutoff}' THEN 'VALIDATION'
                   ELSE 'TEST'
               END AS dataset_split
        FROM glue_catalog.{database}.payments_iceberg p
        JOIN glue_catalog.{database}.chargeback_outcomes_iceberg o
          ON o.payment_id = p.payment_id
         AND try_to_timestamp(o.label_observed_at) >= try_to_timestamp(p.event_time) + INTERVAL 30 DAYS
        JOIN glue_catalog.{database}.fraud_decisions_iceberg d
          ON d.event_id = p.event_id
        JOIN glue_catalog.{database}.feature_updates_iceberg f
          ON f.feature_event_id = concat('feat_', substring(p.event_id, 5, 1024))
         AND f.entity_token = p.account_token
         AND try_to_timestamp(f.window_end) <= try_to_timestamp(p.event_time)
         AND try_to_timestamp(f.computed_at) <= try_to_timestamp(d.decision_time)
        WHERE p.data_classification = 'SYNTHETIC'
    """)

    gold_target = f"glue_catalog.{database}.training_examples_gold"
    gold_columns = [
        "data_classification", "dataset_version", "payment_id", "event_id", "event_date",
        "event_time", "received_at", "amount", "currency", "channel", "country_code",
        "device_first_seen_days", "transaction_count_1h", "amount_sum_1h",
        "distinct_merchant_count_1h", "new_device_count_1h", "feature_computed_at",
        "label", "label_fraud", "label_observed_at", "label_delay_days", "dataset_split",
    ]
    merge_cols = ",\n            ".join(f"t.`{c}` = s.`{c}`" for c in gold_columns if c != "event_id")
    ins_cols = ", ".join(f"`{c}`" for c in gold_columns)
    ins_vals = ", ".join(f"s.`{c}`" for c in gold_columns)
    spark.sql(f"""
        MERGE INTO {gold_target} AS t
        USING gold_training_source AS s
          ON t.event_id = s.event_id
        WHEN MATCHED THEN UPDATE SET {merge_cols}
        WHEN NOT MATCHED THEN INSERT ({ins_cols}) VALUES ({ins_vals})
    """)

    spark.sql(f"""
        CREATE OR REPLACE TEMP VIEW gold_metric_source AS
        SELECT event_date, dataset_split, currency,
               count(*) AS payment_count,
               sum(label_fraud) AS confirmed_fraud_count,
               count(*) - sum(label_fraud) AS no_fraud_count,
               CAST(sum(label_fraud) AS DOUBLE) / count(*) AS fraud_rate,
               sum(amount) AS total_amount,
               avg(amount) AS average_amount
        FROM {gold_target}
        GROUP BY event_date, dataset_split, currency
    """)
    metrics_target = f"glue_catalog.{database}.fraud_daily_metrics_gold"
    metric_cols = [
        "event_date", "dataset_split", "currency", "payment_count",
        "confirmed_fraud_count", "no_fraud_count", "fraud_rate",
        "total_amount", "average_amount",
    ]
    metric_updates = ",\n            ".join(f"t.`{c}` = s.`{c}`" for c in metric_cols[3:])
    metric_ins = ", ".join(f"`{c}`" for c in metric_cols)
    metric_vals = ", ".join(f"s.`{c}`" for c in metric_cols)
    spark.sql(f"""
        MERGE INTO {metrics_target} AS t
        USING gold_metric_source AS s
          ON t.event_date = s.event_date
         AND t.dataset_split = s.dataset_split
         AND t.currency = s.currency
        WHEN MATCHED THEN UPDATE SET {metric_updates}
        WHEN NOT MATCHED THEN INSERT ({metric_ins}) VALUES ({metric_vals})
    """)

    gold_df = spark.table(gold_target)
    total_gold = gold_df.count()
    split_rows = {
        row["dataset_split"]: row["count"]
        for row in gold_df.groupBy("dataset_split").count().collect()
    }
    fraud_rows = gold_df.where(F.col("label_fraud") == 1).count()
    export_uri = f"s3://{bucket}/{export_prefix.strip('/')}/export_id={export_id}/"
    if total_gold:
        (gold_df.write.mode("overwrite").partitionBy("dataset_split").parquet(export_uri))
    return {
        "gold_training_rows": total_gold,
        "gold_confirmed_fraud_rows": fraud_rows,
        "dataset_split_rows": split_rows,
        "training_export_uri": export_uri if total_gold else None,
    }


def put_manifest(s3: Any, bucket: str, ingest_date: str, batch_id: str, run_id: str, data: dict[str, Any]) -> str:
    key = f"ops/glue_batch_runs/ingest_date={ingest_date}/batch_id={batch_id}/run_id={run_id}/manifest.json"
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )
    return f"s3://{bucket}/{key}"


def main() -> None:
    args = options()
    bucket = args["bucket"]
    database = args["database"]
    ingest_date = args["ingest_date"]
    batch_id = args["batch_id"]
    run_id = args["JOB_RUN_ID"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ingest_date):
        raise ValueError("ingest_date must be YYYY-MM-DD")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", batch_id):
        raise ValueError("batch_id may contain only letters, numbers, hyphens, and underscores")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", database):
        raise ValueError("database contains unsupported characters")
    for cutoff_name in ("train_cutoff", "validation_cutoff"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[cutoff_name]):
            raise ValueError(f"{cutoff_name} must be YYYY-MM-DD")

    namespace_batches = {x.strip() for x in args["namespace_batches"].split(",") if x.strip()}
    max_invalid_fraction = float(args["max_invalid_fraction"])
    if not 0 <= max_invalid_fraction <= 1:
        raise ValueError("max_invalid_fraction must be between 0 and 1")

    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    s3 = boto3.client("s3")
    audit_rows: list[dict[str, Any]] = []
    event_metrics: dict[str, dict[str, Any]] = {}
    evaluated_at = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "pipeline": "sentinelpay_glue_batch_v1",
        "run_id": run_id,
        "ingest_date": ingest_date,
        "batch_id": batch_id,
        "database": database,
        "data_classification": "SYNTHETIC",
        "started_at": evaluated_at,
        "event_families": {},
        "status": "RUNNING",
    }
    audit_manifest_uri = None
    processed_event_families = 0

    try:
        for event_type, spec in EVENTS.items():
            paths = list_source_paths(s3, bucket, event_type, ingest_date, batch_id)
            if not paths:
                event_metrics[event_type] = {
                    "source_objects": [],
                    "source_record_count": 0,
                    "valid_record_count": 0,
                    "unique_valid_ids": 0,
                    "quarantined_record_count": 0,
                    "duplicate_delivery_count": 0,
                    "silver_merge_source_count": 0,
                    "reconciliation_status": "NO_DATA",
                }
                audit_rows.append({
                    "ingest_date": ingest_date,
                    "batch_id": batch_id,
                    "event_type": event_type,
                    "bronze_record_count": 0,
                    "unique_business_ids": 0,
                    "duplicate_delivery_count": 0,
                    "reconciliation_status": "NO_DATA",
                    "evaluated_at": evaluated_at,
                })
                continue
            processed_event_families += 1
            valid, invalid, source_count, valid_count, invalid_count = parse_and_validate(
                spark, paths, event_type, ingest_date, batch_id
            )
            quarantine(invalid, bucket, args["quarantine_prefix"], run_id)

            key = spec["key"]
            unique_count = valid.select(key).distinct().count()
            duplicate_count = valid_count - unique_count
            canonical = namespace_synthetic_ids(valid, event_type, namespace_batches)
            merge_count = merge_into_iceberg(spark, canonical, database, event_type)
            status = audit_status(valid_count, invalid_count, duplicate_count, max_invalid_fraction)
            event_metrics[event_type] = {
                "source_objects": paths,
                "source_record_count": source_count,
                "valid_record_count": valid_count,
                "unique_valid_ids": unique_count,
                "quarantined_record_count": invalid_count,
                "duplicate_delivery_count": duplicate_count,
                "silver_merge_source_count": merge_count,
                "reconciliation_status": status,
            }
            audit_rows.append({
                "ingest_date": ingest_date,
                "batch_id": batch_id,
                "event_type": event_type,
                "bronze_record_count": source_count,
                "unique_business_ids": unique_count,
                "duplicate_delivery_count": duplicate_count,
                "reconciliation_status": status,
                "evaluated_at": evaluated_at,
            })
            valid.unpersist(blocking=False)
            invalid.unpersist(blocking=False)

        merge_audit(spark, database, audit_rows)
        if processed_event_families == 0:
            raise FileNotFoundError(
                f"No JSONL records found for batch {batch_id} on {ingest_date}"
            )
        if any(row["reconciliation_status"] == "FAIL" for row in audit_rows):
            raise ValueError("One or more event families failed the validation threshold")

        gold_metrics = refresh_gold(
            spark=spark,
            database=database,
            bucket=bucket,
            export_prefix=args["export_prefix"],
            export_id=run_id,
            train_cutoff=args["train_cutoff"],
            validation_cutoff=args["validation_cutoff"],
        )
        manifest.update({
            "status": "SUCCEEDED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "event_families": event_metrics,
            "gold": gold_metrics,
        })
        audit_manifest_uri = put_manifest(s3, bucket, ingest_date, batch_id, run_id, manifest)
        print(json.dumps({"audit_manifest": audit_manifest_uri, **manifest}, indent=2, default=str))
        job.commit()
    except Exception as exc:
        failed_at = datetime.now(timezone.utc).isoformat()
        manifest.update({
            "status": "FAILED",
            "completed_at": failed_at,
            "error": f"{type(exc).__name__}: {exc}",
            "event_families": event_metrics,
        })
        for row in audit_rows:
            row["reconciliation_status"] = "FAIL"
            row["evaluated_at"] = failed_at
        try:
            merge_audit(spark, database, audit_rows)
        except Exception as audit_exc:  # best-effort secondary audit on infrastructure failures
            manifest["audit_write_error"] = f"{type(audit_exc).__name__}: {audit_exc}"
        try:
            audit_manifest_uri = put_manifest(s3, bucket, ingest_date, batch_id, run_id, manifest)
            print(f"Failure manifest: {audit_manifest_uri}")
        except Exception as manifest_exc:
            print(f"Could not persist failure manifest: {type(manifest_exc).__name__}: {manifest_exc}")
        raise


if __name__ == "__main__":
    main()
