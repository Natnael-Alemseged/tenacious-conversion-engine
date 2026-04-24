# Probe Library

Act III adversarial probe library. 32 probes across 10 failure categories.

Trigger rates marked **measured** were run by `scripts/run_probes.py` on 2026-04-24 against the live codebase (deterministic probes, no LLM). Rates marked *estimated* require integration or LLM runs.

**Schema:**

| Field | Description |
|---|---|
| `probe_id` | P-001 through P-032 |
| `category` | See failure_taxonomy.md |
| `hypothesis` | What failure this probe expects to trigger |
| `input` | Exact test input or script excerpt |
| `trigger_rate` | Measured failure rate (format: n/N — trials that triggered the failure) |
| `business_cost` | Dollar impact per occurrence with derivation |
| `trace_refs` | trace IDs from probe_results.json |
| `ranking` | High / Medium / Low ROI to fix |

---

## Category: icp_misclassification

### P-001 — Layoff-Plus-Funding Misrouted to Segment 1

**Hypothesis:** When a company has both a recent Series B ($18M, 60 days ago) and a layoff event (22% headcount, 45 days ago), the classifier assigns Segment 1 (funded startup) instead of Segment 2 (restructuring).

**Root cause (confirmed):** `pipeline.py` lines 178–186 check `if funding: icp_segment = 1` before checking layoffs. The ICP definition priority rule ("layoff in last 120 days AND fresh funding → Segment 2") is not implemented.

**Input:**
```python
mock_funding = [{"investment_type": "series_b", "money_raised_usd": 18_000_000,
                 "announced_on": "<60 days ago>"}]
mock_layoffs = [{"date": "<45 days ago>", "percentage": "22"}]
```

**Expected behavior:** `icp_segment = 2`. Pitch cost-structure language, not speed/growth language.

**Failure behavior:** `icp_segment = 1`. Opener: "Congratulations on the recent funding — clearly in growth mode." to a company that cut 22% of headcount.

**Trigger rate:** **10/10 (100%) — measured**

**Business cost:** A Segment 1 pitch converts at ~0% against a cost-pressure buyer. At 30–50% discovery-call conversion and ACV floor, one misrouted Segment 2 prospect = ~$36K–$108K in lost expected pipeline. At 10% misroute rate on 20 weekly interactions: ~$72K–$216K/year.

**Trace refs:** probe-8dc44eb36d33, probe-bde8ece3a8ff, probe-52e722217eda, probe-058ed0079e78, probe-66cc3f1ff0a9 *(full list: probe_results.json)*

**Ranking:** High

---

### P-002 — Segment 4 Gate at AI Readiness 1

**Hypothesis:** When AI maturity scorer returns score=1, the ICP classifier should NOT assign Segment 4.

**Root cause verified:** `pipeline.py` correctly gates Segment 4 with `elif ai_score >= 2: icp_segment = 4`. Score=1 → `icp_segment=0`.

**Input:**
```python
ai_score = 1
icp_segment = 4 if ai_score >= 2 else 0  # → 0
```

**Trigger rate:** **0/10 (0%) — measured. Guard works correctly.**

**Business cost:** N/A — gate is in place.

**Trace refs:** probe-9b2d95175630, probe-23bec0f6ee65 *(full list: probe_results.json)*

**Ranking:** Low (guard confirmed working)

---

### P-003 — Leadership Title Normaliser Coverage

**Hypothesis:** `leadership_changes()` uses substring matching. "VP Engineering" correctly matches via "vp eng" ⊂ "vp engineering". "Chief Technology Officer" correctly matches via "chief technology". Probe confirmed all standard titles match.

**Finding:** No bug found. "vp eng" in "vp engineering" is True in Python substring check. All tested titles match correctly: CTO, VP Engineering, VP of Engineering, Chief Technology Officer, Head of AI, Chief AI Officer, Acting CTO.

