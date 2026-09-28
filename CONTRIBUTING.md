# Contributing to GuardGap

GuardGap welcomes bug fixes, documentation, new evidence adapters, and narrowly
defined controls. The project favors explicit evidence boundaries over broad
claims. A control must say exactly what it establishes and return `unknown` when
its required evidence is missing, stale, incomplete, or planned-only.

## Development setup

GuardGap requires Python 3.11 or newer and is tested on Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m pip install -e '.[dev]'
python -m pytest -q
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`. Docker users can validate the production image
with `docker build -t guardgap:dev .`.

## Making a change

1. Open an issue for substantial behavior or schema changes so scope and
   evidence semantics can be discussed first.
2. Keep collectors read-only and normalize only fields needed by documented
   checks. Never collect secret payloads or raw environment values.
3. Add meaningful tests for control predicates, schema boundaries, parsers, and
   authentication behavior. Missing evidence must never become an implicit pass.
4. Update the README, integration documentation, and changelog when user-facing
   behavior changes.
5. Run `python -m pytest -q` and build the Docker image before opening a pull
   request.

## Adding a control

A control contribution should include:

- A stable control ID, title, severity, evidence kind, and implementation guidance.
- A deterministic predicate with explicit `met`, `gap`, and `unknown` behavior.
- Tests for positive, negative, missing, stale, and planned evidence where relevant.
- Documentation of what the result establishes and what remains outside its scope.

Avoid controls that infer a pass from a missing resource, collection error, name
pattern, or intended Terraform configuration alone.

## Adding a collector

Collectors run with the caller's identity and must use fixed read-only commands
or APIs. Validate all resource identifiers, bound input and output sizes, retain
source timestamps, and emit the versioned normalized model in
`guardgap/models.py`. Keep vendor-specific raw payloads out of the server.

## Pull requests

Keep pull requests focused. Describe the concrete behavior change, its evidence
boundary, and the validation performed. By contributing, you agree that your
work is licensed under the repository's MIT License.

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security issues
through the private process in [SECURITY.md](SECURITY.md).
