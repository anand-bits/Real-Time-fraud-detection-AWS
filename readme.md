# SentinelPay — production-style real-time fraud detection portfolio

> **Purpose:** Personal learning project and recruiter showcase. It demonstrates production engineering practices; it is not a company payment system, a PCI DSS implementation, or a production approval.

SentinelPay scores synthetic, tokenized card-not-present payment requests and evaluates behavior asynchronously. Use generated data only. Never put PAN, CVV, track data, credentials, or real customer records in source control, logs, fixtures, or the lake.

## Architecture

![SentinelPay advanced target architecture](architecture/financial-fraud-architecture.svg)

- [Editable target architecture](architecture/financial-fraud-architecture.mmd)
- [Current implemented data workflow](architecture/current-implemented-data-workflow.mmd)
- [Step 1 scope diagram](architecture/step-1-business-scope.svg)
- [Step 1 charter](docs/adr/000-project-charter.md)
- [Architecture decision records](docs/adr/)

The full diagram shows a production-style target. **Build and deploy a single-Region baseline first.** Region B, cross-Region replication, and the MRSC witness are optional, time-boxed labs. The diagram does not mean these resources are implemented or deployed.

## What the project demonstrates

- **Authorization:** API Gateway/WAF, bounded decision service, local feature lookup, SageMaker inference, rules fallback, idempotent result, and stable event key.
- **Streaming:** Kinesis Data Streams, Managed Apache Flink event-time windows, late-event handling, quarantine, and controlled replay.
- **Lakehouse:** S3 and Iceberg bronze/silver/gold tables, Glue transformations/catalog, reconciliation, and Athena investigation. Redshift Serverless is optional.
- **ML lifecycle:** point-in-time training, leakage checks, temporal evaluation, calibration/fairness/drift review, model registry, canary, and rollback.
- **Operations:** Terraform, least-privilege roles, encryption, observability, CI, runbooks, load tests, and failure exercises.

## Personal-project deployment strategy

1. Use one Region and one sandbox account for the baseline. Keep Region names in local configuration, not application code or committed files.
2. Use regional DynamoDB tables first. Compare MREC and MRSC only in optional experiments.
3. Estimate the temporary multi-Region lab cost before creating Region B or a witness; tear it down after the test.
4. Start with small synthetic workloads, set budget/anomaly alerts, and stop SageMaker endpoints when not testing.
5. Describe only behavior that was actually built and measured.

## Production-style build requirements

### Scope and correctness

- Simulate card-not-present authorizations and return APPROVE, STEP_UP, REVIEW, or DECLINE.
- Define versioned payment, decision, feature, and delayed-outcome schemas with stable event IDs/idempotency keys.
- Generate duplicates, late/out-of-order events, hot keys, malformed records, corrections, and delayed labels.
- Assume at-least-once delivery. Make consumers replay-safe; do not claim end-to-end exactly-once processing.
- Keep event time and label-observed time separate to prevent future-label leakage.
- Reconcile source, accepted/rejected/duplicate, decision, checkpoint, and lakehouse counts.

### Serving and resilience

- Use the charter’s p99 ≤500 ms at 100 requests/second for 30 minutes as an initial synthetic load target, not a provider guarantee.
- Keep Flink and lakehouse writes asynchronous to the response. Bound calls and retries.
- Fall back to deterministic rules when inference fails or features are stale; persist reason codes and fallback status.
- Test component restart, throttling, model timeout, stale features, replay, and reconciliation. Region evacuation is an optional lab.
- Publish measured p50/p95/p99, errors, feature age, lag, checkpoint behavior, and recovery results.

### Security and model governance

- Synthetic data only; no cardholder data or secrets in Git, logs, fixtures, or screenshots.
- Use TLS, encryption, short-lived credentials, scoped IAM, private endpoints where useful, and protected Terraform state.
- Keep S3 Object Lock off unless deliberately testing its retention and teardown consequences.
- Use temporal splits; compare the model to a rules-only baseline. Report precision/recall, calibration, segment errors, and synthetic-data limitations.
- Require model evaluation and an explicit approval step before canary deployment. Demonstrate rollback; never auto-deploy a retrained model.

