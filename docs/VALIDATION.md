# Validation record

The Python automated suite exercises the full HTTP API using a temporary SQLite database: login and CSRF, application creation, collector token creation/scoping/revocation, bundle ingestion and duplicate handling, before/after reports, reassessment, demo isolation, request size rejection, and audit history. Engine tests cover stale/planned/missing evidence, public invocation, matching digest/test evidence, and not-observed change records. Collector tests confirm Python AST does not execute code or follow file symlinks, Terraform extracts only allowlisted facts, GCP normalization drops environment secret values, failed cloud reads do not pass controls, and JUnit XML rejects DTD/entities.

The additional CLI-to-HTTP test starts a real local server, scans a target repository, normalizes two synthetic GCP snapshots, submits evidence with a scoped collector token, and verifies a gap-to-met transition through persisted reports.

For the example target application, run `examples/support-agent/test_authorization.py` against a live local HTTP service with the ownership check disabled, then enabled. This HTTP test was executed locally: it failed with the ownership check disabled and passed after the check was enabled. Its JUnit output can be given to the collector, but `TEST-001` only becomes met when that test is linked to the digest of a ready deployed revision.

Container startup, Cloud SQL connectivity, GitHub OIDC, live gcloud permissions, and Cloud Run Terraform deployment require your Docker/GCP environment. The package includes the configuration and local verification commands; it does not claim that those external integrations were exercised here. A browser-accessible local preview can be checked after startup at `http://localhost:8000`.
