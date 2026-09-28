"""Deterministic controls. Missing evidence is UNKNOWN, never an implicit pass."""
from datetime import datetime, timezone
from .models import Bundle

CATALOG = [
    {"id":"RUN-001", "kind":"cloud_run", "title":"Backend invocation requires IAM authentication", "severity":"high", "fix":"Enable the Cloud Run Invoker IAM check. Remove allUsers/allAuthenticatedUsers invoker grants at the service and ancestor scopes. Collect all ancestor policies; inspect custom roles separately."},
    {"id":"RUN-002", "kind":"cloud_run", "title":"Service uses a dedicated runtime identity", "severity":"medium", "fix":"Assign a dedicated user-managed service account to the Cloud Run revision instead of a Compute Engine or App Engine default identity."},
    {"id":"RUN-003", "kind":"cloud_run", "title":"Ready revision matches the collected build digest", "severity":"high", "fix":"Deploy the immutable image digest produced by this commit. Wait for the revision to be ready and collect its imageDigest. Supply --image-digest from the trusted build output."},
    {"id":"IAM-001", "kind":"project_iam", "title":"Selected runtime identities have no basic broad roles", "severity":"high", "fix":"Remove roles/owner and roles/editor for the selected runtime service accounts at project, folder, and organization scopes. Grant task-specific roles. This check does not establish full least privilege or inspect group/custom-role expansion."},
    {"id":"SQL-001", "kind":"cloud_sql", "title":"Database has no public IP", "severity":"high", "fix":"Disable ipv4_enabled and use a private network path. Recollect the instance after the change. Cloud SQL may take time to finish updates."},
    {"id":"SQL-002", "kind":"cloud_sql", "title":"Database requires encrypted connections", "severity":"medium", "fix":"Set ssl_mode to ENCRYPTED_ONLY or TRUSTED_CLIENT_CERTIFICATE_REQUIRED and configure compatible clients."},
    {"id":"GCS-001", "kind":"gcs_bucket", "title":"Bucket explicitly enforces public access prevention", "severity":"high", "fix":"Set public_access_prevention = \"enforced\" on this bucket. An inherited setting needs additional organization-policy evidence and is UNKNOWN in this version."},
    {"id":"GCS-002", "kind":"gcs_bucket", "title":"Bucket uses uniform access control", "severity":"medium", "fix":"Enable uniform_bucket_level_access after migrating any required object ACL access to bucket IAM."},
    {"id":"TEST-001", "kind":"authorization_test", "title":"Negative authorization test passed for this image", "severity":"high", "fix":"Run a cross-customer denial integration test against the deployed revision. Submit JUnit plus the tested image digest with the collector. This records the CI test result, not exhaustive authorization correctness."},
]

PUBLIC = {"allUsers", "allAuthenticatedUsers"}
INVOKE_ROLES = {"roles/run.invoker", "roles/run.admin", "roles/owner", "roles/editor"}

