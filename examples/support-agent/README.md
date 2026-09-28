# Runnable target application

This is the application being assessed, separate from GuardGap. It supports a
real local cross-customer authorization test and an optional Vertex AI call.
Its static application bearer tokens are fixture identities, not production IAM.

From this directory, after installing dependencies:

```bash
export SUPPORT_TOKENS_JSON='{"local-customer-a":"customer-a","local-customer-b":"customer-b"}'
export SUPPORT_LOCAL_MODE=true
export ENFORCE_TENANT_CHECK=false
python -m uvicorn app:app --host 127.0.0.1 --port 8081
```

In another terminal from the GuardGap root:

```bash
export SUPPORT_BASE_URL=http://127.0.0.1:8081
export TENANT_A_TOKEN=local-customer-a
export TENANT_B_TOKEN=local-customer-b
python -m pytest examples/support-agent/test_authorization.py --junitxml=authorization.xml
```

The test should fail. Stop the example server, set `ENFORCE_TENANT_CHECK=true`,
restart it and repeat the test. It should pass. This is an actual HTTP behavior
check, unlike the separately labeled dashboard fixture walkthrough.

For GCP: build this directory as its own image, deploy to Cloud Run with a
dedicated service account, put `SUPPORT_TOKENS_JSON` in Secret Manager, and
supply `SUPPORT_DATABASE_URL` for a PostgreSQL database. Do not persist SQLite
on Cloud Run. For the model route set `SUPPORT_LOCAL_MODE=false`,
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and an available `GEMINI_MODEL`;
grant the runtime identity the necessary Vertex AI permissions. Provision the
fixture identities only in an isolated test environment. Replace them with real
identity validation and customer membership before production use.

The `/ask` route reads only the authenticated customer's records. The update
endpoint demonstrates the deterministic authorization check an agent tool
would call. This sample does not implement an autonomous multi-tool agent or
a Storage upload flow. The collector can assess your application's real Cloud
SQL and Storage resources independently of this sample.

To submit deployed behavioral evidence, run the integration test against the
actual deployed image, then supply the JUnit file, explicit test name, and that
image digest to `guardgap collect`. Local tests without matching deployed
image evidence remain UNKNOWN for TEST-001, as intended.
