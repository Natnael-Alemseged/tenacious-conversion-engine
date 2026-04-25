## Booking link parity examples (rubric evidence)

### Email reply path
- **Trigger**: inbound email contains “schedule / book / cal.com …”
- **Behavior**: reply email includes `https://cal.com/<CALCOM_USERNAME>` when configured.
- **Implementation**: `agent/workflows/lead_orchestrator.py` (`_build_inbound_email_reply`)

### SMS warm-lead path
- **Trigger**: inbound SMS contains “schedule / book / cal.com …”
- **Behavior**: warm-lead SMS reply includes `https://cal.com/<CALCOM_USERNAME>` when configured.
- **Implementation**: `agent/workflows/lead_orchestrator.py` (`_build_inbound_sms_reply`)

