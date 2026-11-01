# ADR-005: Serving-path latency budget

**Status:** Accepted as an initial personal-demo target; revise from measurements  
**Date:** 2026-11-01

## Context
The charter targets p99 response latency ≤500 ms at 100 requests/second for 30 minutes. The baseline is one Region with a local DynamoDB ledger. The diagram’s MRSC path is optional and is not assumed to meet this budget.

## Baseline budget

| Stage | Initial p99 allocation |
|---|---:|
| API edge, request parsing, response overhead | 50 ms |
| Local feature lookup and freshness check | 50 ms |
| SageMaker inference and serialization | 250 ms |
| Risk policy, reason codes, bounded rules fallback | 50 ms |
| Local conditional idempotency-ledger write | 75 ms |
| Kinesis event append and remaining service overhead | 25 ms |
| **End-to-end target** | **500 ms** |

This is a measurement budget, not an AWS service guarantee. Stage percentiles do not add mathematically to end-to-end p99; instrument each stage and measure the full request separately.

## Serving-path rules
- Keep Flink aggregation and S3/Iceberg writes asynchronous; do not wait for them in the authorization path.
- Bound every call and retry. Use a rules-only fallback when inference is late or invalid.
- Commit the idempotency decision and append the event before returning success. If persistence fails before the deadline, return a retryable unavailable response with the stable key; never return an unrecorded decision.
- Keep feature reads local and record feature age.
- In the optional MRSC lab, trace commit latency separately. If it misses the budget, report the result and compare with the baseline. Do not run MRSC continuously just to satisfy the diagram.

## Acceptance tests
- 100 requests/second for 30 minutes in the baseline Region; report p50/p95/p99, errors, timeouts, fallback rate, feature age, ledger latency, and Kinesis append latency.
- 2× target for 5 minutes; report lag and recovery.
- Inject inference timeout, stale features, ledger throttling, Kinesis errors, and process restart; verify bounded responses, idempotency, replay, and reconciliation.
- Keep tests synthetic and time-boxed. Compare provisioned inference and autoscaling only if the experiment budget allows.

## Revisit when
Measurements miss the target, the model or request rate changes, or the optional multi-Region/MRSC design is activated.
