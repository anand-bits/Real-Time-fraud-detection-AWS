# ADR-000: SentinelPay project charter

**Status:** Draft — portfolio assumptions, not company-approved business or compliance requirements  
**Date:** 2026-11-01  
**Owner:** Project author  
**Decision scope:** Define the simulated fraud problem, decision boundary, success measures, and constraints before implementation.

## 1. Problem statement

Build a production-oriented portfolio system that scores synthetic card-not-present e-commerce payment authorizations in real time, uses streaming behavior to enrich risk features, and produces an auditable recommendation. The system should demonstrate that an event can be scored, recorded once despite duplicate delivery, replayed, reconciled, investigated, and evaluated against delayed outcomes.

This project does not process real payments or make decisions for a financial institution. It uses synthetic records and simulated outcomes only.

## 2. User and decision boundary

- **Primary user:** A payment authorization service requesting a risk recommendation.
- **Secondary users:** Fraud/risk analyst reviewing flagged cases; data scientist evaluating model performance; on-call engineer operating the pipeline.
- **Unit of decision:** One payment authorization request, identified by a stable synthetic payment ID and idempotency key.
- **Allowed recommendations:** APPROVE, STEP_UP, REVIEW, DECLINE.
- **Decision evidence:** Risk score, rules triggered, model version, feature freshness, policy version, decision timestamp, and fallback indicator.

The decision policy is an explicit project configuration. A missing model response or stale feature must not silently become a decline. The demonstrator uses a deterministic rules-only fallback and records why it was used.

## 3. In-scope event and data

A payment authorization event contains:

- Stable event ID, payment ID, idempotency key, schema version, and correlation ID.
- Synthetic tokenized account/card, merchant, device, and IP identifiers.
- Amount, currency, channel, country, and synthetic merchant/device risk attributes.
- Event time, received time, source Region, and origin Region.

A later outcome event contains the related payment ID, outcome type, label-observed time, and source. The online decision must not see its future outcome. The training and evaluation pipeline must use only labels available as of the simulated evaluation time.

**Data boundary:** use generated identities and values only. Never ingest or generate PAN, CVV, track data, credentials, or production customer data.

## 4. Fraud definition and label assumptions

For the portfolio simulation, a payment is positive when the synthetic outcome generator marks it as confirmed unauthorized fraud or a confirmed fraud chargeback. The generator will create both fraud and legitimate examples, including overlapping signals so that classification is not a trivial rule lookup.

- Label maturity assumption: fraud/chargeback outcomes become available 30 simulated days after payment.
- Preserve payment event time and label-observed time separately.
- Keep fraud labels out of the authorization event and out of features available before label observation.
- Support later corrections to an outcome without duplicating the payment decision.

The 30-day delay is a project simulation choice, not a claim about industry-wide chargeback timing.

## 5. Decision policy assumptions

The decision service produces a recommendation and reason codes. The portfolio policy is:

- Low estimated risk: APPROVE.
- Intermediate risk or missing/stale signals: STEP_UP or REVIEW, based on configured policy.
- High estimated risk: DECLINE only when the configured policy threshold is met.
- Model timeout or invalid response: invoke deterministic rules-only fallback; persist fallback status and reason.
- Region failure: route to the healthy Region only after the prior writer for the affected entity is fenced. Do not allow both Regions to write the same home-region-owned feature partition during failover.

Risk thresholds are configuration, not code constants. Every change is versioned and evaluated against the same temporal holdout.

## 6. Portfolio acceptance targets

These are initial engineering targets for the synthetic demonstrator. They are not production guarantees or externally validated industry benchmarks. Measure them and revise the design if the tests fail.

| Measure | Initial target | How it will be measured |
|---|---:|---|
| Authorization response latency | p99 ≤ 500 ms at 100 requests/second for 30 minutes in each serving Region | Load test with regional dependencies; report p50/p95/p99 and error rate |
| Burst handling | 2× steady target rate for 5 minutes without event loss; recovery lag is measured and reported | Load test plus Kinesis/Flink lag and checkpoint metrics |
| Synthetic fraud detection | Recall ≥ 80% while legitimate false-decline rate ≤ 1% on a matured temporal holdout | Report confusion matrix, precision-recall curve, PR-AUC, calibration, and threshold |
| Manual review workload | ≤ 5% of evaluated payments enter REVIEW at the selected threshold | Count review recommendations on holdout data |
| Idempotency | Replaying the same event set yields the same final decision state and no duplicate payment decisions | Replay test with duplicates and reordered delivery |
| Reconciliation | Every source record is accounted for as accepted, rejected, or duplicate; decision and lake totals reconcile | Automated run report with zero unexplained count difference |
| Availability exercise | ≥ 99.9% successful requests during steady-state load test, excluding intentionally injected failure intervals | Load-test result and request/response ledger |

Synthetic model metrics only show whether the implementation meets its generated-data objective. They do not establish real-world fraud effectiveness.

## 7. Failure and operational behavior

- Model endpoint unavailable: rules-only fallback, explicit reason code, metric and alert.
- Feature stale or unavailable: use allowed local/rules-only signals; record feature age; never treat missing features as evidence of fraud.
- Invalid schema: quarantine with source identity and error reason; alert on rate increase.
- Duplicate event: return the existing idempotent decision or equivalent persisted result.
- Stream lag: authorization continues only within its defined feature freshness and fallback policy; alert and reconcile lagging events later.
- Region evacuation: health-based routing, entity writer fencing, controlled promotion, and post-failover reconciliation.
- Recovery and retention objectives for every dataset are finalized in architecture ADRs before deployment.

## 8. Out of scope

- Real cardholder data, real payment authorization, and real customer impact.
- Claiming PCI DSS compliance or production certification.
- Automatic model retraining-to-production without review and approval.
- Choosing fraud thresholds on behalf of a real business.
- Deploying continuously running multi-Region infrastructure before load and cost checks.

## 9. Required reviewers and responsibilities

For the portfolio, the project author simulates these roles and records review decisions:

- **Business/risk owner:** fraud definition, action policy, loss/false-decline tradeoff, review capacity.
- **Payments owner:** request/response contract, timeout budget, idempotency behavior.
- **Security/privacy owner:** data classification, token boundary, access and retention controls.
- **Platform/on-call owner:** SLOs, alert routing, recovery and failover runbooks.
- **Data/ML owner:** labels, leakage prevention, feature definitions, evaluation protocol, model approval.

A company deployment requires named accountable owners and documented approval from the organization.

## 10. Step 1 exit criteria

Step 1 is complete when:

1. The synthetic payment flow and decision actions are agreed.
2. Label definition, delayed-label behavior, and leakage boundary are explicit.
3. Initial measurable portfolio targets are accepted or edited.
4. Fallback behavior and entity ownership during failover are documented.
5. Data restrictions and reviewer roles are acknowledged.
6. These requirements are recorded as the baseline for architecture decisions and later tests.

**Next step:** create ADRs for Region selection, MREC versus MRSC use, RTO/RPO, event retention, and serving-path latency budget. Do not provision the full multi-Region stack until those decisions and cost implications are reviewed.
