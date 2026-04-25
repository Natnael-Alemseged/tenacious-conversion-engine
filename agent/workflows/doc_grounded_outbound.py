from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from agent.enrichment.schemas import HiringSignalBrief
from agent.workflows.tenacious_kb import MarkdownSection, load_tenacious_kb

STEP_BODY_MAX_WORDS: dict[int, int] = {1: 120, 2: 100, 3: 70}
FULL_TEXT_MAX_WORDS = 140
BANNED_PHRASES: tuple[str, ...] = (
    "circling back",
    "touch base",
    "hope this finds you well",
)


@dataclass
class OutboundDraft:
    subject: str
    html: str
    text: str
    doc_sources_used: list[str]
    fallback_used: bool
    constraint_violations: list[str] = field(default_factory=list)
    word_count: int = 0


def _extract_code_fence(text: str) -> str:
    match = re.search(r"```(?:\w+)?\n([\s\S]*?)\n```", text)
    return (match.group(1).strip() if match else "").strip()


def _html_from_text(text: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return "".join(f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)


def _word_count(text: str) -> int:
    return len([t for t in re.split(r"\s+", text.strip()) if t])


def _render_signature(*, kb: object, first_name: str) -> tuple[str, MarkdownSection | None]:
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


def _fact_sentence(brief: HiringSignalBrief) -> str:
    raw = brief.signals.job_posts.data.get("open_roles", 0)
    try:
        open_roles = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        open_roles = 0
    if open_roles > 0:
        return f"Public job-post signal lists {open_roles} open roles at {brief.company_name}."
    if brief.signals.funding.data:
        return f"Public funding activity is on record for {brief.company_name}."
    return f"We reviewed public hiring and firmographic signals for {brief.company_name}."


def _subject_for_step(*, brief: HiringSignalBrief, step: int) -> str:
    company = brief.company_name.strip() or "your team"
    if step == 2:
        return f"One more data point: hiring at {company}"[:59]
    if step == 3:
        return f"Closing the loop: {company}"[:59]
    seg = brief.icp_segment
    if seg == 2:
        return f"Note: signals at {company}"[:59]
    if seg == 3:
        return f"Congrats: leadership at {company}"[:59]
    if seg == 4:
        return f"Question: capacity at {company}"[:59]
    return f"Context: hiring at {company}"[:59]


def _compose_body(
    *,
    brief: HiringSignalBrief,
    first_name: str,
    cal_link: str,
    step: int,
) -> str:
    fact = _fact_sentence(brief)
    if step == 1:
        return (
            f"{first_name},\n\n"
            f"{fact}\n\n"
            "Post-funding teams often hit recruiting-capacity pressure before budget "
            "becomes the constraint.\n\n"
            "Tenacious embeds senior engineers in client stacks with short ramp and "
            "timezone overlap — managed teams, not staff aug.\n\n"
            f"Worth 15 minutes to compare notes? {cal_link}"
        ).strip()
    if step == 2:
        return (
            f"{first_name},\n\n"
            f"Adding one hiring-signal data point: {fact}\n\n"
            "Does that pattern read as hiring-velocity pressure, or a deliberate cadence?\n\n"
            f"Happy to compare notes without a deck. {cal_link}"
        ).strip()
    return (
        f"{first_name},\n\n"
        f"{fact}\n\n"
        "I'll leave this thread here if timing is not a fit.\n\n"
        f"If a one-page hiring-signal snapshot helps, reply yes. "
        f"You can also book a short call: {cal_link}"
    ).strip()


def _fallback_body(*, first_name: str, cal_link: str, signature_text: str) -> str:
    core = (
        f"{first_name},\n\n"
        f"If a quick fit check helps, pick a slot here: {cal_link}\n\n"
        f"{signature_text}"
    ).strip()
    return core


def _collect_violations(*, text: str, body_main: str, body_max: int) -> list[str]:
    violations: list[str] = []
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            violations.append(f"banned_phrase:{phrase}")
    if "bench" in lowered:
        violations.append("contains_bench_jargon")
    wc_body = _word_count(body_main)
    if wc_body > body_max:
        violations.append(f"body_word_count_{wc_body}_exceeds_{body_max}")
    wc_full = _word_count(text)
    if wc_full > FULL_TEXT_MAX_WORDS:
        violations.append(f"full_word_count_{wc_full}_exceeds_{FULL_TEXT_MAX_WORDS}")
    return violations


def build_doc_grounded_cold_outbound(
    *,
    brief: HiringSignalBrief,
    first_name: str,
    cal_link: str,
    step: int,
) -> OutboundDraft:
    if step not in STEP_BODY_MAX_WORDS:
        raise ValueError(f"step must be one of {sorted(STEP_BODY_MAX_WORDS)}, got {step}")

    kb = load_tenacious_kb()
    cold = kb.find_first_in_source(
        source_suffix="tenacious_sales_data/seed/email_sequences/cold.md",
        heading_contains=f"Email {step}",
    )
    signature_text, signature_section = _render_signature(kb=kb, first_name=first_name)
    doc_sources_used = kb.doc_refs(cold, signature_section)

    subject = _subject_for_step(brief=brief, step=step)
    body_main = _compose_body(brief=brief, first_name=first_name, cal_link=cal_link, step=step)
    text = f"{body_main}\n\n{signature_text}".strip()
    violations = _collect_violations(
        text=text,
        body_main=body_main,
        body_max=STEP_BODY_MAX_WORDS[step],
    )
    constraint_violations: list[str] = []
    fallback_used = False
    if violations:
        fallback_used = True
        constraint_violations = list(violations)
        text = _fallback_body(
            first_name=first_name, cal_link=cal_link, signature_text=signature_text
        )

    wc = _word_count(text)
    return OutboundDraft(
        subject=subject,
        html=_html_from_text(text),
        text=text,
        doc_sources_used=doc_sources_used,
        fallback_used=fallback_used,
        constraint_violations=constraint_violations,
        word_count=wc,
    )
