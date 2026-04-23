# Outbound Safety + Auditability Spec

**Goal:** Ensure the Conversion Engine cannot send real outbound messages by default during the Tenacious challenge week, and that any outbound content is explicitly marked as draft and auditable end-to-end.

**Scope:** Outbound email (Resend) and outbound SMS (Africa's Talking) from `agent/workflows/lead_orchestrator.py`, plus associated tracing and CRM write-back metadata.

---

## Requirements (from Tenacious brief)

- **Kill-switch:** A configuration flag that, when unset, routes **all outbound to a staff sink**. Default must be unset.
- **Sink by default:** Outbound must route to sink unless explicitly enabled.
- **Draft marking:** Any Tenacious-branded outbound content (emails/SMS) must be marked **draft** in metadata.
- **Auditability:** Outbound payloads and/or stored CRM fields must include metadata so routing and draft status are explicit and auditable.

---

## Design

### Configuration

Add these settings in `agent/core/config.py`:

- `outbound_enabled: bool = False`
- `outbound_sink_email: str = ""`
- `outbound_sink_phone: str = ""`

Defaults keep the system in **sink mode** unless `OUTBOUND_ENABLED=true`.

### Routing behavior

In `LeadOrchestrator.send_outbound_email` and `LeadOrchestrator.send_warm_lead_sms`:

- Compute `intended_to` (original user-supplied target).
- Compute `routed_to`:
  - If `settings.outbound_enabled` is `True`, `routed_to = intended_to`.
  - Else, `routed_to = settings.outbound_sink_*` (sink must be configured; if missing, fail closed with a clear error).
- Always emit an **outbound audit metadata** payload:
  - `outbound_mode`: `"live"` or `"sink"`
  - `draft`: `true`
  - `intended_to`: original recipient
  - `routed_to`: actual recipient used
  - `reason`: `"outbound_disabled"`

### Metadata propagation

- **Langfuse traces/spans:** Attach outbound audit metadata to the outbound send span(s).
- **Resend payload tags:** Add tags (or metadata if available) so draft + sink mode is visible at provider level.
- **HubSpot:** Persist minimal, explicit outbound audit markers in CRM properties (string fields), without assuming new HubSpot properties exist.
  - At minimum, write:
    - `last_outbound_mode` (`"sink"`/`"live"`)
    - `last_outbound_draft` (`"true"`)
    - `last_outbound_intended_to` (truncated)
    - `last_outbound_routed_to` (truncated)

---

## Non-goals

- Implement voice channel delivery.
- Create new HubSpot custom properties via API (out of scope; deployment-specific).

---

## Verification

- Unit tests cover:
  - sink routing default (outbound disabled routes to sink, not intended)
  - live routing when explicitly enabled
  - draft markers and audit metadata present in traces/CRM writes

