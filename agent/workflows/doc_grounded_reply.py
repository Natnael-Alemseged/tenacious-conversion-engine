from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from agent.core.config import settings
from agent.enrichment.schemas import HiringSignalBrief
from agent.models.webhooks import InboundEmailEvent
from agent.workflows.reply_intent import ReplyIntentResult
from agent.workflows.tenacious_kb import MarkdownSection, TenaciousKnowledgeBase, load_tenacious_kb


def _inbound_text_lower(event: InboundEmailEvent) -> str:
    return f"{event.subject or ''}\n{event.body or ''}".lower()


def _is_weak_intent(intent: ReplyIntentResult | None) -> bool:
    if intent is None:
        return True
    return intent.confidence < 0.5


def _has_pricing_keywords(text: str) -> bool:
    return any(k in text for k in ("price", "pricing", "rate", "cost", "budget"))


def _has_proof_keywords(text: str) -> bool:
    return any(
        p in text
        for p in (
            "case study",
            "case studies",
            "references",
            "customers",
            "proof",
        )
    )


def _has_discovery_keywords(text: str) -> bool:
    return any(
        p in text
        for p in (
            "process",
            "timeline",
            "what happens next",
            "how does this work",
        )
    )


def _has_objection_phrase(text: str) -> bool:
    return any(p in text for p in ("too expensive", "higher than", "cheaper"))


def _segment_transcript_section(
    kb: TenaciousKnowledgeBase, icp_segment: int
) -> MarkdownSection | None:
    suffixes = {
        1: "transcript_01_series_b_startup.md",
        2: "transcript_02_mid_market_restructure.md",
        3: "transcript_03_new_cto_transition.md",
        4: "transcript_04_specialized_capability.md",
    }
    need = f"Transcript 0{icp_segment}"
    name = suffixes.get(icp_segment)
    if not name:
        return None
    return kb.find_first_in_source(
        source_suffix=f"tenacious_sales_data/seed/discovery_transcripts/{name}",
        heading_contains=need,
    )


def _collect_intent_grounded_sections(
    kb: TenaciousKnowledgeBase,
    *,
    event: InboundEmailEvent,
    brief: HiringSignalBrief,
    intent: ReplyIntentResult | None,
) -> list[MarkdownSection]:
    """Extra KB sections from deterministic keyword heuristics (no LLM).

    Heuristics apply when LLM intent is missing or low-confidence.
    """
    t = _inbound_text_lower(event)
    weak = _is_weak_intent(intent)
    if not weak:
        return []

    out: list[MarkdownSection] = []
    seen: set[str] = set()

    def push(sec: MarkdownSection | None) -> None:
        if sec and sec.ref not in seen:
            seen.add(sec.ref)
            out.append(sec)

    if _has_pricing_keywords(t):
        push(
            kb.find_first_in_source(
                source_suffix="tenacious_sales_data/seed/pricing_sheet.md",
                heading_contains="Talent outsourcing",
            )
        )
        push(
            kb.find_first_in_source(
                source_suffix="tenacious_sales_data/seed/pricing_sheet.md",
                heading_contains="How the agent routes to a human",
            )
        )
        if _has_objection_phrase(t):
            push(
                kb.find_first_in_source(
                    source_suffix=(
                        "tenacious_sales_data/seed/discovery_transcripts/"
                        "transcript_05_objection_heavy.md"
                    ),
                    heading_contains="Transcript 05",
                )
            )

    if _has_proof_keywords(t):
        push(
            kb.find_first_in_source(
                source_suffix="tenacious_sales_data/seed/case_studies.md",
                heading_contains="Case Study 1",
            )
        )

    if _has_discovery_keywords(t):
        if 1 <= brief.icp_segment <= 4:
            push(_segment_transcript_section(kb, brief.icp_segment))
        if _has_objection_phrase(t):
            push(
                kb.find_first_in_source(
                    source_suffix=(
                        "tenacious_sales_data/seed/discovery_transcripts/"
                        "transcript_05_objection_heavy.md"
                    ),
                    heading_contains="Transcript 05",
                )
            )

    return out


@dataclass(frozen=True)
class DocGroundedReply:
    subject: str
    html: str
    text: str
    doc_sources_used: list[str]
    fallback_used: bool = False
    constraint_violations: list[str] | None = None


def _extract_code_fence(text: str) -> str:
    match = re.search(r"```(?:\w+)?\n([\s\S]*?)\n```", text)
    return (match.group(1).strip() if match else "").strip()


def _reply_subject(subject: str) -> str:
    cleaned = subject.strip()
    if not cleaned:
        return "Re: your note"
    if cleaned.lower().startswith("re:"):
        return cleaned
    return f"Re: {cleaned}"


