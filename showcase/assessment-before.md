# GuardGap assessment

Assessed: 2026-09-28T04:02:16.062971+00:00

Checks apply to selected resources under a private-backend baseline. MET confirms the stated check within collected evidence, not complete security. Collector identity is trusted; observations are not independently attested.

| Control | Resource | Status | Observation |
| --- | --- | --- | --- |
| IAM-001 | showcase-project IAM | gap | A selected runtime identity has a direct Owner or Editor binding in the collected policies. |
| RUN-001 | support-agent-api | gap | The Cloud Run Invoker IAM check is disabled. |
| RUN-002 | support-agent-api | gap | The runtime uses a default service account. |
| RUN-003 | support-agent-api | met | The ready deployed revision matches the immutable digest supplied by CI. |
| SQL-001 | customer-records | gap | Public IPv4 is enabled or a public address is assigned. |
| SQL-002 | customer-records | gap | The database allows unencrypted connections. |
| GCS-001 | support-documents | unknown | Bucket enforcement is not explicit; effective inherited organization policy is not collected. |
| GCS-002 | support-documents | gap | Object ACLs are still enabled. |
| TEST-001 | test_cross_customer_denied | gap | The named negative authorization test failed. |