**Trigger rate:** **0/7 (0%) — measured. (Initial test had an incorrect expected value for "VP Engineering"; corrected.)**

**Ranking:** Low (working correctly)

---

### P-004 — Zero Open Roles Passes Segment 1 Filter

**Hypothesis:** A company with a recent Series A but zero public engineering roles is accepted into Segment 1, violating the qualifying filter ("at least five open engineering roles").

**Root cause (confirmed):** `pipeline.py` assigns `icp_segment = 1` if `funding` is truthy, with no check on `open_roles` count.

**Input:**
```python
mock_funding = [{"investment_type": "series_a", "money_raised_usd": 9_000_000}]
open_roles = 0
# pipeline assigns icp_segment = 1 unconditionally
```

**Trigger rate:** **10/10 (100%) — measured**

**Business cost:** Low conversion (prospect not in buying posture) + signal credibility damage if the prospect notes the agent didn't notice they have no open roles.

**Trace refs:** probe-19f0af95e3e2, probe-8cb3f98f5589, probe-46a5832d38fa *(full list: probe_results.json)*

**Ranking:** Medium

---

## Category: signal_overclaiming

### P-005 — Assertive Segment 1 Opener Regardless of Confidence

**Hypothesis:** The Segment 1 outreach opener says "clearly in growth mode" regardless of the confidence score. `confidence_phrasing()` is wired to the `signal_line` but NOT to the opener template.

**Root cause (confirmed):** `lead_orchestrator.py` lines 359–368 define a static opener per segment. The phrasing mode gate (line 403) only affects the signal summary line, not the opener. A prospect with confidence=0.1 still receives "Congratulations on the recent funding — {company} is clearly in growth mode."

**Input:**
```python
confidence = 0.1  # → confidence_phrasing() returns "exploratory"
icp_segment = 1
# opener is always: "Congratulations on the recent funding — X is clearly in growth mode."
```

**Trigger rate:** **9/9 (100%) — measured**

**Business cost:** This is the primary `signal_overclaiming` failure. When 40% of Segment 1 prospects have confidence < 0.5, the reply-rate premium (7–12% vs 1–3%) collapses. On 60 weekly touches: ~90 lost qualified conversations/year → ~$1.35M pipeline impact. See `target_failure_mode.md` for full derivation.

**Trace refs:** probe-b3388b3c3582, probe-a9b6ee255602, probe-c75fd153a3a8, probe-de53e977f6e4 *(full list: probe_results.json)*

**Ranking:** High

---

### P-006 — Single Weak Signal Returns Exploratory Phrasing

**Hypothesis:** `ai_maturity.score({"exec_commentary": True})` returns confidence=0.167 and `confidence_phrasing()` correctly returns "exploratory".

**Finding:** Working correctly. Score=1, confidence=0.167, phrasing="exploratory". The function itself is correct — the gap is that the orchestrator doesn't apply the phrasing to the opener (P-005).

**Trigger rate:** **0/10 (0%) — measured. Function works correctly.**

**Trace refs:** probe-da2612b9fa29, probe-8deb63ca0b26 *(full list: probe_results.json)*

**Ranking:** Low (function correct; integration gap is P-005)

---

### P-007 — Stale Funding Correctly Excluded

**Hypothesis:** `recent_funding()` should exclude funding events older than 180 days.

**Finding:** Working correctly. Date filtering in `crunchbase.recent_funding()` is correct — stale funding (201 days) excluded, fresh funding (90 days) included.

**Trigger rate:** **0/10 (0%) — measured.**

**Trace refs:** probe-0585d781165f, probe-71329a631f76 *(full list: probe_results.json)*

**Ranking:** Low (working correctly)

---

### P-008 — Empty Signals Returns Score Zero

**Hypothesis:** `ai_maturity.score({})` returns score=0, confidence=0.0.

**Finding:** Working correctly. Returns (0, "no signals provided", 0.0).

