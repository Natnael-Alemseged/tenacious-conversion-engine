# Outbound E2E Checklist

Use this as a requirement-aligned pass/fail checklist for the Tenacious outbound flow. It is grouped into setup, core outbound behavior, reply-to-booking continuity, and Act V evidenceability.

## Setup

- [ ] `OUTBOUND_ENABLED=false` and sink email/phone are configured.
- [ ] `LAYOFFS_FYI_PATH` points to `./data/layoffs_fyi.csv`.
- [ ] `BENCH_SUMMARY_PATH` points to `./tenacious_sales_data/seed/bench_summary.json`.
- [ ] Resend, HubSpot, Cal.com, and Langfuse credentials are present for the environment being tested.
- [ ] The prospect is synthetic and all outbound is routed to the sink only.

## 1. Enrichment Readiness

- [ ] Crunchbase firmographics resolve for the target company.
- [ ] Funding event is detected if present.
- [ ] Layoff event is detected from the CSV if present.
- [ ] Leadership-change signal is detected if present.
- [ ] Job-post signal is present and open-role count is populated.
- [ ] AI maturity score is generated with justification.
- [ ] Hiring-signal brief is produced and saved in the expected schema.
- [ ] Bench-to-brief match is computed.
- [ ] Honesty flags are present when signals are weak or conflicting.

## 2. ICP Classification

- [ ] Prospect lands in the expected ICP segment.
- [ ] Layoff overrides funding when both exist.
- [ ] Leadership-transition cases route to Segment 3.
- [ ] Segment 4 is not used for low AI-readiness prospects.
- [ ] Zero-open-role cases do not get growth-language assumptions.
- [ ] Low-confidence signals cause hedged/exploratory phrasing, not direct assertions.

## 3. Bench Safety

- [ ] Outbound send is blocked if `bench_to_brief_gate_passed=false`.
- [ ] Off-bench capability requests do not produce availability promises.
- [ ] On-bench prospects can proceed to outbound send.
- [ ] Bench gaps are visible in the brief or logs.

## 4. Outbound Email Content

- [ ] Subject line matches the highest-confidence signal.
- [ ] Subject line stays within the length limit.
- [ ] Body uses one grounded public fact.
- [ ] Body does not claim facts unsupported by the brief.
- [ ] Tone matches `tenacious_sales_data/seed/email_sequences/cold.md`.
- [ ] No banned filler like "just circling back" or fake urgency.
- [ ] No service-menu dumping.
- [ ] No off-bench commitment.
- [ ] Pricing stays within allowed public-tier guidance and routes deeper pricing to a human.
- [ ] Email metadata is marked `draft`.

## 5. Outbound Routing and Safety

- [ ] Email routes to sink when outbound is disabled.
- [ ] Logs capture `intended_to` and `routed_to`.
- [ ] Outbound mode is recorded as `sink`.
- [ ] If sink is missing, the send fails loudly.
- [ ] No real recipient is contacted during challenge-week testing.

## 6. Send, Trace, and CRM

- [ ] Resend send succeeds in sink mode.
- [ ] Langfuse trace is created for outbound send.
- [ ] Trace contains segment, AI score, phrasing, and routing audit.
- [ ] HubSpot contact is created or updated.
- [ ] HubSpot stores `lead_source=outbound_email`.
- [ ] HubSpot stores outbound timestamps and sink/live metadata.
- [ ] HubSpot record carries `draft` / Tenacious-safe metadata.

## 7. Reply Handoff

- [ ] A reply to the outbound email is correctly linked to the same thread.
- [ ] The system handles the reply as a reply, not as a new cold thread.
- [ ] Enrichment context is preserved into reply handling.
- [ ] The response reflects actual reply intent.
- [ ] Reply handling updates HubSpot again.
- [ ] Reply handling writes trace events cleanly.

## 8. Booking Path

- [ ] Positive reply with booking intent triggers Cal.com flow.
- [ ] Booking succeeds with a real booking UID.
- [ ] Booking metadata is written back to HubSpot.
- [ ] Booking state is reflected in traces/logs.
- [ ] Booking failure is surfaced clearly and not silently swallowed.

## 9. Sequence Controls

- [ ] Sequence stops immediately on prospect reply.
- [ ] Sequence stops on opt-out.
- [ ] Sequence stops on bounce/invalid address.
- [ ] Sequence stops if re-enrichment later disqualifies the prospect.
- [ ] No fourth touch is sent inside 30 days.

## 10. Segment-Specific Checks

- [ ] Segment 1 email references funding/growth carefully.
- [ ] Segment 2 email treats restructure neutrally, not aggressively.
- [ ] Segment 3 email references new leadership appropriately.
- [ ] Segment 4 email uses capability-gap language only when readiness supports it.
- [ ] Low-confidence cases ask rather than assert.

## 11. Act V Evidenceability for Outbound

- [ ] Outbound traces contain stable IDs for contact/thread/message.
- [ ] Each outbound event is attributable to a lead/contact.
- [ ] Replies can be linked back to the correct outbound thread.
- [ ] Sink-mode sends still produce usable trace artifacts.
- [ ] The run produces enough machine-readable data to compute:
- [ ] fraction of outbound using `competitive_gap` vs `generic`
- [ ] reply-rate delta between variants
- [ ] stalled-thread rate
- [ ] cost per qualified lead

## 12. Competitive-Gap Specific

- [ ] `competitor_gap_brief.json` is generated for the prospect.
- [ ] The brief is attached or persisted with the lead metadata.
- [ ] Outbound is tagged with `outbound_variant=competitive_gap` or `generic`.
- [ ] The message actually uses a research finding when tagged `competitive_gap`.
- [ ] Variant tagging is visible in traces.
- [ ] Variant-level reply outcomes are measurable.

## 13. Cross-Channel Scheduling

- [ ] If the lead moves from email to SMS for scheduling, the same thread/lead is preserved.
- [ ] Cross-channel routing does not duplicate the lead in HubSpot.
- [ ] Booking through SMS still counts toward the outbound-originated thread correctly.

## 14. Failure Cases To Intentionally Test

- [ ] Weak funding signal with low job-post count.
- [ ] Layoff + funding conflict.
- [ ] Off-bench requested stack.
- [ ] Missing sink config.
- [ ] Resend failure.
- [ ] HubSpot write-back failure.
- [ ] Cal.com booking response missing UID.
- [ ] Prospect opt-out after first outbound.
- [ ] Re-enrichment disqualifies the prospect between touches.

## Current Likely Repo Gaps To Watch Closely

- [ ] `competitor_gap_brief.json` path is fully implemented, not just schema-tested.
- [ ] Outbound variant tagging exists in traces.
- [ ] Reply classification / autoresponder exclusion is explicit enough for Act V metrics.
- [ ] Root-level evidence artifacts for Act V can actually be produced from outbound runs.

## Minimum True Outbound E2E Pass

- [ ] Synthetic prospect enriched.
- [ ] Correct segment chosen.
- [ ] Bench gate passes.
- [ ] Outbound email sent to sink.
- [ ] HubSpot updated.
- [ ] Reply received and handled.
- [ ] Booking created.
- [ ] Trace, CRM, and booking records all line up for the same lead.
