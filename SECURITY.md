# Security policy

## Supported version

GuardGap is currently an alpha-stage `0.1.x` project. Security fixes target the
latest revision on the default branch. There is no long-term support policy yet.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** private-reporting feature for this
repository. Include affected versions, reproduction steps, impact, and any
suggested mitigation. Do not include credentials, customer evidence, or exploit
details in a public issue.

If private vulnerability reporting is unavailable, open a minimal public issue
asking the maintainers for a private contact channel without describing the
vulnerability itself.

The project will acknowledge a report, validate its impact, coordinate a fix,
and publish release notes appropriate to the risk. Response times are best-effort
while the project is in alpha.

## Deployment security

GuardGap stores architecture metadata and findings that may be sensitive. Review
the complete [security boundary and evidence semantics](docs/SECURITY.md) before
deployment. Production operators should use HTTPS, PostgreSQL backups, restricted
dashboard access, protected CI runners, narrowly scoped cloud permissions, and
short-lived or regularly rotated collector tokens.
