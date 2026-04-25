# Email and SMS Channel Status

Last updated: 2026-04-25

## Where We Are

The inbound communication layer is now working end to end for both email and SMS at a basic operational level.

Email is in the stronger state:
- inbound Resend webhooks are processed successfully
- enrichment runs on inbound email
- HubSpot write-back happens through the MCP-first client path
- confidence-aware reply logic is wired into the live inbound flow
- replies are now sent as actual threaded email replies instead of fresh cold-style messages
- duplicate inbound webhook deliveries are deduplicated by `message_id`
- outbound replies use an idempotency key to reduce duplicate sends

SMS is now usable, but still lighter than email:
- inbound SMS webhook parsing works
- `STOP`, `HELP`, `UNSUBSCRIBE`, and `START` flows work
- inbound SMS writes back to HubSpot
- inbound SMS now sends a short human reply for normal hiring questions
- duplicate inbound SMS deliveries are deduplicated by `message_id`
- outbound warm-lead SMS remains available as a separate path

## What We Changed

### Email

We fixed the inbound email path so it behaves like a reply workflow instead of a cold outbound workflow.

Implemented:
- confidence-aware reply generation from the live inbound path
- end-to-end wiring from webhook -> enrichment -> HubSpot -> reply send
- reply subject normalization with `Re:`
- Resend threading headers:
  - `In-Reply-To`
  - `References`
- friendlier inbound reply copy that reacts to the actual message content
- dedupe for repeated Resend inbound events
- idempotency key on outbound reply sends

Behavior before:
- replies sounded like generic outbound templates
- replies were effectively sent as new emails
- duplicate inbound webhook attempts could produce repeated sends

Behavior now:
- a message like `hello can i get python developers from you guys`
  gets a reply shaped like a human follow-up, not a generic prospecting email

### SMS

We cleaned up the SMS path so it no longer feels like a dead-end webhook.

Implemented:
- inbound SMS reply generation for basic hiring inquiries
- intent-sensitive SMS responses for:
  - general hiring questions
  - scheduling intent
  - pricing/rate questions
- duplicate SMS webhook suppression by `message_id`

Behavior before:
- inbound SMS mainly wrote to HubSpot and stopped

Behavior now:
- inbound SMS can answer with a short, human, qualification-oriented reply

## Current Quality Level

### Email

Good enough for realistic iterative testing:
- threaded
- reasonably human
- operationally stable

Still not polished enough for high-quality production sales communication.

### SMS

Good enough for webhook and conversational-path testing:
- compliance controls work
- normal inbound hiring questions get an answer
- retries are less likely to echo duplicate replies

Still simpler than the email channel.

## What Is Left for Polish

### Email Polish

- make tone warmer and less checklist-heavy
- vary replies by intent:
  - availability
  - pricing
  - speed to hire
  - scheduling
  - role clarification
- carry more multi-turn context across repeated replies in the same thread
- improve reply specificity when enrichment confidence is low but the user intent is clear
- add better duplicate-event observability in logs and traces
- tighten subject handling for awkward or noisy inbound subjects

### SMS Polish

- make SMS replies shorter and more naturally conversational
- vary SMS responses more by intent and stage
- support better multi-turn SMS follow-up instead of single-turn qualification prompts
- distinguish between inbound prospect questions and scheduling nudges more cleanly
- add stronger routing controls for when SMS should reply immediately vs only log
- improve sink/live visibility in SMS logs and traces

### Cross-Channel Polish

- unify tone between email and SMS
- maintain shared context across channels so email and SMS do not feel like separate agents
- track previous asked/answered qualification fields
- avoid repeating the same request for role count, seniority, timezone overlap, and start date
- add per-channel dedupe metrics and dashboards
- improve long-running conversation memory and next-best-action selection

## Recommended Next Round

1. Add intent classification for inbound email and SMS replies.
2. Make both channels use the same conversation state.
3. Improve response variation so repeated conversations do not feel templated.
4. Add stronger multi-turn follow-up behavior for pricing, availability, and scheduling.

## Verification Snapshot

Recent verification completed:
- `uv run pytest tests/test_resend_email.py tests/test_route_errors.py tests/test_workflow_tracing.py -q`
- `uv run pytest tests/test_workflow_tracing.py tests/test_sms_controls.py -q`
- `uv run ruff check agent/integrations/resend_email.py agent/api/routes/webhooks.py agent/workflows/lead_orchestrator.py tests/test_resend_email.py tests/test_route_errors.py tests/test_workflow_tracing.py tests/test_sms_controls.py`

At the time of writing, the targeted email and SMS channel tests were passing.
