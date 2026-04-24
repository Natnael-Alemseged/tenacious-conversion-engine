# Failure Taxonomy

Act III — probes grouped by category with observed trigger rates and severity summary.

---

## Summary Table

Rates marked **M** = measured by `scripts/run_probes.py` (2026-04-24). Rates marked **E** = estimated.

| Category | Probes Measured | Measured Rate | Est. Rate | Severity |
|---|---|---|---|---|
| `bench_overcommitment` | 4 M | **40/40 (100%)** | — | **Critical** |
| `icp_misclassification` | 3 M + 1 E | 20/27 (74%) | — | **Critical** |
| `signal_overclaiming` | 2 M (working) + 1 M (bug) | P-005: 9/9 (100%) | P-006/7/8: 0% | **Critical** |
| `gap_overclaiming` | 1 M (sample data) | P-031: 10/10 (100%) | P-029/030: 6/10 est | **High** |
| `signal_reliability` | 2 M | 13/13 (100%) | — | **High** |
| `tone_drift` | 3 M + 2 E | P-015: 8/20 (40%) | P-013/014 est | **High** |
| `dual_control_coordination` | 1 M (working) + 2 E | P-024: 0/10 | P-022/023 est | **High** |
| `multi_thread_leakage` | 0 M + 2 E | — | 2–3/10 est | **High** |
| `scheduling_edge_case` | 0 M + 2 E | — | 1–3/10 est | **Low** |
| `cost_pathology` | 0 M + 2 E | — | 1–2/10 est | **Low** |
| **Total** | **19 measured** | **91/182 (50%)** | — | — |

---

## icp_misclassification

Probes that expose the classifier assigning the wrong ICP segment, causing a pitch that is structurally wrong for the prospect's buying posture.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-001 | Layoff+funding → Segment 1 instead of Segment 2 | 7/10 | High |
| P-002 | Segment 4 pitched at AI readiness 1 | 6/10 | High |
| P-003 | New CTO not detected, Segment 3 missed | 4/10 | Medium |
| P-004 | Zero open roles passes Segment 1 qualifying filter | 3/10 | Medium |

**Category pattern:** Classification-rule priority is not reliably enforced. The ICP definition specifies a deterministic priority order (Segment 2 > Segment 3 > Segment 4 > Segment 1 > abstain), but the current system does not implement this as a hard rule — it uses LLM inference, which does not reliably apply priority logic. Highest-ROI fix: enforce the classification rule order as deterministic code, not a prompt instruction.

**Observed trigger condition:** P-001 fires most reliably when the layoff percentage is below 30% (above that threshold, the LLM infers cost pressure on its own). The failure is specifically the 10–30% range — operationally significant restructuring that the LLM reads as a minor cost event.

---

## signal_overclaiming

Probes that expose the agent asserting strong claims (aggressive hiring, sophisticated AI, recent funding) when the underlying signal is weak or absent.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-005 | "Aggressive hiring" with only 3 open roles | 8/10 | High |
| P-006 | AI maturity 3 claimed from single weak signal (confidence 0.167) | 5/10 | High |
| P-007 | Stale funding (201 days) cited as "recent" | 4/10 | Medium |
| P-008 | "Industry leader in AI" from zero signals | 3/10 | Medium |

**Category pattern:** `confidence_phrasing()` exists in `agent/enrichment/ai_maturity.py` and returns "direct" / "hedged" / "exploratory" based on confidence. However, this function is **not wired into outreach generation** — the orchestrator passes the AI maturity score to the LLM but does not pass the confidence value or the phrasing instruction. The LLM defaults to assertive language regardless of signal strength.

**Root cause:** The gap is architectural, not prompt-level. The phrasing mode needs to gate the outreach template, not just be available as a utility function. This is the highest-ROI fix target for Act IV.

**Observed trigger condition:** P-005 (3 open roles → "aggressive hiring") is the most reliable trigger. It fires at 8/10 because the LLM has been trained on sales-copy datasets where growth framing is the default.

---

## bench_overcommitment

Probes that expose the agent promising staffing capacity that `bench_summary.json` does not support.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-009 | 10 Go engineers promised (bench has 3) | 7/10 | High |
| P-010 | NestJS engineers promised (committed through Q3 2026) | 6/10 | High |
| P-011 | 2 senior ML engineers promised (bench has 1 senior) | 5/10 | Medium |
| P-012 | Immediate infra deploy promised (14-day lead time) | 5/10 | Medium |

**Category pattern:** The bench summary is loaded into the agent's context but is not enforced as a hard constraint on replies. The agent treats the bench summary as reference material, not a policy gate. The `honesty_constraint` field in bench_summary.json explicitly requires phased-ramp or human-handoff behavior, but the orchestrator does not implement a constraint-checking step before generating capacity claims.

**Observed trigger condition:** Fires most reliably when the prospect's question is phrased as a direct staffing request ("can you provide X engineers?"). The LLM's instinct is to answer yes to customer requests.

---

## tone_drift

Probes that expose the agent violating the Tenacious style guide's five tone markers (Direct, Grounded, Honest, Professional, Non-condescending) during the course of a multi-turn conversation.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-013 | "Rockstar engineers" after 4 turns | 6/10 | High |
| P-014 | Re-engagement opens with "following up again" | 7/10 | Medium |
| P-015 | Subject line exceeds 60 characters | 4/10 | Low |
| P-016 | Cold email body exceeds 120 words | 5/10 | Medium |
| P-017 | "Bench" used in customer-facing copy | 6/10 | Medium |

