# E2E Verification and Code Improvements

This note captures two things:

1. Code-level improvements that would make the outbound/inbound flow genuinely end-to-end solid.
2. User-style verification steps to test the intended operator flow, not just fixtures or unit tests.

## Code-Level Improvements

The highest-value improvements to make next are:

### 1. Build one real golden-path runner

The current "golden path" is artifact playback. Add a script that actually:

- runs enrichment for a synthetic lead
- generates `hiring_signal_brief.json`
- generates `competitor_gap_brief.json`
- sends sink-routed outbound email
- simulates inbound reply
- triggers booking
- verifies HubSpot fields
- writes one final summary artifact

### 2. Make channel handoff a real state model

`channel_handoff.py` is useful, but still shallow. Add:

- explicit contact/thread state struct
- last channel
- replied by email?
- SMS suppressed?
- booking requested?
- booking created?
- next-action resolver

### 3. Strengthen the live competitor-gap path

The current competitor-gap flow still falls back to sample data when sectors are sparse.

Improve by:

- making live peer selection the default success path
- clearly labeling fallback in trace/artifact output
- blocking outbound "research-backed" claims when only fallback/sample data exists

### 4. Make outbound measurement first-class

For Act V and for operational confidence:

- stable `thread_id`
- stable `lead_id`
- outbound event log
- reply classification log
- booking event log
- one thread summary artifact per lead

### 5. Tighten job-source implementations

The source modules are still mostly wrappers around generic scraping.

Improve by:

- source-specific selectors/parsers
- source-specific tests
- clearer robots/allowlist behavior
- deterministic fallback behavior

### 6. Add one real integration test per core path

Not just unit tests. Add controlled integration tests for:

- outbound email send to sink
- inbound email reply handling
- SMS warm-lead scheduling
- booking writeback
- competitor-gap-gated outbound phrasing

## User-Style Verification

Test the app in the intended flow, not just by reading artifacts.

## Flow 1: Outbound Email -> Reply -> Booking -> CRM

This is the main one.

1. Pick one synthetic prospect with:
   - clear company name
   - careers URL
   - known signal mix
2. Run enrichment and inspect:
   - segment
   - AI maturity
   - layoffs/funding/leadership/job signals
   - bench gate
3. Trigger outbound email in sink mode.
4. Verify:
   - email was generated
   - routed to sink, not live address
   - HubSpot contact got created/updated
   - trace/log entry exists
   - outbound metadata says `draft`
5. Simulate a reply email like:
   - `Yes, open to a quick call next week`
6. Verify:
   - same thread is used
   - reply is handled as reply, not new cold lead
   - HubSpot updated again
7. Simulate booking intent.
8. Verify:
   - Cal.com booking is created
   - booking UID exists
   - HubSpot reflects booking
   - final trace shows booking created

## Flow 2: Outbound Email -> Warm-Lead SMS Scheduling

This checks channel handoff.

1. Send outbound email first.
2. Simulate positive email reply.
3. Then simulate SMS inbound like:
   - `Can we do Friday morning?`
4. Verify:
   - SMS response includes booking link if configured
   - SMS only works because the lead is warm
   - same contact/thread is preserved in CRM
   - booking via SMS still ties back to the original outbound lead

## Flow 3: Safety / Failure Flow

This is just as important.

Test these as an operator:

- outbound disabled and no sink configured -> should fail loudly
- off-bench prospect -> should not send a capacity-committing message
- weak signal -> should ask, not assert
- opt-out -> should stop sequence
- bounce -> contact should be marked appropriately
- booking error -> visible failure, not silent drop

## What To Inspect While Testing

Check these every time:

- generated email content
- sink/live routing behavior
- HubSpot contact fields
- Langfuse trace/log
- outbound events log
- reply classification log
- booking result
- final thread continuity

## Best Practical Acceptance Test

Before calling the system done, require:

- one synthetic lead
- one real enrichment run
- one real outbound sink send
- one real simulated reply
- one real booking creation
- real HubSpot updates
- one traceable thread from start to finish

Run it twice:

- once for a normal Segment 1 or 2 lead
- once for a weak-signal / exploratory case

If both runs work cleanly, confidence in the E2E claim goes up substantially.
