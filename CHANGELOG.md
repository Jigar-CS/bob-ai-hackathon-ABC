# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-09-13

First production-ready release. The hackathon prototype was restructured into an
installable package with a versioned API, typed configuration and a real CI pipeline.

### Added

- Installable `portpulse` package with `pyproject.toml`, a `src/` layout and a
  `portpulse` console script.
- Typed configuration (`config.py`) across the `PORTPULSE_*` and `WATSONX_*`
  environment namespaces, replacing hardcoded constants.
- Versioned API under `/api/v1`, plus an unversioned `/health` probe that reports
  `503` when datasets are unreadable.
- Optional API key authentication (`X-API-Key`) on write endpoints, with startup
  refusal in production when unconfigured.
- Request correlation IDs (`X-Request-ID`) and access logging middleware, with
  optional JSON log output.
- Pydantic request and response models for every endpoint, giving OpenAPI a real
  contract in both directions.
- Alternate-port catalogue moved from source code to
  `src/portpulse/data/alternate_ports.json`.
- `scripts/generate_sample_data.py` with argparse options for size, seed and output.
- Test suite of 139 tests covering configuration, CSV handling, all three engines,
  the watsonx client and every endpoint. Coverage gate at 70%; actual coverage 93%.
- CI pipeline: Ruff, mypy, tests on Python 3.10–3.13, an HTTP smoke test and a
  Docker image build with a container health check.
- `.dockerignore`, `LICENSE`, `CHANGELOG.md`, `Makefile`, Dependabot config and a
  pull request template.
- `docs/api.md` endpoint reference.

### Changed

- `src/port-app/` became `src/portpulse/`, an importable package. The five
  `sys.path.insert` shims in the test files are gone.
- `main.py` split into an application factory (`app.py`), three route modules and a
  domain package that imports no web framework.
- The two duplicated upload handlers merged into `POST /api/v1/uploads/{dataset}`,
  and the two template handlers into `GET /api/v1/templates/{dataset}`.
- Congestion windows are now rolling 24-hour buckets from the earliest ETA, capped
  at the planning horizon, rather than calendar-day buckets of arbitrary span.
- The watsonx client is a class with instance-scoped state instead of module
  globals, so tests are isolated and the client is injectable.
- Retry backoff now includes jitter; timeouts, retry counts and the auth cooldown
  are configurable.
- CORS defaults to a localhost allowlist instead of `*`, and wildcards are rejected
  in production.
- Upload size limits are enforced while streaming rather than after buffering the
  whole body.
- All dependencies pinned to exact versions, with runtime and development sets split.
- Dockerfile rebuilt: virtualenv-based multi-stage build, non-root user, no
  development dependencies in the runtime image, configurable port.
- Documentation consolidated into `README.md` plus four focused files in `docs/`.

### Fixed

- `.gitignore` no longer excludes the packaged sample datasets, which previously
  made a fresh clone and any CI run fail with `503`. Also removed a broken
  `Cargo.lock` pattern with an inline comment.
- Placeholder credentials (`your_api_key_here` and similar) are treated as unset.
  Previously they passed the presence check and triggered three failed IAM requests
  per vessel before falling back.
- Non-UTF-8 uploads return `400` instead of surfacing a `UnicodeDecodeError` as `500`.
- Dead code removed: the unused `VesselItem` / `BerthItem` models, an unreachable
  branch in the exception handler, and an unused import.
- `POST /api/v1/plan/custom` validates its input. It previously accepted arbitrary
  `List[dict]` with no field checks.
- watsonx error messages no longer embed upstream response bodies, which could carry
  request detail into user-facing errors.
- `crane_count` and `priority` are emitted as integers or `null` rather than the
  string `"N/A"`.
- The sample-data generator creates its output directory and no longer depends on
  the current working directory.
- `submission.yaml` `track` now matches the values the validation workflow accepts.

### Removed

- `abc.readme` and `abc.readme.md` — byte-identical duplicates of README content.
- `PROJECT_CONTENT_BRIEF.md` and `ai-routing-plan.md` — agent scaffolding with
  unfilled placeholders and stale line references.
- `docs/template-guide.md` — unmodified hackathon template instructions.
- `src/.env` and `src/port-app/.env` — placeholder credential files.
- `src/.env.example` — duplicated the real template and carried unused
  `DATABASE_URL` and `SLACK_WEBHOOK_URL` keys.
- `src/README.md` — folded into the root README.