## Cost controls

Continuous multi-Region serving, an MRSC witness, Flink, global tables, and SageMaker endpoints can be expensive. The default build is single-Region and time-boxed. Keep Redshift optional, run scale tests briefly, and verify teardown after each cloud exercise.

## Repository layout

    .
    ├── readme.md
    ├── architecture/                 # rendered SVG and editable Mermaid diagrams
    ├── ci/                           # validation and policy checks
    ├── data/
    │   ├── contracts/                # versioned event schemas
    │   └── synthetic/                # deterministic safe fixtures
    ├── docs/
    │   ├── adr/                      # charter and architecture decisions
    │   ├── data-contracts/
    │   └── runbooks/
    ├── infra/terraform/modules/      # small reusable modules
    ├── ml/
    │   ├── evaluation/
    │   └── pipelines/
    ├── ops/
    │   ├── alerts/
    │   ├── dashboards/
    │   └── runbooks/
    ├── scripts/
    ├── src/
    │   ├── decision-api/
    │   ├── feature-pipeline/
    │   ├── replay/
    │   └── stream-processing/flink/
    └── tests/
        ├── chaos/
        ├── contract/
        ├── integration/
        ├── load/
        └── unit/

Implementation folders are placeholders. Never commit credentials, account-specific state, Terraform state, or non-synthetic payment data.

## Build order

1. Finalize the charter and review ADRs 001–005.
2. Define contracts and deterministic synthetic data.
3. Build the local rules baseline and replay/idempotency tests.
4. Implement the one-Region AWS vertical slice.
5. Add Flink velocity features, quarantine, and replay.
6. Build Iceberg/Glue tables and reconciliation.
7. Add point-in-time ML evaluation and model registry/canary/rollback.
8. Add security controls, CI, dashboards, alerts, and runbooks.
9. Run bounded load/failure tests and publish results.
10. Optionally compare multi-Region MREC/MRSC behavior and costs, then tear down the lab.

## Current reproducible data workflow

The implemented data engineering slice is documented in [the current data workflow runbook](docs/runbooks/current-data-workflow.md). It covers deterministic synthetic batch generation, landing to S3, Athena Bronze/Silver/Gold processing, reconciliation, streaming smoke checks, training export, and the Logistic Regression baseline. Saved Athena verification queries are in [sql/athena](sql/athena/README.md).

The first automated Glue Spark batch job is documented in [the Glue batch runbook](docs/runbooks/glue-batch-etl.md). It processes one raw batch, quarantines invalid rows, merges Silver and Gold Iceberg tables, exports the split training dataset, and writes reconciliation status. It is a manually started ETL job.

The Glue success manifest triggers a container-based model-training Lambda. It reads the S3 TRAIN, VALIDATION, and TEST Parquet splits, checks label maturity and minimum sample gates, trains a versioned Logistic Regression artifact, and writes metrics to S3. Model promotion/deployment remains a separate approval step; see [the model-training Lambda runbook](docs/runbooks/model-training-lambda.md).

The cloud deployment is still a learning baseline. The architecture above describes the broader target, while the runbook distinguishes built steps from optional or future components. Running the S3 landing, Terraform, or Kinesis sections makes AWS changes and may incur charges.

## Portfolio quality gates

- No real cardholder/customer data or secrets.
- Repeated replay produces the same final decision state.
- Delayed-label evaluation shows no future leakage.
- Load-test results include measured latency distributions and failures.
- Recovery and rollback results are documented for components actually tested.
- Cost notes distinguish the baseline from optional advanced services.
- Recruiter-facing claims match the evidence and state synthetic-data limitations.

## AWS references

- [DynamoDB Global Tables design and consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.html)
- [DynamoDB Global Tables deployment checklist](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.checklist-and-faq.html)
- [Kinesis enhanced fan-out](https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html)
- [Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/)
- [AWS Glue Iceberg support](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
- [SageMaker Model Registry](https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry.html)