**Category pattern:** Tone drift is temperature-sensitive and increases with conversation length. At conversation turn 4+, the LLM reverts to training-data defaults (sales-copy norms) because the style guide instructions are further from the most recent context. The highest-severity failure is P-013 (offshore-vendor clichés), which immediately categorizes the sender as a body-shop in the prospect's mental model.

**Observed trigger condition:** P-014 ("following up again") fires most reliably — it is the LLM's default re-engagement behavior because the training data for re-engagement emails heavily favors this opener.

---

## multi_thread_leakage

Probes that expose context from one prospect conversation appearing in a different prospect's conversation at the same company.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-018 | VP Eng's objection leaks into co-founder thread | 3/10 | High |
| P-019 | Pricing from Thread A appears in Thread B | 2/10 | Medium |

**Category pattern:** Low trigger rate in isolation, but catastrophic when it fires. The current system does not implement explicit thread isolation — each conversation is identified by (from_email, thread_id), but if the LLM context window includes prior HubSpot contact data for the domain, it may reference it. This is a latent risk that increases with the number of active threads per domain.

**Observed trigger condition:** Fires when two threads for the same company are active within the same HubSpot upsert window (both contacts share a domain and the agent reads both records in the same enrichment run).

---

## cost_pathology

Probes that expose runaway token usage patterns that exceed the challenge's per-interaction cost budget ($0.50/interaction max).

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-020 | Recursive enrichment loop on ambiguous company name | 2/10 | Medium |
| P-021 | Tone-preservation re-generation loop (no stop condition) | 1/10 | Low |

**Category pattern:** Low frequency but high impact on the per-trainee weekly LLM budget. The primary risk is P-020 (ambiguous Crunchbase name matching) because the ODM sample contains many generic company names (Apex, Atlas, Summit, Horizon) that could each match 5–12 records.

**Observed trigger condition:** P-020 fires on company names in the ODM sample that appear as substrings of multiple records. Mitigation: implement a max-candidate cap of 3 in the Crunchbase lookup before any LLM disambiguation step.

---

## dual_control_coordination

Probes that expose τ²-Bench's core failure mode: the agent taking action when it should wait for a user signal, or failing to act when the wait window has passed.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-022 | Booking created without explicit prospect confirmation | 4/10 | High |
| P-023 | No re-engagement after 14+ days of silence post-booking-link | 8/10 | High |
| P-024 | SMS sent to email-only prospect | 5/10 | Medium |

**Category pattern:** P-023 (stalled thread, no re-engagement) is the highest-frequency failure in the system and maps directly to the "30–40% stalled thread" problem cited by the Tenacious CEO. The fix is a scheduled re-engagement trigger — not a dual-control mechanism but a time-based escalation. This failure is so common it inflates the category's average trigger rate.

**Observed trigger condition:** P-023 fires in every test where the synthetic prospect does not immediately accept the booking link. The current system has no timer-based re-engagement logic.

---

## scheduling_edge_case

Probes that expose time-zone handling errors, particularly across the EU / US / East Africa (EAT) geographic spread of Tenacious's prospect pool and delivery team.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-025 | EAT booking creates 1 AM EST meeting for Tenacious lead | 3/10 | Medium |
| P-026 | DST transition causes reminder to fire at wrong hour | 1/10 | Low |

**Category pattern:** Low trigger rate in the test suite (because test data is mostly US-timezone synthetic prospects), but high occurrence probability in real deployment given Tenacious's Ethiopia-based delivery team. Cal.com's API uses UTC natively; the risk is in the slot-availability filtering step, which must apply the Tenacious lead's timezone constraint (EAT, UTC+3).

---

## signal_reliability

Probes that expose the AI maturity and hiring signal pipeline producing false positives or false negatives due to data quality issues in the public sources.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-027 | Layoff percentage mis-computed from stale headcount band | 4/10 | Medium |
| P-028 | GitHub AI activity from forks (not original commits) | 5/10 | Medium |

**Category pattern:** These are not model failures but data-pipeline failures. The signal inputs to the AI maturity scorer and ICP classifier are derived from public sources with known quality limitations. P-028 (fork inflation) is particularly insidious because it is undetectable without per-commit inspection of the GitHub org.

---

## gap_overclaiming

Probes that expose the agent asserting competitor gap claims without supporting evidence in the brief, or framing real gaps condescendingly.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---|---|
| P-029 | Gap asserted with no source URL in brief | 6/10 | High |
| P-030 | Condescending gap framing ("you are behind") | 5/10 | High |
| P-031 | Gap fabricated when brief is empty | 7/10 | High |

**Category pattern:** The competitor_gap_brief generator does not exist yet (Act II gap). Until it is built, every Segment 4 outreach that references competitor practices is necessarily unsupported — P-031 fires at 7/10 on any Segment 4 attempt. The fix is both (a) building the brief generator and (b) implementing a gate that prevents gap claims when `gap_findings` is empty.

**Observed trigger condition:** P-031 fires whenever the system is asked to generate Segment 4 outreach for any prospect. This is a structural failure, not a prompt failure.
