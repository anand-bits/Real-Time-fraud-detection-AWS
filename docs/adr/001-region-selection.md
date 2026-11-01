# ADR-001: Region selection

**Status:** Accepted for personal portfolio baseline
**Date:** 2026-11-01
**Scope:** Synthetic learning/demo deployment only

## Context
The first version should demonstrate production patterns without requiring a continuously running multi-Region footprint. No real payment, cardholder, or company data is in scope.

## Decision
- The baseline deploys into **one AWS Region**, supplied through local Terraform configuration. Do not hardcode a Region in application code or commit account-specific environment files.
- Select a Region where required services are available, considering cost and the developer’s test location. This project does not prescribe a home Region.
- Region B and Region C in the architecture are an **optional, temporary resilience lab**, not part of the default deployment.
- For an MRSC comparison, choose a supported three-Region set after checking current AWS availability. A candidate APAC set is ap-south-1, ap-southeast-1, and ap-northeast-1; change it if availability, latency, or cost makes another set better.

## Rationale and consequences
A single Region is enough to demonstrate authorization, streaming, lakehouse, model lifecycle, security boundaries, and recovery from component/AZ failures. Regional failover can be added later as a short experiment.

The baseline makes no Region-level disaster-recovery claim. The advanced lab adds duplicated services, inter-Region transfer, global tables, KMS/logging setup, and possibly a witness Region. Estimate cost first, run for a bounded test window, then tear it down. Verify service availability and quotas before applying.

## Revisit when
The selected Region lacks a required service, the test location changes measured latency/cost, or a residency requirement is introduced.

## References
- [DynamoDB Global Tables design guidance](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.html)
- [DynamoDB Global Tables deployment checklist](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.checklist-and-faq.html)
