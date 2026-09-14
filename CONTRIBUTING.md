# Contributing

## Getting set up

```bash
git clone https://github.com/Jigar-CS/bob-ai-hackathon-ABC.git
cd bob-ai-hackathon-ABC

python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
make check                         # confirm a clean baseline
```

## Before opening a pull request

```bash
make check        # ruff check, ruff format --check, mypy, pytest
make test-cov     # confirm coverage has not regressed
```

Without `make`:

```bash
ruff check . && ruff format --check . && mypy && pytest --cov
```

CI runs the same checks on Python 3.10 through 3.13, plus an HTTP smoke test and a
Docker image build. A red CI run will not be merged.

## Where code belongs

| Layer | Path | Rule |
|---|---|---|
| Planning logic | `src/portpulse/domain/` | No web framework imports. Raise `portpulse.errors` exceptions, never `HTTPException`. |
| HTTP routes | `src/portpulse/api/` | Thin. Validate, delegate to the domain, translate errors to status codes. |
| Data access | `src/portpulse/datasets.py` | The only place that touches storage. |
| Third-party calls | `src/portpulse/integrations/` | Own the retry, timeout and error-taxonomy behaviour for that service. |
| Configuration | `src/portpulse/config.py` | New tunables go here, not as literals in a module. |
| Contracts | `src/portpulse/schemas.py` | Request and response models; keep them in step with what the domain emits. |

## Conventions

- **Configuration over constants.** Anything an operator might want to change belongs
  in `config.py` with a documented default and an entry in `.env.example`.
- **Type hints everywhere.** `mypy` runs with `disallow_untyped_defs` on `src/` and
  `scripts/`.
- **Docstrings explain *why*.** The reader can see what the code does; record the
  reasoning, trade-offs and non-obvious constraints.
- **Line length 100.** Enforced by Ruff; `ruff format` handles it.
- **No new runtime dependency** without a note in the pull request explaining why an
  existing one will not do. Pin exact versions in both `pyproject.toml` and
  `requirements.txt`.

## Testing rules

- Tests must not make network calls. `tests/conftest.py` blanks watsonx credentials;
  inject a fake client instead (see `FakeWatsonx` in `tests/domain/test_routing.py`).
- Tests must not read the shipped datasets. Use the `data_dir` fixture, which writes a
  known dataset to a temporary directory.
- Tests must not leak state. Use `reset_settings_cache()` and `reset_client_cache()`
  when mutating the environment; the autouse fixture already does this per test.
- Assert on behaviour rather than log output or internal call order.

## Adding an endpoint

1. Define request and response models in `schemas.py`.
2. Add the route to the relevant module in `api/`, or a new module registered in
   `api/__init__.py`.
3. Put any real logic in `domain/`, not the route handler.
4. Guard state-changing endpoints with `dependencies=[Depends(require_api_key)]`.
5. Add tests under `tests/api/`.
6. Update `docs/api.md` and the endpoint table in `README.md`.

## Changing the data contract

Column names and the timestamp format live in `src/portpulse/constants.py`. Change
them there and the API, the domain layer and the sample-data generator stay in step.
Also update the sample CSVs, `docs/setup-guide.md` and the dashboard if the change is
user-visible.

## Commits and pull requests

- Present-tense, imperative subject lines: `Add rolling-window congestion forecast`.
- One logical change per pull request.
- Fill in the pull request template: what changed, how it was verified, and anything
  reviewers should look at closely.
