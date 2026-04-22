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
4. Start the API with `uv run uvicorn app.main:app --reload`.

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
