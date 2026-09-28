# Collectors and integrations

## Evidence flow

Git checkout + build digest + saved plan + selected live cloud observations
become a normalized `Bundle` submitted to `POST /api/ingest`. GuardGap records
the submitting collector token, stores the immutable bundle, evaluates rules,
and saves a new report. Failed source reads remain warnings or UNKNOWN facts;
collector-generated pass/fail flags are never accepted as control verdicts.

The web service makes no outbound cloud calls. Run collectors anywhere that can
reach both their evidence sources and the service. A local service and remote
CI therefore need a reachable path; a local laptop's `localhost` is not a
GitHub-hosted runner's `localhost`.

## GCP adapter

Install Google Cloud CLI on the collector runner and authenticate it. In
GitHub Actions use Workload Identity Federation, restricted to your repository,
branch/environment and intended service account. The workflow requests
`contents: read` and `id-token: write`; it does not need a service-account JSON key.

The collector calls only these command families:

- `gcloud projects get-iam-policy PROJECT`
- `gcloud projects get-ancestors PROJECT`
- `gcloud resource-manager folders get-iam-policy FOLDER`
- `gcloud organizations get-iam-policy ORGANIZATION`
- `gcloud run services describe SERVICE --region=REGION`
- `gcloud run services get-iam-policy SERVICE --region=REGION`
- `gcloud run revisions describe READY_REVISION --region=REGION`
- `gcloud sql instances describe INSTANCE`
- `gcloud storage buckets describe gs://BUCKET --raw`

Provision read permissions for the selected resources. Typically these include
`run.services.get`, `run.services.getIamPolicy`, `run.revisions.get`,
`cloudsql.instances.get`, `storage.buckets.get`, and resource-manager project,
folder and organization metadata/IAM-policy read permissions. Scope them to
what your application uses. This collector never reads Secret Manager secret
versions and does not need secret access. Parent policy visibility may require
an organization administrator to grant narrowly scoped access. If a parent
cannot be read, IAM coverage is incomplete and relevant checks cannot pass.

Capture is explicit; the tool does not assume that every resource in a project
belongs to one application. Use repeated resource flags for selected backends,
databases and buckets. Each Cloud Run service uses the supplied region. Collect
services from another region separately in this release.

IAM semantics are deliberately bounded:

- Public invocation via `allUsers` or `allAuthenticatedUsers` and known
  invocation-capable roles is a gap. Public custom roles yield UNKNOWN.
- Conditional public invocation grants are conservatively flagged, not assumed
  harmless because of their condition.
- Broad-role checks inspect direct Owner/Editor membership of selected runtime
  accounts. They do not expand Google Groups or analyze all custom permissions.
- Bucket public access prevention inherited from organization policy is UNKNOWN.
- A ready image digest is not a guarantee that 100% of live traffic reaches it.
  Traffic splitting and tagged old revisions need a future dedicated check.

## Saved Terraform plans

Produce `tfplan.json` in your existing infrastructure job:

```bash
terraform plan -out=tfplan
terraform show -json tfplan > tfplan.json
python -m guardgap collect ... --terraform-plan tfplan.json
```

Raw plan JSON may contain secrets. Do not upload it as an unrestricted job
artifact. The collector extracts only supported security facts from
`planned_values.root_module` and nested modules, then discards other fields.
It supports `google_cloud_run_v2_service`, `google_sql_database_instance`,
and `google_storage_bucket`. Unresolved values stay unknown. The plan timestamp
(or file mtime if missing) is preserved. No Terraform command is run by GuardGap.
Planned resources use a separate ID namespace and never masquerade as deployed
resources. Automatic semantic matching of arbitrary Terraform addresses to
cloud resource IDs is outside v0.1.

## Offline GCP captures