def predicate(rule, resource, bundle):
    f = resource.facts
    if rule == "RUN-001":
        if f.invoker_iam_disabled is True:
            return "gap", "The Cloud Run Invoker IAM check is disabled."
        public = [b for b in f.iam_bindings if PUBLIC.intersection(b.get("members", []))]
        if any(b.get("role") in INVOKE_ROLES for b in public):
            return "gap", "A service or ancestor policy grants invocation-capable access to a public principal."
        if public:
            return "unknown", "Public-principal role bindings require permission expansion; no safe conclusion."
        if f.invoker_iam_disabled is None or not f.iam_complete:
            return "unknown", "Invoker configuration or complete service/ancestor IAM evidence is unavailable."
        return "met", "Invoker IAM checking is enabled and collected service/ancestor bindings contain no public grants."
    if rule == "RUN-002":
        sa = f.service_account
        if not sa: return "unknown", "Runtime service account was not collected."
        if sa.endswith("-compute@developer.gserviceaccount.com") or sa.endswith("@appspot.gserviceaccount.com"):
            return "gap", "The runtime uses a default service account."
        return "met", "A non-default runtime service account is explicitly configured."
    if rule == "RUN-003":
        if not bundle.expected_image_digest or not f.image_digest or f.ready is None:
            return "unknown", "Build digest or ready revision evidence is missing."
        if bundle.deployment_status != "succeeded":
            return "unknown", "The collector did not report a successful deployment."
        if not f.ready: return "gap", "The latest created revision is not ready."
        if f.image_digest != bundle.expected_image_digest:
            return "gap", "The deployed image digest differs from the collected build."
        return "met", "The ready deployed revision matches the immutable digest supplied by CI."
    if rule == "IAM-001":
        identities = {r.facts.service_account for r in bundle.resources if r.kind == "cloud_run" and r.layer == resource.layer and r.facts.service_account}
        if not identities: return "unknown", "No runtime identities are available to correlate with IAM."
        members = {"serviceAccount:" + sa for sa in identities}
        if any(b.get("role") in {"roles/owner", "roles/editor"} and members.intersection(b.get("members", [])) for b in f.iam_bindings):
            return "gap", "A selected runtime identity has a direct Owner or Editor binding in the collected policies."
        if not f.iam_complete: return "unknown", "Ancestor IAM coverage is incomplete."
        return "met", "No direct Owner or Editor bindings found for the selected runtime identities in the collected scopes."
    if rule == "SQL-001":
        if f.public_ip_enabled is True or f.public_ip_present is True:
            return "gap", "Public IPv4 is enabled or a public address is assigned."
        if f.public_ip_enabled is False and (resource.layer == "planned" or f.public_ip_present is False):
            return "met", "Public IPv4 is disabled and no public address was observed."
        return "unknown", "Public IP settings or address inventory are missing."
    if rule == "SQL-002":
        if f.ssl_mode in {"ENCRYPTED_ONLY", "TRUSTED_CLIENT_CERTIFICATE_REQUIRED"}:
            return "met", "Database configuration requires encrypted connections."
        if f.ssl_mode == "ALLOW_UNENCRYPTED_AND_ENCRYPTED":
            return "gap", "The database allows unencrypted connections."
        return "unknown", "No supported explicit SSL mode was collected."
    if rule == "GCS-001":
        if f.public_access_prevention == "enforced": return "met", "Public access prevention is explicitly enforced on the bucket."
        return "unknown", "Bucket enforcement is not explicit; effective inherited organization policy is not collected."
    if rule == "GCS-002":
        if f.uniform_bucket_access is None: return "unknown", "Uniform bucket access setting is missing."
        return ("met", "Uniform bucket-level access is enabled.") if f.uniform_bucket_access else ("gap", "Object ACLs are still enabled.")
    if rule == "TEST-001":
        if not f.tested_image_digest or f.tested_image_digest != bundle.expected_image_digest:
            return "unknown", "Test evidence is not linked to this build digest."
        if not any(r.kind == "cloud_run" and r.layer == "deployed" and r.facts.ready and r.facts.image_digest == f.tested_image_digest for r in bundle.resources) or bundle.deployment_status != "succeeded":
            return "unknown", "The tested image is not confirmed on a ready deployed service."
        if f.test_passed is None: return "unknown", "Test result is absent or skipped."
        return ("met", "The named negative authorization test passed for this image, according to CI.") if f.test_passed else ("gap", "The named negative authorization test failed.")
    raise ValueError("unknown control")

def assess(bundle: Bundle, max_age_hours=24, now=None):
    now = now or datetime.now(timezone.utc)
    findings = []
    for resource in bundle.resources:
        for control in CATALOG:
            if resource.kind != control["kind"]: continue
            status, message = predicate(control["id"], resource, bundle)
            observed = status
            age = (now - resource.evidence.collected_at).total_seconds() / 3600
            if age > max_age_hours:
                status, message = "unknown", f"Evidence is older than {max_age_hours} hours. Collect a new snapshot. Last observation: {message}"
            elif resource.layer == "planned":
                status, message = "unknown", f"Planned only ({observed}); deployment confirmation is pending. {message}"
            findings.append({**control, "resource_id": resource.id, "resource_name": resource.name, "status": status, "observed_status": observed, "layer": resource.layer, "message": message, "evidence": resource.evidence.model_dump(mode="json")})
    if not any(r.kind == "authorization_test" for r in bundle.resources) and any(r.kind == "cloud_run" or r.facts.ai_signals for r in bundle.resources):
        control = next(c for c in CATALOG if c["id"] == "TEST-001")
        findings.append({**control,"resource_id":"application", "resource_name":"Application", "status":"unknown", "observed_status":"unknown", "layer":"test", "message":"A selected application backend or AI signal was observed, but no linked negative authorization test evidence was supplied.", "evidence":None})
    counts = {s: sum(f["status"] == s for f in findings) for s in ("met", "gap", "unknown")}
    return {"engine_version":"0.1.0", "assessed_at": now.isoformat(), "demo":bundle.demo, "counts": counts, "findings": findings, "coverage": {"resources":len(bundle.resources), "supported_controls":len(CATALOG), "evaluated_checks":len(findings), "warnings":bundle.warnings}, "scope_note":"Checks apply to selected resources under a private-backend baseline. MET confirms the stated check within collected evidence, not complete security. Collector identity is trusted; observations are not independently attested."}

def compare(current, previous):
    old = {(f["id"], f["resource_id"]): f for f in (previous or {}).get("findings", [])}
    changes = []
    seen = set()
    for f in current["findings"]:
        key = (f["id"], f["resource_id"]); seen.add(key)
        before = old.get(key)
        if before is None or before["status"] != f["status"]:
            changes.append({"control":f["id"], "resource":f["resource_name"], "before":before["status"] if before else "new", "after":f["status"]})
    for key, f in old.items():
        if key not in seen:
            changes.append({"control":f["id"], "resource":f["resource_name"], "before":f["status"], "after":"not_observed"})
    return changes
