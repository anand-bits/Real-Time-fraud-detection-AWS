# SentinelPay event contracts and field guide

These JSON Schema files define the version-1 event shapes. In these event records, a “column” means a JSON field. A field has a name, data type, and meaning.

All records carry data_classification=SYNTHETIC and schema_version=1. Timestamps are UTC RFC 3339 strings. IDs/tokens are generated placeholders. V1 rejects unknown fields; when the contract changes, update the schema version and its examples deliberately.

## PaymentAuthorizedV1
File: payment-authorized.schema.json. Emitted when a simulated payment reaches the authorization service.

| Field | Type | Meaning |
|---|---|---|
| data_classification | string | Always SYNTHETIC; makes the data boundary visible downstream. |
| schema_version | integer | Contract version; currently 1. |
| event_id | string | Identity of this event. Redelivery keeps the same ID. |
| payment_id | string | Stable identity for the logical simulated payment. |
| idempotency_key | string | Request key used to avoid creating multiple decisions on retry. |
| event_time | timestamp | When the payment happened at its source. |
| received_at | timestamp | When this system received it; compare with event_time to detect late arrival. |
| payment_token | string | Fake token for the payment instrument; never a PAN. |
| account_token | string | Fake account token used to group account behavior. |
| merchant_id | string | Fake merchant identity. |
| device_token | string | Fake device identity. |
| amount | number | Amount in major currency units, such as 84.50. |
| currency | string | Three-letter currency code. Do not aggregate different currencies without conversion. |
| channel | string | Scenario channel; V1 is CARD_NOT_PRESENT. |
| country_code | string | Synthetic two-letter country code, not a raw IP address. |
| device_first_seen_days | integer | Days since this device was first seen; 0 means first seen today. |
| source_region | string | AWS Region label where the event entered the demo. |
| trace_id | string | Fake correlation ID for joining logs and events. |

## FraudDecisionV1
File: fraud-decision.schema.json. Emitted by the decision service after scoring.

| Field | Type | Meaning |
|---|---|---|
| data_classification | string | Always SYNTHETIC. |
| schema_version | integer | Contract version, currently 1. |
| decision_id | string | Unique identity of the persisted decision. |
| event_id | string | Payment event that was scored. |
| payment_id | string | Logical payment being decided. |
| decision | string | APPROVE, STEP_UP, REVIEW, or DECLINE. |
| risk_score | number | Score from 0 (lower risk) to 1 (higher risk). |
| reason_codes | string array | Stable machine-readable reasons for the result. |
| model_id | string | Model or rules-engine name. |
| model_version | string | Exact version used for this result. |
| policy_version | string | Version of thresholds/action policy. |
| feature_age_ms | integer | Age of the oldest feature used, in milliseconds. |
| fallback_used | boolean | True if rules fallback replaced model inference. |
| decision_time | timestamp | When the decision was committed. |
| source_region | string | Region that created the decision. |
| trace_id | string | Correlation ID shared with the request. |

## ChargebackOutcomeV1
File: chargeback-outcome.schema.json. Emitted later as the simulated ground-truth label. It is deliberately separate from the payment event.

| Field | Type | Meaning |
|---|---|---|
| data_classification | string | Always SYNTHETIC. |
| schema_version | integer | Contract version, currently 1. |
| outcome_event_id | string | Unique identity of this later outcome record. |
| payment_id | string | Payment to which the label belongs. |
| outcome | string | CONFIRMED_FRAUD or NO_FRAUD. |
| outcome_source | string | Always SYNTHETIC_LABEL_GENERATOR; identifies the simulated label source. |
| payment_event_time | timestamp | Original payment time. |
| label_observed_at | timestamp | When the simulated system learns the outcome; default is 30 days later. |
| source_region | string | Region where the simulated outcome is emitted. |
| trace_id | string | Fake correlation ID linking outcome and payment. |

## FeatureUpdateV1
File: feature-update.schema.json. Represents a calculated window, not an individual raw payment.

| Field | Type | Meaning |
|---|---|---|
| data_classification | string | Always SYNTHETIC. |
| schema_version | integer | Contract version, currently 1. |
| feature_event_id | string | Unique identity of this feature snapshot. |
| entity_type | string | ACCOUNT, PAYMENT_TOKEN, DEVICE, or MERCHANT. |
| entity_token | string | Fake token for the entity summarized. |
| feature_version | integer | Version of the feature calculation logic. |
| window_start / window_end | timestamps | Start (inclusive) and end (exclusive) of the event-time window. |
| window_seconds | integer | Window length in seconds. |
| transaction_count | integer | Number of payments for this entity in the window. |
| amount_sum | number | Sum of amounts in the stated currency. |
| currency | string | Currency of amount_sum; never mix currencies implicitly. |
| distinct_merchant_count | integer | Count of unique synthetic merchants in the window. |
| new_device_count | integer | Count of first-seen devices in the window. |
| computed_at | timestamp | When the streaming job produced the feature snapshot. |
| source_region | string | Region that computed the feature. |

## Examples and generation

Examples for all four contracts are in examples/. The synthetic generator creates payment events, delayed outcomes, duplicates, shuffled arrival order, late events, and a separate intentionally-invalid file. It does not generate decision or feature events; those are examples for the next implementation stage.

From the repository root:

    python3 data/synthetic/generate_events.py --events 1000 --output work/synthetic
    python3 -m unittest discover -s tests/contract -v

The second command requires the JSON Schema test dependency installed with:

    python3 -m pip install -r data/contracts/requirements-dev.txt

