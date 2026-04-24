# Failure Taxonomy

Act III — probes grouped by category with observed trigger rates and severity summary.

Rates marked **M** were measured by `scripts/run_probes.py` on 2026-04-24 against deterministic code paths, with no LLM or live external calls. Rates marked *E* are integration or LLM-sensitive probes that remain estimated until Act IV/final evaluation.

---

## Summary Table

| Category | Probes | Measured Trigger Rate | Estimated Trigger Rate | Severity |
|---|---:|---:|---:|---|
| `bench_overcommitment` | 4 M | **40/40 (100%)** | — | **Critical** |
| `icp_misclassification` | 4 M | **20/37 (54%)** | — | **Critical** |
| `signal_overclaiming` | 4 M | **0/39 (0%)** | — | **Critical** |
| `gap_overclaiming` | 1 M + 2 E | **10/10 (100%)** | *P-029: 6/10, P-030: 5/10* | **High** |
| `signal_reliability` | 2 M | **13/13 (100%)** | — | **High** |
| `tone_drift` | 3 M + 2 E | **8/33 (24%)** | *P-013: 5/10, P-014: 7/10* | **High** |
| `dual_control_coordination` | 1 M + 2 E | **0/10 (0%)** | *P-022: 4/10, P-023: 8/10* | **High** |
| `multi_thread_leakage` | 2 E | — | *P-018: 3/10, P-019: 2/10* | **High** |
| `scheduling_edge_case` | 2 E | — | *P-025: 3/10, P-026: 1/10* | **Low** |
| `cost_pathology` | 2 E | — | *P-020: 2/10, P-021: 1/10* | **Low** |
| `additional_cross_cutting` | 1 E | — | *P-032: 5/10* | **Medium** |
| **Total measured** | **19 M** | **91/182 (50%)** | — | — |

---

## `icp_misclassification`

These probes test whether the classifier assigns the wrong ICP segment and therefore sends a pitch that does not match the prospect's buying posture.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-001 | Layoff+funding routes to Segment 1 instead of Segment 2 | **10/10 M** | High |
| P-002 | Segment 4 should not be assigned at AI readiness score 1 | **0/10 M** | Low |
| P-003 | Leadership titles should be normalized and detected | **0/7 M** | Low |
| P-004 | Recent funding with zero open engineering roles passes Segment 1 | **10/10 M** | Medium |

**Category pattern:** The highest-cost classification failures are deterministic rule gaps: the Segment 2 layoff override and the Segment 1 open-role threshold are not hard gates. The AI readiness and leadership-title guards tested here are working.

---

## `signal_overclaiming`

These probes test whether the agent asserts strong claims when the underlying public signal is weak, stale, or absent.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-005 | Segment 1 opener stays assertive even when confidence is exploratory | **0/9 M after Act IV** | High |
| P-006 | Single weak AI signal should produce exploratory phrasing | **0/10 M** | Low |
| P-007 | Funding older than 180 days should not be cited as recent | **0/10 M** | Low |
| P-008 | Empty AI signals should return score 0 | **0/10 M** | Low |

**Category pattern:** The signal scoring utilities behave correctly. Act IV added confidence-sensitive opener phrasing, which reduced `P-005` from the Act III baseline of 9/9 failures to 0/9 in the current deterministic probe run. This closes the selected target failure while leaving other categories unchanged.

---

## `bench_overcommitment`

These probes test whether the agent can promise staffing capacity that the Tenacious bench summary does not support.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-009 | Prospect requests 10 Go engineers; bench has 3 | **10/10 M** | High |
| P-010 | NestJS engineers show available but are committed through Q3 2026 | **10/10 M** | High |
| P-011 | Prospect requests 2 senior ML engineers; bench has 1 | **10/10 M** | Medium |
| P-012 | Prospect requests infra deployment in 7 days; bench lead time is 14 days | **10/10 M** | Medium |

**Category pattern:** Bench facts are available as reference material, but not enforced as a hard reply constraint. This makes every direct capacity-request probe trigger structurally.

