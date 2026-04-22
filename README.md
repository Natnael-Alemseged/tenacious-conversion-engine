# Conversion Engine

FastAPI backend scaffold for the Tenacious sales-automation conversion engine challenge.

## What This Repo Covers

- inbound email and SMS webhook entrypoints
- minimal SMS compliance controls for `STOP`, `HELP`, `UNSUBSCRIBE`, and `START`
- placeholder integrations for HubSpot, Cal.com, and Langfuse
- enrichment stubs for Crunchbase, layoffs, job-post signals, and AI maturity scoring
- a sibling-repo evaluation wrapper for `tau2-bench`

## Architecture

```text
conversion-engine/
├── app/
│   ├── api/routes/         # FastAPI endpoints
│   ├── core/               # Settings and app config
│   ├── enrichment/         # Signal-enrichment pipeline stubs
│   ├── integrations/       # External service clients
│   ├── models/             # Webhook payload models
│   ├── storage/            # Local state scaffolding
│   └── workflows/          # Orchestration layer
├── eval/                   # tau2-bench wrapper scripts
├── probes/                 # Adversarial probe notes
├── tests/                  # FastAPI and webhook tests
└── render.yaml             # Render deployment config
```

## Project Boundaries

- Keep `tau2-bench` in a separate sibling folder. This repo wraps it; it does not vendor it.
- Keep Cal.com separate as booking infrastructure. Point this app at its base URL through env vars.
- Do not commit live secrets. Use `.env` locally and configure real secrets in Render or GitHub.

## Local Setup

1. Create a virtualenv and install dependencies with `uv sync --group dev`.
2. Copy `.env.example` to `.env`.
3. Fill in your API keys and local paths.
4. Install git hooks (required once per clone):
   ```bash
   uv run pre-commit install && uv run pre-commit install --hook-type commit-msg
   ```
5. Start the API with `uv run uvicorn app.main:app --reload`.

## Development Workflow

### Linting & formatting

Runs automatically on `git commit`. To run manually:

```bash
uv run ruff check --fix .
uv run ruff format .
```

### Commit message format

Commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description
```

Valid types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `ci`, `perf`, `build`, `style`, `revert`

```bash
# Good
git commit -m "feat(enrichment): add crunchbase funding signal"
git commit -m "fix(integrations): handle hubspot 429 retries"
git commit -m "chore: bump ruff to 0.15"

# Rejected — wrong format
git commit -m "fix auth bug"

# Rejected — bundles two changes
git commit -m "fix: update auth and add new endpoint"
```

### One module per commit

Commits that touch files from more than one `app/` subdirectory are rejected. Keep each commit scoped to a single module (e.g. `app/integrations` or `app/enrichment`). Files in `tests/`, `eval/`, `scripts/`, and root config are neutral and may be included alongside any module.

To unstage a file: `git restore --staged <file>`

To bypass all hooks when genuinely needed: `git commit --no-verify`

## Environment

Key env vars in `.env.example`:

- `OPENROUTER_API_KEY`
- `HUBSPOT_API_KEY`
- `CALCOM_API_KEY`
- `CALCOM_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `RESEND_API_KEY`
- `AFRICASTALKING_API_KEY`

If Cal.com is tunneled through ngrok or Cloudflare Tunnel, keep `CALCOM_BASE_URL` aligned with the public URL configured in the Cal.com project.

## Testing

Run:

```bash
uv sync --group dev
uv run pytest
```

## Evaluation

`eval/run_baseline.py` assumes this folder layout:

```text
backend/
├── conversion-engine/
└── tau2-bench/
```

Example:

```bash
python eval/run_baseline.py --domain retail --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-tasks 5
```

## Deployment

`render.yaml` contains a starter Render service definition for the FastAPI app.

## Status

This is a scaffold, not a full production implementation yet. The external integrations and enrichment steps still use placeholders and need to be wired to real services.
