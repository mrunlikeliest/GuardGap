# Roadmap

GuardGap's roadmap follows one principle: broaden evidence coverage without
weakening the meaning of a result. Items here describe direction and are not a
release commitment.

## Near term

- Formal database migrations and documented upgrade/rollback procedures.
- Configurable retention for evidence, reports, audit records, and tokens.
- More GCP observations: Cloud Run traffic splits, Secret Manager references,
  VPC connectivity, organization-policy evaluation, and richer IAM conditions.
- GitHub Checks integration alongside the existing SARIF and workflow artifacts.
- More example policy profiles for private APIs, batch services, and public edges.
- Accessibility, responsive-layout, and browser automation coverage for the UI.

## Expansion

- AWS, Azure, and Kubernetes adapters using the existing versioned evidence model.
- Multi-repository aggregation into one application/environment posture.
- Approved exceptions with owners, expiry, reason, and immutable audit history.
- Pluggable control packs and a documented collector SDK.
- Signed releases and stronger build/evidence provenance verification.

## Production operations

- SSO and role-based access control with per-user audit identity.
- Supported multi-instance operation and background job coordination.
- Metrics, structured logs, backup verification, and operational health dashboards.
- Stable API lifecycle and schema compatibility guarantees.

Proposals are welcome through GitHub issues. New work should include its trust
boundary, required evidence, failure behavior, and validation plan.