`--gcp-snapshot path.json` accepts the raw envelope produced by
`guardgap.collectors.gcp.capture(...)` instead of making live calls. It must
contain `project` and a timezone-aware `collected_at`. It has `cloud_run`
entries containing `requested_name`, `service`, `revision`, `iam_policy`;
`sql_instances` entries with `requested_name`, `instance`; `buckets` entries
with `requested_name`, `bucket`; `project_policy`, `ancestor_policies`, and
`ancestor_iam_complete`. Imported evidence retains that timestamp. Treat raw
captures as sensitive; normalized output omits secret values.

The public upload format is the normalized Bundle, not this private adapter
input. Export its JSON schema with `python -m guardgap schema`.

## Behavioral tests

Run a named negative test against the actual deployed revision, then collect:

```bash
python -m guardgap collect ... \
  --junit authorization.xml \
  --test-name test_cross_customer_denied \
  --tested-image-digest sha256:ACTUAL_DEPLOYED_DIGEST
```

A skipped, missing, or ambiguous named test yields UNKNOWN. A passed test can
be marked MET only when its supplied digest matches the collected build and a
ready deployed service. This is a trusted CI test result. GuardGap does not
inspect the test's semantics or independently prove which endpoint CI tested.
The test name, file hash and collected timestamp remain inspectable.

## GitHub job placement

Place collection after deployment and after integration tests. Supply the
image digest from the build output, not a mutable tag. Use the exact checkout
that built the image; don't fetch the current default branch after deploying
an older commit. Keep the collector package in `tools/guardgap` for the supplied
workflow, or install your own version-pinned package from an internal artifact
repository. For stronger dependency integrity, pin third-party Actions to
reviewed full commit SHAs when adopting the example in your organization.

For pre-deployment jobs, use source + Terraform plans and
`--deployment-status not_deployed`. Do not relabel planned evidence as live.
For a deployment failure, use `--deployment-status failed` if submitting the
remaining observations; build-link verification stays UNKNOWN.

## API surface

| Endpoint | Authorization | Purpose |
| --- | --- | --- |
| `GET /healthz` | None | Liveness/version only |
| `POST /api/login` | Admin password | Create 8-hour HTTP-only session |
| `GET /api/me` | Session | CSRF token and workspace configuration |
| `POST /api/applications` | Session + CSRF | Create application |
| `GET /api/applications` | Session | List applications |
| `POST /api/applications/{id}/tokens` | Session + CSRF | Create environment-scoped collector token |
| `GET /api/applications/{id}/tokens` | Session | Token metadata, never token secrets |
| `DELETE /api/tokens/{id}` | Session + CSRF | Revoke token |
| `POST /api/ingest` | Collector bearer token | Store and assess a normalized bundle |
| `POST /api/import` | Session + CSRF | Import offline normalized bundle |
| `GET /api/applications/{id}/reports` | Session | Latest 200 report summaries |
| `GET /api/reports/{id}` | Session | Report and supporting bundle |
| `POST /api/snapshots/{id}/assess` | Session + CSRF | Reassess stored evidence |
| `GET /api/controls` | Session | Control catalog |
| `GET /api/schema` | Session | Bundle JSON Schema |
| `GET /api/audit` | Session | Latest 200 audit records |

Browser mutation requests need the `X-GuardGap-CSRF` header returned by `/api/me`.
Tokens are shown once, stored as hashes and restricted to ingestion for their
application/environment. Repeating an identical bundle ID is idempotent;
reusing the ID for different content returns 409.

## Extending coverage

Add a collector module that produces typed Resource facts with a capture
timestamp and source locator. Add supported resource kinds/fields in models.py,
then a catalog entry and predicate in engine.py. A rule must define missing,
partial, stale, planned, and contradictory evidence behavior. Add tests that
prove absent data cannot pass. Version the evidence schema when its semantics
change. Do not let incoming bundles define executable rules or commands.

Official reference material used for this integration:

- https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-google-cloud-platform
- https://docs.cloud.google.com/run/docs/authenticating/public
- https://docs.cloud.google.com/sdk/gcloud/reference/run/services/describe
- https://docs.cloud.google.com/run/docs/reference/rest/v1/namespaces.revisions
- https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/describe
- https://developer.hashicorp.com/terraform/cli/commands/show
