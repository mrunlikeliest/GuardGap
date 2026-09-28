# Security boundary and evidence semantics

GuardGap stores architecture metadata, IAM principals, source file names, routes, resource names, and security findings. That metadata can be sensitive. Restrict dashboard access, protect the PostgreSQL volume and backups, use HTTPS off localhost, and configure database retention for your organization.

## Trust model

- The server trusts authenticated collectors for the facts they report. Collector bearer tokens are 38+ random bytes, stored only as SHA-256 hashes in the database, shown once and scoped to one application/environment. Protect them in the CI secret store; rotate/revoke after compromise.
- The collector reads code and cloud metadata with the runner's own permissions. It does not execute source code, run Terraform, read secret payloads, or accept commands from incoming data. A compromised runner can still forge evidence, so avoid collecting on untrusted pull-request code with privileged cloud permissions.
- Password-based administration uses a salted scrypt hash. The browser receives an eight-hour HTTP-only, SameSite=Strict session and a CSRF value for mutations. This is a single-administrator service, with no per-user audit identity or SSO in v0.1.
- Requests are limited to 5 MB. Evidence uses an allowlisted Pydantic schema and fixed control predicates. Some values such as resource names, paths, IAM principals, and secret *names* are intentionally retained for assessment. Raw environment values and secret content are not included by the bundled collectors.
- `guardgap collect` rejects non-local plaintext HTTP by default. It follows no redirects. An explicit `--allow-http` opts in to an operator-controlled network.

## What MET means

A `met` result means the named, narrowly defined predicate held for the available fresh evidence. It does not certify the application's security. Missing inputs, collection errors, old snapshots, unsupported inherited settings, and planned-only observations remain `unknown`. An observation older than `GUARDGAP_MAX_EVIDENCE_HOURS` (24 by default) becomes `unknown` on a new assessment.

GitHub Actions and the GCP collector can establish a chain of source commit → CI-supplied image digest → ready Cloud Run revision digest. CI-supplied provenance is trusted and not cryptographically attested here. A ready revision may not serve all traffic if the service splits traffic to older revisions. Test evidence is trusted JUnit output with an image digest supplied by the runner; GuardGap does not replay the requests itself.

The database keeps received evidence and report history, including demo records when demo mode is enabled. Admins can inspect them through the dashboard. Demo evidence cannot enter `/api/ingest` with a collector token and is labeled throughout the UI.

## Operational considerations

The example GitHub Actions job is a manual trigger. Restrict the GitHub environment to approved branches, issue a narrowly scoped GCP Workload Identity Federation principal, and put collection after successful deployment. Do not upload raw Terraform state, plan output, live gcloud dumps, `SUPPORT_TOKENS_JSON`, or `.env` as artifacts. Normalized bundles can still contain sensitive architecture metadata and should have short artifact retention.

A publicly exposed single-password dashboard needs an upstream access gateway, edge rate limiting, logs, and organization-appropriate identity management before broad rollout. The built-in per-IP login throttle is a basic defense, not a distributed anti-abuse system. Replace the supplied sample application's fixture tokens with production identity verification before deploying it beyond an isolated test.
