# Deploy GuardGap

The web service is portable. Its collectors run in GitHub Actions, a self-hosted runner, or another host with access to the application's source and GCP. They post normalized evidence to the service over HTTPS. The service never needs the collector's cloud identity.

## Local machine

Follow the root README for Python or Docker Compose. The local Docker service binds `127.0.0.1:8000`; a remote GitHub-hosted runner cannot access it. Use a self-hosted runner on the same reachable network, or write an offline bundle and import it in the dashboard.

## VM / container host

Use `deploy/compose.postgres.yaml` for a single VM. Create `.env` with `python scripts/bootstrap.py`, add a strong random `POSTGRES_PASSWORD`, set `GUARDGAP_SECURE_COOKIE=true`, and start from the package root:

```bash
docker compose --env-file .env -f deploy/compose.postgres.yaml up --build -d
```

This Compose configuration binds GuardGap to localhost and uses a persistent PostgreSQL volume. Terminate TLS at a reverse proxy such as the packaged Caddyfile and point DNS to the host. Add backups and a retention policy for the database. Keep the reverse proxy and database patched. Do not expose port 8000 or 5432 directly to the internet.

`DATABASE_URL` may point to an externally managed PostgreSQL server. Provision the database/user first, enable TLS and backups according to your provider, then supply the connection URI through your secret store. Only one database schema version (0.1.0) is supported; `create_all` adds tables but does not migrate existing tables. Take a backup and test a migration before upgrading the schema. Running more than one server replica requires a PostgreSQL database and deployment coordination; this release assumes one instance.

## Cloud Run example for the GuardGap service

`deploy/cloudrun.tf` is an optional starting point if you want to host GuardGap itself on GCP. It assumes an existing Cloud SQL PostgreSQL instance, a database/user, and two existing Secret Manager secrets:

- `DATABASE_URL`: a SQLAlchemy PostgreSQL URL (typically using `postgresql+psycopg://` and the `/cloudsql/PROJECT:REGION:INSTANCE` socket).
- `GUARDGAP_ADMIN_PASSWORD_HASH`: a salted hash in the exact `scrypt:salt:hash` format produced by `scripts/bootstrap.py`. Copy only that value; never upload the bootstrap `.env` file.

Build and push the Docker image to a registry your Cloud Run deployment can read. Pass its immutable digest as `image`, along with `project_id`, `cloud_sql_connection_name`, and the names of the two existing secrets. Inspect the Terraform plan before applying. Set `public_login_endpoint=false` (the default) to keep Cloud Run IAM authentication. Authorized users can use an authenticated proxy to reach the dashboard; CI can set `GUARDGAP_IDENTITY_TOKEN` to an ID token for that Cloud Run URL, and must still provide its GuardGap collector token. Configure audience and token minting according to your GCP access design.

If you explicitly set `public_login_endpoint=true`, GuardGap's own password/session and collector-token checks are the perimeter for a publicly reachable HTTPS endpoint. This is useful for an isolated test but requires careful credential protection, monitoring, and rate limiting at the edge. The app has a single-admin password and no SSO/RBAC. Do not treat the supplied Cloud Run Terraform as a completed enterprise access architecture.

Cloud Run uses `GUARDGAP_SECURE_COOKIE=true`, disables fixture demo mode, mounts the Cloud SQL Unix socket, runs one server instance, and injects secrets through references. SQLite is inappropriate for Cloud Run because its filesystem is ephemeral. The service image does not include gcloud; the CI collector authenticates separately.

The Cloud Run example is source-only. It was not applied to a cloud account as part of this deliverable.

## Network and CI routing

The collector posts to `POST /api/ingest` using `GUARDGAP_URL` and a scoped `GUARDGAP_TOKEN`. From a GitHub-hosted runner, choose a reachable HTTPS hostname and outbound access. For a private Cloud Run endpoint, authenticate the runner with Workload Identity Federation and provide an appropriately scoped Cloud Run ID token as `GUARDGAP_IDENTITY_TOKEN`. The service's own token still scopes each bundle to an application and environment. A self-hosted runner can connect through your private network to a VM-hosted service instead.

Deploy the service before enabling the post-deployment collection step. After changing a control, run the application's usual pipeline and let the collector gather a new live snapshot. Pressing **Reassess snapshot** in the UI only recomputes the old evidence.

## Other hosting platforms

Run the Docker image on any container platform that supports port `8000`, persistent PostgreSQL, TLS termination, and secret injection. Set `DATABASE_URL`, `GUARDGAP_ADMIN_PASSWORD_HASH`, `GUARDGAP_SECURE_COOKIE=true`, `GUARDGAP_DEMO=false`, and `PORT=8000`. Use one replica for this release. Health endpoint: `/healthz`.

Hosting anywhere does not imply that AWS or Azure can be assessed by the initial GCP adapter. The service receives versioned normalized bundles, so adding native cloud collectors does not require changing where it is hosted.