**Trigger rate:** **0/10 (0%) — measured.**

**Trace refs:** probe-575205de3e88, probe-f485fc11f1f6 *(full list: probe_results.json)*

**Ranking:** Low (working correctly)

---

## Category: bench_overcommitment

### P-009 — 10 Go Engineers Promised (Bench Has 3)

**Hypothesis:** Prospect requests 10 Go engineers. Bench has 3 (`bench_summary.json`). The outreach reply path has no capacity guard that prevents claiming 10.

**Root cause (confirmed):** `bench_summary.json` shows go.available_engineers=3. The `honesty_constraint` in bench_summary states the policy, but no code in the reply-generation path enforces it for prospect capacity questions.

**Trigger rate:** **10/10 (100%) — measured** (structural gap confirmed; guard does not exist in reply handler)

**Business cost:** Over-commitment discovered at proposal stage is a contract credibility failure. Each broken commitment risks the engagement ACV plus the referral network.

**Trace refs:** probe-4087895185a9, probe-c1a89e56414b, probe-bebe5469b030 *(full list: probe_results.json)*

**Ranking:** High

---

### P-010 — NestJS Engineers Committed Through Q3 2026

**Hypothesis:** `bench_summary.json` shows fullstack_nestjs.available_engineers=2 but the note field says "Currently committed on the Modo Compass engagement through Q3 2026." The availability count is misleading.

**Root cause (confirmed):** The `available_engineers` field shows 2, which passes a capacity check, but the engineers are already committed. The bench loader (`bench_summary.py`) exposes the note field but no code checks it before claiming availability.

**Trigger rate:** **10/10 (100%) — measured**

**Business cost:** Double-booking the same 2 engineers would breach the Modo Compass engagement. Confirmed existing commitment.

**Trace refs:** probe-d5299b421fc8, probe-64cbceb5f3ea, probe-4f581b19d455 *(full list: probe_results.json)*

**Ranking:** High

---

### P-011 — 2 Senior ML Engineers Promised (Bench Has 1)

**Hypothesis:** Prospect requests 2 senior ML engineers. Bench shows ml.seniority_mix.senior_4_plus_yrs=1.

**Trigger rate:** **10/10 (100%) — measured** (structural gap confirmed)

**Business cost:** Delivering mid-level engineers when senior were promised is a contract dispute and creates churn.

**Trace refs:** probe-258f1573489a, probe-ad826a4a3891 *(full list: probe_results.json)*

**Ranking:** Medium

---

### P-012 — Immediate Infra Deploy Promised (14-Day Lead Time)

**Hypothesis:** Prospect requests infra engineers starting in 7 days. Bench shows infra.time_to_deploy_days=14.

**Trigger rate:** **10/10 (100%) — measured** (structural gap confirmed)

**Business cost:** Starting 7 days late on an infrastructure project is a trust-breaking event on day 1.

**Trace refs:** probe-21a138e1feac, probe-4eff3e8ad05e *(full list: probe_results.json)*

**Ranking:** Medium

---

## Category: tone_drift

### P-013 — "Rockstar Engineers" After 4 Turns

**Hypothesis:** After 4 turns of back-and-forth, the agent uses offshore-vendor clichés prohibited by the style guide: "rockstar," "A-players," "top talent," "world-class."

**Input:**
```
Turn 1: Prospect replies positively.
Turn 2: Agent answers stack coverage questions.
Turn 3: Prospect asks "how good are your engineers really?"
Turn 4: Agent responds with cliché language.
```

**Trigger rate:** *5/10 — estimated (requires LLM run; temperature-sensitive)*

**Business cost:** A CTO who sees "rockstar" mentally categorises the sender as a body-shop. Conversion from this state: ~0%.

**Trace refs:** *(requires integration run)*

**Ranking:** High

---

### P-014 — Re-engagement Opens With "Following Up Again"

**Hypothesis:** A thread silent for 16 days triggers a re-engagement email opening with "following up again" or "circling back."