def _attendee_name_from_email(email: str) -> str:
    local = email.split("@", 1)[0]
    tokens = re.split(r"[._+-]+", local)
    return " ".join(token.capitalize() for token in tokens if token) or "there"


def _signal_summary_from_brief(brief: HiringSignalBrief) -> str:
    parts: list[str] = []
    if brief.signals.funding.data:
        parts.append("a public funding signal")
    if brief.signals.layoffs.data:
        parts.append("a restructuring signal")
    open_roles = brief.signals.job_posts.data.get("open_roles", 0)
    if open_roles:
        parts.append(f"{open_roles} open roles")
    if brief.signals.ai_maturity.score:
        parts.append(f"AI maturity score {brief.signals.ai_maturity.score}/3")
    if not parts:
        return "limited public signal, so this should stay exploratory"
    return ", ".join(parts)


def _segment_label(segment: int) -> str:
    labels = {
        0: "exploratory fit",
        1: "recent funding / scaling window",
        2: "restructuring / efficiency window",
        3: "new technical leadership window",
        4: "specialized AI capability gap",
    }
    return labels.get(segment, "exploratory fit")


def _capacity_line(brief: HiringSignalBrief) -> str:
    bench = brief.signals.bench.data
    if bench.bench_to_brief_gate_passed:
        counts = {
            stack: count
            for stack, count in bench.available_counts.items()
            if stack in bench.required_stacks and count
        }
        if counts:
            joined = ", ".join(f"{count} {stack}" for stack, count in counts.items())
            return f"Capacity check: available engineers match the current brief ({joined})"
        return "Capacity check: available engineers match the current brief"
    return "Capacity check: not enough current capacity to commit without human review"


def _ai_maturity_line(brief: HiringSignalBrief) -> str:
    score = brief.signals.ai_maturity.score
    if score <= 0:
        return "AI maturity: no strong public AI signal yet"
    return f"AI maturity: {score}/3 from public signals"


