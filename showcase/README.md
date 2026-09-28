# GuardGap showcase

This directory is a complete end-to-end demonstration of GuardGap's collector,
ingestion API, evidence model, control engine, history, architecture explorer,
and audit trail.

Start with one of these reports:

- [Illustrated Markdown report](SHOWCASE_REPORT.md)
- [Standalone HTML report](SHOWCASE_REPORT.html)
- [Shareable PDF report](GuardGap-Showcase-Report.pdf)

The run compares a deliberately vulnerable support-agent deployment with a
remediated successor:

| Result | Met | Gaps | Unknown |
| --- | ---: | ---: | ---: |
| Before | 1 | 7 | 1 |
| After | 9 | 0 | 0 |

The GCP API payloads are synthetic and do not represent a real cloud account.
Everything after those inputs is exercised through the real implementation:
Python source scanning, GCP normalization, JUnit parsing, scoped HTTP ingestion,
persistence, assessment, comparison, dashboard rendering, and audit logging.

## Artifact map

- `01`–`06-*.png`: authenticated dashboard screenshots.
- `evidence-*.json`: normalized bundles accepted by the ingestion API.
- `gcp-*.json`: synthetic read-only cloud observations used by the normalizer.
- `authorization-*.xml`: named failed and passing JUnit evidence.
- `assessment-*.md`: standalone CLI reports.
- `showcase-summary.json`: persisted report/snapshot IDs, counts, and transitions.
- `SHA256SUMS.txt`: fingerprints for the source evidence artifacts.

Use the built-in dashboard demo for a quick local walkthrough. To reproduce the
full integration against a deployment, follow the root README and use
`examples/github/collect.yml` from the application repository's deployment job.
