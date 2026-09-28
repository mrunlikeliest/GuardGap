## Problem and resulting behavior

Describe the concrete trigger and the behavior before and after this change.

## Evidence boundary

For collector or control changes, state what the result establishes, which inputs
are required, and when the result remains unknown.

## Validation

- [ ] `python -m pytest -q`
- [ ] Docker image builds, when runtime packaging changed
- [ ] Documentation and changelog updated, when user-facing behavior changed
- [ ] No credentials, secret payloads, raw environment values, or private cloud dumps added