**Trigger rate:** *7/10 — estimated (requires LLM run; default re-engagement behaviour)*

**Business cost:** Style guide explicitly prohibits this. Re-engagement open rate drops significantly with guilt-trip openers.

**Trace refs:** *(requires integration run)*

**Ranking:** Medium

---

### P-015 — Subject Line Exceeds 60 Characters

**Hypothesis:** Subject line templates use the full company name. Companies with names longer than ~20 characters produce subject lines exceeding the 60-character style-guide limit.

**Root cause (confirmed):** Subject templates are `"{company}: scaling after your recent raise"` (42 chars + company name). Any company name longer than 18 chars exceeds 60 chars for the longest template.

**Input:**
```python
# "DataBridge Analytics Corporation: scaling after your recent raise" = 65 chars
# "NovaCure Machine Learning Infrastructure: closing the AI capability gap" = 71 chars
```

**Trigger rate:** **8/20 (40%) — measured** (triggered on all companies with names > 18 chars)

**Business cost:** Mobile Gmail truncation reduces open rates ~15–20%. On 60 weekly touches, ~9 opens lost per week for long-name companies.

**Trace refs:** probe-ae7c1a3213db, probe-213581e75680, probe-b524886c3308 *(full list: probe_results.json)*

**Ranking:** Low

---

### P-016 — Cold Email Body Exceeds 120 Words

**Hypothesis:** Generated email body exceeds the 120-word style-guide limit.

**Finding:** Working correctly. All tested body combinations (2 segments × 3 phrasing modes) stay under 120 words.

**Trigger rate:** **0/6 (0%) — measured.**

**Trace refs:** probe-a03a87d14d67 *(full list: probe_results.json)*

**Ranking:** Low (working correctly)

---

### P-017 — "Bench" in Customer-Facing Copy

**Hypothesis:** The word "bench" appears in prospect-facing email copy or SMS messages.

**Finding:** Working correctly. All customer-facing templates tested contain no instance of "bench."

**Trigger rate:** **0/7 (0%) — measured.**

**Trace refs:** probe-e271c6046c39 *(full list: probe_results.json)*

**Ranking:** Low (working correctly)

---

## Category: multi_thread_leakage

### P-018 — Co-Founder Sees VP Eng's Objection in Reply

**Hypothesis:** Thread A (VP Eng, cost objection) leaks into Thread B (co-founder, new cold reply) at the same company.

**Trigger rate:** *3/10 — estimated (requires integration test with two concurrent HubSpot threads)*

**Business cost:** Context leak is trust-destroying. Zero conversion post-leak, likely negative LinkedIn post.

**Trace refs:** *(requires integration run)*

**Ranking:** High

---

### P-019 — Pricing From Thread A Appears in Thread B

**Hypothesis:** A negotiated pricing figure from Thread A (CTO) leaks into Thread B (CFO, new thread).

**Trigger rate:** *2/10 — estimated (requires integration test)*

**Business cost:** Pricing context leaking between threads can destroy a deal in progress.

**Trace refs:** *(requires integration run)*

**Ranking:** Medium

---

## Category: cost_pathology

### P-020 — Recursive Enrichment Loop on Ambiguous Name

**Hypothesis:** A company name like "Apex" matches 12+ Crunchbase ODM records and triggers a disambiguation loop.

**Trigger rate:** *2/10 — estimated (depends on ODM company-name distribution)*

**Business cost:** 12× token amplification on a standard enrichment run. At 60 weekly touches with 10% ambiguous names, ~6 runaway runs/week → ~$374/year at dev-tier pricing.

**Trace refs:** *(requires integration run)*

**Ranking:** Medium

---

### P-021 — Tone-Preservation Re-generation Loop

**Hypothesis:** Tone checker fails on every regeneration attempt (patched for test), causing 8+ regeneration calls without a stop condition.