---

## `tone_drift`

These probes test whether outbound and reply copy violates Tenacious style constraints over subject lines, body length, word choice, and multi-turn drift.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-013 | Multi-turn reply uses offshore-vendor cliches like "rockstar engineers" | *5/10 E* | High |
| P-014 | Re-engagement opens with "following up again" or "circling back" | *7/10 E* | Medium |
| P-015 | Subject line exceeds 60 characters | **8/20 M** | Low |
| P-016 | Cold email body exceeds 120 words | **0/6 M** | Low |
| P-017 | Customer-facing copy uses the word "bench" | **0/7 M** | Low |

**Category pattern:** Template length and banned-word checks are mostly stable. The larger tone risk is LLM-sensitive multi-turn drift, which needs integration probes rather than deterministic string checks.

---

## `multi_thread_leakage`

These probes test whether context from one prospect at a company leaks into a different prospect's thread at the same company.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-018 | Co-founder thread sees VP Engineering's objection | *3/10 E* | High |
| P-019 | Pricing from Thread A appears in Thread B | *2/10 E* | Medium |

**Category pattern:** Low estimated frequency, but catastrophic business cost. These require an integration test with concurrent HubSpot/contact state.

---

## `cost_pathology`

These probes test runaway token or tool-usage patterns.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-020 | Ambiguous company name creates recursive enrichment/disambiguation loop | *2/10 E* | Medium |
| P-021 | Tone checker can regenerate repeatedly without a stop condition | *1/10 E* | Low |

**Category pattern:** These are lower-frequency budget risks. The mitigation is explicit max-candidate and max-regeneration caps.

---

## `dual_control_coordination`

These probes test whether the agent acts only after the right user/prospect signal, and whether it follows up when a thread stalls.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-022 | Discovery call is booked without explicit prospect confirmation | *4/10 E* | High |
| P-023 | No re-engagement after 14 days of silence | *8/10 E* | High |
| P-024 | SMS sent to email-only prospect | **0/10 M** | Low |

**Category pattern:** The SMS channel guard is present. Booking confirmation and stalled-thread recovery need integration/scheduler tests.

---

## `scheduling_edge_case`

These probes test timezone and reminder issues for EU, US, and East Africa prospect pools.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-025 | EAT booking resolves to an unreasonable EST meeting time | *3/10 E* | Medium |
| P-026 | DST transition shifts reminder timing by an hour | *1/10 E* | Low |

**Category pattern:** Cal.com stores UTC, so the primary risk is slot filtering and reminder display logic around local working hours.

---

## `signal_reliability`

These probes test public-signal false positives and false negatives that flow into the classifier or AI maturity score.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-027 | Blank layoff percentage is not computed from headcount | **3/3 M** | Medium |
| P-028 | GitHub activity from forks can inflate AI maturity score | **10/10 M** | Medium |

**Category pattern:** These are data-pipeline issues, not language-model issues. They matter because bad public signals feed both ICP assignment and signal-grounded copy.

---

## `gap_overclaiming`

These probes test unsupported or condescending competitor-gap claims.

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-029 | Gap claim has no source URL in peer evidence | *6/10 E* | High |
| P-030 | Gap is framed as "you are behind" rather than a research question | *5/10 E* | High |
| P-031 | Competitor gap brief uses bundled sample benchmark, not live peer research | **10/10 M** | High |

**Category pattern:** The current generator exists, but `P-031` confirms it is based on bundled sample data rather than live sector-peer research. This is acceptable as an identified Act III failure, but it must be treated as a blocker before Segment 4 production outreach.

---

## `additional_cross_cutting`

| Probe | Hypothesis Summary | Trigger Rate | Ranking |
|---|---|---:|---|
| P-032 | Segment 4 pitch is not checked against available senior ML bench capacity | *5/10 E* | Medium |

**Category pattern:** This joins the gap-brief and bench-commitment risks: even a well-sourced gap claim should not produce an offer the bench cannot credibly staff.
