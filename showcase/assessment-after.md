# GuardGap assessment

Assessed: 2026-09-28T04:02:17.968782+00:00

Checks apply to selected resources under a private-backend baseline. MET confirms the stated check within collected evidence, not complete security. Collector identity is trusted; observations are not independently attested.

| Control | Resource | Status | Observation |
| --- | --- | --- | --- |
| IAM-001 | showcase-project IAM | met | No direct Owner or Editor bindings found for the selected runtime identities in the collected scopes. |
| RUN-001 | support-agent-api | met | Invoker IAM checking is enabled and collected service/ancestor bindings contain no public grants. |
| RUN-002 | support-agent-api | met | A non-default runtime service account is explicitly configured. |
| RUN-003 | support-agent-api | met | The ready deployed revision matches the immutable digest supplied by CI. |
| SQL-001 | customer-records | met | Public IPv4 is disabled and no public address was observed. |
| SQL-002 | customer-records | met | Database configuration requires encrypted connections. |
| GCS-001 | support-documents | met | Public access prevention is explicitly enforced on the bucket. |
| GCS-002 | support-documents | met | Uniform bucket-level access is enabled. |
| TEST-001 | test_cross_customer_denied | met | The named negative authorization test passed for this image, according to CI. |