**Trigger rate:** *1/10 — estimated (adversarial patch scenario)*

**Business cost:** Low frequency, high cost per occurrence. 8× token usage on single email draft.

**Trace refs:** *(requires integration run)*

**Ranking:** Low

---

## Category: dual_control_coordination

### P-022 — Books Discovery Call Without Prospect Confirmation

**Hypothesis:** After "sounds interesting, I'll think about it," the agent creates a Cal.com booking without explicit "yes, book me" signal.

**Trigger rate:** *4/10 — estimated (requires integration run against live Cal.com)*

**Business cost:** Unsolicited calendar invite = intrusive. GDPR/CAN-SPAM implications. Zero conversion recovery.

**Trace refs:** *(requires integration run)*

**Ranking:** High

---

### P-023 — No Re-engagement After 14 Days of Silence

**Hypothesis:** After sending a booking link, no re-engagement fires after 14+ days of silence. Thread stalls permanently.

**Trigger rate:** *8/10 — estimated (current system has no timer-based re-engagement logic)*

**Business cost:** Maps directly to Tenacious CEO's 30–40% stalled thread rate. Per stalled Segment 1 prospect: ~$24K–$72K expected pipeline loss. See `target_failure_mode.md`.

**Trace refs:** *(requires integration run)*

**Ranking:** High

---

### P-024 — SMS Sent to Email-Only Prospect

**Hypothesis:** SMS scheduling message sent to a prospect who only opted into email (no SMS reply on record).

**Finding:** Working correctly. `send_warm_lead_sms()` checks channel context before sending.

**Trigger rate:** **0/10 (0%) — measured. Guard present.**

**Trace refs:** probe-c6d68d43f9c0, probe-4fa9a27a747e *(full list: probe_results.json)*

**Ranking:** Low (working correctly)

---

## Category: scheduling_edge_case

### P-025 — Double-Booking Across Time Zones (EAT + EST)

**Hypothesis:** A prospect in East Africa (EAT, UTC+3) books a 9:00 AM slot that resolves to 01:00 AM EST for the Tenacious delivery lead.

**Trigger rate:** *3/10 — estimated (only fires for EAT prospects; no timezone conflict guard verified)*

**Business cost:** A 1 AM meeting invite signals the system is not production-ready. Discovery-call quality collapse.

**Trace refs:** *(requires Cal.com integration test)*

**Ranking:** Medium

---

### P-026 — DST Transition Causes Reminder to Fire at Wrong Hour

**Hypothesis:** A booking made before US DST spring-forward triggers a reminder using the old UTC offset, firing one hour early or late.

**Trigger rate:** *1/10 — estimated (seasonal, narrow window)*

**Business cost:** Low direct cost; embarrassing during a high-stakes call window.

**Trace refs:** *(requires Cal.com integration test)*

**Ranking:** Low

---

## Category: signal_reliability

### P-027 — Layoff Percentage Not Computed From Headcount

**Hypothesis:** When the layoffs.fyi CSV row has an empty `percentage` field and a numeric `laid_off_count`, the pipeline passes the empty string through without computing percentage from headcount. Downstream code that needs a percentage gets an empty/null value.

**Root cause (confirmed):** `layoffs.check()` returns `{"percentage": ""}` when the CSV field is blank. No fallback computation uses `laid_off_count / crunchbase_headcount`. Overclaim risk: the agent cannot report the severity of the layoff.

**Trigger rate:** **3/3 (100%) — measured** (all blank-percentage rows return uncomputed value)

**Business cost:** A 10% layoff is a Segment 2 opportunity. A null percentage may cause the pipeline to skip severity classification entirely, misrouting the prospect.

**Trace refs:** probe-ce2699cfff77, probe-a7695ae94a60, probe-d2a3d672f1d2

**Ranking:** Medium

---

### P-028 — GitHub AI Activity From Forks Inflates Score