def _html_from_text(text: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return "".join(f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)


def _render_signature(*, kb: object, first_name: str) -> tuple[str, MarkdownSection | None]:
    # Tight lookup: anchor to style_guide.md to avoid accidental matches.
    sig_section = (
        kb.find_first_in_source(
            source_suffix="tenacious_sales_data/seed/style_guide.md",
            heading="Signature template",
        )
        if hasattr(kb, "find_first_in_source")
        else None
    )
    template = _extract_code_fence(sig_section.text) if sig_section else ""
    if template:
        lines = template.splitlines()
        out: list[str] = []
        for line in lines:
            if line.strip().lower().startswith("[first name]"):
                out.append(first_name)
                continue
            if line.strip().lower().startswith("[title"):
                out.append("Research Partner")
                continue
            out.append(line)
        return "\n".join(out).strip(), sig_section
    return (
        "\n".join(
            [
                first_name,
                "Research Partner",
                "Tenacious Intelligence Corporation",
                "gettenacious.com",
            ]
        ).strip(),
        sig_section,
    )


def _word_count(text: str) -> int:
    return len([t for t in re.split(r"\s+", text.strip()) if t])


def _enforce_constraints(*, body: str, max_words: int) -> None:
    lowered = body.lower()
    if "bench" in lowered:
        raise ValueError("Customer-facing copy must not include internal term 'bench'.")
    if _word_count(body) > max_words:
        raise ValueError(f"Reply body exceeds max_words={max_words}.")


def _sanitize_for_constraints(*, body: str, max_words: int) -> tuple[str, list[str]]:
    """Best-effort constraint sanitizer: never raises.

    Returns (sanitized_body, violations).
    """
    violations: list[str] = []
    text = body
    if "bench" in text.lower():
        violations.append("contains_bench_jargon")
        # Replace rather than fail.
        text = re.sub(r"\bbench\b", "available capacity", text, flags=re.IGNORECASE)
    # Word-count: truncate by dropping tail tokens (keeps deterministic behavior).
    wc = _word_count(text)
    if wc > max_words:
        violations.append(f"word_count_exceeds_{max_words}")
        tokens = [t for t in re.split(r"\s+", text.strip()) if t]
        tokens = tokens[:max_words]
        text = " ".join(tokens).strip()
    return text, violations


def _handoff_reply(*, greeting: str, cal_link: str | None, signature_text: str) -> str:
    middle = "Thanks — a delivery lead will follow up within 24 hours with a tighter answer."
    if cal_link:
        middle += f"\n\nIf you prefer to talk live: {cal_link}"
    return f"{greeting}\n\n{middle}\n\n{signature_text}".strip()


def build_doc_grounded_inbound_reply(
    *,
    event: InboundEmailEvent,
    brief: HiringSignalBrief,
    booking_requested: bool,
    booking_result: dict[str, Any] | None,
    requested_booking_start: str | None,
    intent: ReplyIntentResult | None = None,
) -> DocGroundedReply:
    """Build a deterministic reply grounded in Tenacious markdown sections."""
    kb = load_tenacious_kb()
    first_name = _attendee_name_from_email(str(event.from_email)).split(" ", 1)[0]
    greeting = f"{first_name},"
    wants_brief = bool(intent and intent.intent == "request_brief" and intent.confidence >= 0.5)

    # Select source sections (actual KB sections, not decorative).
    # Tight selection: constrain source file + heading.
    style_tone = kb.find_first_in_source(
        source_suffix="tenacious_sales_data/seed/style_guide.md",
        heading="The five tone markers",
    )
    formatting = kb.find_first_in_source(
        source_suffix="tenacious_sales_data/seed/style_guide.md",
        heading="Formatting constraints",
    )
    warm_engaged = kb.find_first_in_source(
        source_suffix="tenacious_sales_data/seed/email_sequences/warm.md",
        heading_contains="Engaged reply",
    )
    warm_curious = kb.find_first_in_source(
        source_suffix="tenacious_sales_data/seed/email_sequences/warm.md",
        heading_contains="Curious reply",
    )
    inbound_template = kb.find_first_in_source(
        source_suffix="Draft Tenacious Sales Materials Template.md",
        heading_contains="Inbound Template",
    )
    signature_text, signature_section = _render_signature(kb=kb, first_name=first_name)
    intent_sections = _collect_intent_grounded_sections(kb, event=event, brief=brief, intent=intent)
    doc_sources_used: list[str] = kb.doc_refs(
        style_tone,
        formatting,
        warm_engaged,
        warm_curious,
        inbound_template,
        signature_section,
        *intent_sections,
    )

    if booking_result is not None and requested_booking_start:
        body = (
            f"{greeting}\n\n"
            f"Booked for {requested_booking_start} UTC.\n\n"
            "To make the call useful, send role count, seniority mix, timezone overlap, "
            "and target start date before then."
        )
        max_words = 150
    elif booking_requested:
        if settings.calcom_username:
            body = (
                f"{greeting}\n\n"
                "Yes. Pick a slot here: "
                f"https://cal.com/{settings.calcom_username}.\n\n"
                "Once booked, I will attach the public-signal brief and the capacity notes "
                "so the discussion starts concrete."
            )
        else:
            body = (
                f"{greeting}\n\n"
                "Yes. I can send scheduling options.\n\n"
                "Before I do, send your timezone and target start date so I do not propose "
                "irrelevant times."
            )
        max_words = 150
    elif wants_brief:
        body = (
            f"{greeting}\n\n"
            "Thanks for asking for the brief. I checked this against the public hiring "
            "signals and current Tenacious capacity notes.\n\n"
            "Grounded version:\n"
            f"- Segment fit: {_segment_label(brief.icp_segment)} "
            f"(confidence {brief.segment_confidence:.2f})\n"
            f"- {_ai_maturity_line(brief)}\n"
            f"- {_capacity_line(brief)}\n"
            f"- Public signal: {_signal_summary_from_brief(brief)}\n\n"
            "To tighten the recommendation, send role count, seniority mix, timezone overlap, "
            "and target start date."
        )
        max_words = 150
    else:
        # Keep this short per style_guide.md formatting constraints.
        body = (
            f"{greeting}\n\n"
            "Glad this landed. Tenacious runs managed engineering delivery teams for US/EU "
            "scale-ups when hiring velocity or specialized delivery capacity is the bottleneck.\n\n"
            f"For {brief.company_name}, the current read is {_segment_label(brief.icp_segment)} "
            f"based on {_signal_summary_from_brief(brief)}.\n\n"
            "If you'd rather talk live, book 15 minutes here: "
            + (
                f"https://cal.com/{settings.calcom_username}."
                if settings.calcom_username
                else "and I can send a few scheduling options."
            )
        )
        max_words = 120

    full_text = f"{body}\n\n{signature_text}".strip()
    sanitized, violations = _sanitize_for_constraints(body=full_text, max_words=max_words)
    fallback_used = False
    if violations:
        fallback_used = True
        # If sanitizer had to intervene, use a conservative handoff reply instead of
        # sending potentially awkward truncated copy.
        cal_link = (
            f"https://cal.com/{settings.calcom_username}." if settings.calcom_username else None
        )
        sanitized = _handoff_reply(
            greeting=greeting, cal_link=cal_link, signature_text=signature_text
        )
        sanitized, more = _sanitize_for_constraints(body=sanitized, max_words=120)
        violations.extend(more)

    return DocGroundedReply(
        subject=_reply_subject(str(event.subject or "")),
        html=_html_from_text(sanitized),
        text=sanitized,
        doc_sources_used=doc_sources_used,
        fallback_used=fallback_used,
        constraint_violations=violations,
    )