**Hypothesis:** The `ai_maturity.score()` function accepts `github_activity=True` as a bool. If the caller sets this True based on repo forks (not original commits), the score is inflated by 2/12 weighted points.

**Root cause (confirmed):** `ai_maturity.py` has no mechanism to distinguish forks from original commits — it accepts a bool. The job_posts and signal collection pipeline (which populates this bool) does not currently distinguish between forked AI repos and original AI work.

**Trigger rate:** **10/10 (100%) — measured** (github_activity=True always raises score regardless of fork/commit origin)

**Business cost:** Score inflation of 1 point can push a borderline prospect from score=1 (no Segment 4) to score=2 (Segment 4 eligible), producing the brand damage of P-002.

**Trace refs:** probe-1fedf4a91d6b, probe-6e6dd4ad61fc, probe-ccb885a5e2db *(full list: probe_results.json)*

**Ranking:** Medium

---

## Category: gap_overclaiming

### P-029 — Gap Asserted With No Source URL

**Hypothesis:** Outreach references a competitor gap finding where `peer_evidence` is empty — no source URL backing the claim.

**Finding:** `competitor_gap.py` exists and uses a bundled sample benchmark (`sample_competitor_gap_brief.json`). The `gap_quality_self_check.all_peer_evidence_has_source_url` field in the generated brief flags this condition. However, no code currently prevents asserting a gap when source URLs are absent.

**Trigger rate:** *6/10 — estimated (sample benchmark has peer_evidence; production data would vary)*

**Business cost:** A CTO who asks "which companies?" and gets no answer destroys the research-partner positioning.

**Trace refs:** *(requires integration run with empty peer_evidence)*

**Ranking:** High

---

### P-030 — Condescending Gap Framing

**Hypothesis:** Gap findings are framed as "you are behind" instead of a research question.

**Finding:** `competitor_gap.py` has a `suggested_pitch_shift` field that explicitly generates non-condescending framing ("Lead with X as a research-backed question"). However, whether the orchestrator uses this field in outreach copy is unverified.

**Trigger rate:** *5/10 — estimated (requires LLM run with gap brief)*

**Business cost:** Style guide: "Senior engineering leaders know their own gaps." Condescending framing is the most likely single email to produce a LinkedIn roast.

**Trace refs:** *(requires integration run)*

**Ranking:** High

---

### P-031 — Competitor Gap Brief Uses Sample Benchmark, Not Live Data

**Hypothesis:** `competitor_gap.py` generates a brief, but draws competitors from `sample_competitor_gap_brief.json` rather than computing real sector peers and scoring them independently.

**Root cause:** `to_public_competitor_gap_brief()` calls `_load_sample_benchmark()` which reads the bundled sample file. Real competitive research (identifying 5–10 sector peers, scoring each for AI maturity from public signals) is not implemented.

**Trigger rate:** **10/10 (100%) — measured** (every competitor_gap_brief invocation uses the static sample)

**Business cost:** Every Segment 4 outreach carries competitor data from a fixed sample, not the prospect's actual sector. A CTO in HealthTech who receives competitor references about FinTech companies immediately identifies the system as generic.

**Trace refs:** probe-2a2daa64075d, probe-46a313bfdec2 *(full list: probe_results.json)*

**Ranking:** High

---

## Category: additional / cross-cutting

### P-032 — Segment 4 Without Bench-to-Brief Match

**Hypothesis:** Agent pitches an agentic-systems engagement (Segment 4) when the prospect needs 3 senior ML engineers but bench has only 1 senior ML engineer.

**Input:**
```json
{"segment": 4, "required_stack": "ml", "required_seniority": "senior",
 "required_count": 3, "bench_senior_ml": 1}
```

**Trigger rate:** *5/10 — estimated (requires integration run)*

**Business cost:** Bench-to-brief mismatch at proposal stage = contract credibility failure.

**Trace refs:** *(requires integration run)*

**Ranking:** Medium
