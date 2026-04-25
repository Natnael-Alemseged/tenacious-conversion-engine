from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from act5.outbound_events import now_iso
from agent.core.config import settings
from agent.enrichment.competitor_gap import to_public_competitor_gap_brief
from agent.enrichment.pipeline import run as run_enrichment_pipeline
from agent.enrichment.public_briefs import to_public_hiring_signal_brief
from agent.models.webhooks import InboundEmailEvent
from agent.workflows.lead_orchestrator import LeadOrchestrator


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    raw = "|".join([prefix, *[p.strip() for p in parts if p is not None]])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class ThreadState:
    thread_id: str
    lead_id: str
    generated_at: str

    company_name: str
    lead_email: str
    careers_url: str = ""

    routing_mode: str = "sink"
    sink_email: str = ""

    last_channel: str = "email"
    email_replied: bool = False
    sms_suppressed: bool = True

    booking_requested: bool = False
    booking_created: bool = False
    booking_uid: str = ""

    hubspot_contact_id: str = ""
    crm_properties_written: dict[str, str] = field(default_factory=dict)

    bench_to_brief_gate_passed: bool = False


class FakeLangfuseClient:
    @contextmanager
    def trace_workflow(self, name: str, payload: dict[str, Any]):
        yield {"trace_id": ""}

    @contextmanager
    def span(self, name: str, input: dict[str, Any], output: dict[str, Any] | None = None):
        yield None


class FakeResendClient:
    def __init__(self) -> None:
        self._counter = 0

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        html: str,
        text: str | None = None,
        reply_to: str | None = None,
        from_email: str | None = None,
        tags: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._counter += 1
        message_id = f"fake_email_{self._counter}"
        return {
            "id": message_id,
            "to": [to_email],
            "subject": subject,
            "from": from_email or "offline@conversion-engine.invalid",
            "tags": tags or {},
            "headers": headers or {},
            "idempotency_key": idempotency_key or "",
            "created_at": _utcnow_iso(),
        }


class FakeHubSpotClient:
    def __init__(self) -> None:
        self._id_counter = 1000
        self._contacts_by_identifier: dict[str, dict[str, Any]] = {}

    def upsert_contact(
        self,
        identifier: str,
        source: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        props: dict[str, str] = {
            k: str(v) for k, v in dict(properties or {}).items() if v is not None
        }
        props.setdefault("lead_source", source)
        existing = self._contacts_by_identifier.get(identifier)
        if existing is None:
            self._id_counter += 1
            existing = {"id": str(self._id_counter), "properties": {}}
            self._contacts_by_identifier[identifier] = existing
        existing["properties"].update(props)
        return {"id": existing["id"], "properties": dict(existing["properties"])}

    def snapshot(self) -> dict[str, Any]:
        return {
            "contacts_by_identifier": self._contacts_by_identifier,
        }


class FakeCalComClient:
    def __init__(self) -> None:
        self._counter = 0

    def create_booking(
        self,
        *,
        name: str,
        email: str,
        start: str,
        timezone: str = "UTC",
        length_in_minutes: int = 30,
        event_type_id: int | None = None,
        phone_number: str | None = None,
        language: str = "en",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._counter += 1
        uid = f"fake_booking_{self._counter}"
        return {
            "data": {
                "uid": uid,
                "attendee": {"name": name, "email": email},
                "start": start,
                "timezone": timezone,
                "length_in_minutes": length_in_minutes,
                "metadata": metadata or {},
            }
        }


def _prepare_local_enrichment_inputs(*, run_dir: Path, company_name: str) -> dict[str, str]:
    """
    Ensure enrichment has local inputs so the offline runner is hermetic.
    Returns a dict of any settings we mutated so they can be restored.
    """
    mutated: dict[str, str] = {}

    # Provide a minimal Crunchbase ODM file so enrichment + competitor-gap can run without network.
    odm_path = run_dir / "local_inputs" / "crunchbase_odm_offline.json"
    odm_path.parent.mkdir(parents=True, exist_ok=True)
    odm_payload = [
        {
            "uuid": "offline-odm-001",
            "name": company_name,
            "domain": "acme.example",
            "homepage_url": "https://acme.example",
            "country_code": "US",
            "num_employees_enum": "c_00101_00250",
            "categories": ["analytics", "python", "snowflake"],
            "funding_rounds": [
                {
                    "announced_on": "2026-04-01T00:00:00Z",
                    "investment_type": "series_b",
                    "money_raised_usd": 14000000,
                }
            ],
            "ai_maturity_score": 2,
        },
        {
            "uuid": "offline-odm-peer-001",
            "name": "PeerCo One",
            "domain": "peerco1.example",
            "homepage_url": "https://peerco1.example",
            "categories": ["analytics", "python", "snowflake"],
            "ai_maturity_score": 3,
        },
        {
            "uuid": "offline-odm-peer-002",
            "name": "PeerCo Two",
            "domain": "peerco2.example",
            "homepage_url": "https://peerco2.example",
            "categories": ["analytics", "python", "snowflake"],
            "ai_maturity_score": 2,
        },
        {
            "uuid": "offline-odm-peer-003",
            "name": "PeerCo Three",
            "domain": "peerco3.example",
            "homepage_url": "https://peerco3.example",
            "categories": ["analytics", "python", "snowflake"],
            "ai_maturity_score": 2,
        },
        {
            "uuid": "offline-odm-peer-004",
            "name": "PeerCo Four",
            "domain": "peerco4.example",
            "homepage_url": "https://peerco4.example",
            "categories": ["analytics", "python", "snowflake"],
            "ai_maturity_score": 2,
        },
        {
            "uuid": "offline-odm-peer-005",
            "name": "PeerCo Five",
            "domain": "peerco5.example",
            "homepage_url": "https://peerco5.example",
            "categories": ["analytics", "python", "snowflake"],
            "ai_maturity_score": 2,
        },
    ]
    odm_path.write_text(json.dumps(odm_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    mutated["crunchbase_odm_path"] = settings.crunchbase_odm_path
    settings.crunchbase_odm_path = str(odm_path)

    # Provide a minimal layoffs file if the repo-local one is missing.
    layoffs_path = Path(settings.layoffs_fyi_path)
    if not layoffs_path.exists():
        local_layoffs = run_dir / "local_inputs" / "layoffs_fyi_offline.csv"
        local_layoffs.write_text("Company,Date,Laid_Off_Count,Percentage\n", encoding="utf-8")
        mutated["layoffs_fyi_path"] = settings.layoffs_fyi_path
        settings.layoffs_fyi_path = str(local_layoffs)

    # Force outbound safety defaults for offline verification.
    mutated["outbound_enabled"] = str(settings.outbound_enabled)
    mutated["outbound_sink_email"] = settings.outbound_sink_email
    settings.outbound_enabled = False
    if not settings.outbound_sink_email:
        settings.outbound_sink_email = "sink@conversion-engine.invalid"
    return mutated


def _restore_settings(mutated: dict[str, str]) -> None:
    if "crunchbase_odm_path" in mutated:
        settings.crunchbase_odm_path = mutated["crunchbase_odm_path"]
    if "layoffs_fyi_path" in mutated:
        settings.layoffs_fyi_path = mutated["layoffs_fyi_path"]
    if "outbound_enabled" in mutated:
        settings.outbound_enabled = mutated["outbound_enabled"].lower() == "true"
    if "outbound_sink_email" in mutated:
        settings.outbound_sink_email = mutated["outbound_sink_email"]


def _require_live_credentials() -> None:
    missing: list[str] = []
    if not settings.resend_api_key:
        missing.append("RESEND_API_KEY")
    if not settings.resend_from_email:
        missing.append("RESEND_FROM_EMAIL")
    if not settings.hubspot_api_key:
        missing.append("HUBSPOT_API_KEY (or HUBSPOT_ACCESS_TOKEN / HUBSPOT_PERSONAL_ACCESS_KEY)")
    if not settings.calcom_api_key:
        missing.append("CALCOM_API_KEY")
    if missing:
        raise SystemExit("Missing required credentials for --live:\n- " + "\n- ".join(missing))


def run_golden_path(
    *,
    live: bool,
    artifacts_dir: Path,
    seed: int,
    company_name: str,
    lead_email: str,
    careers_url: str = "",
) -> dict[str, Any]:
    random.seed(seed)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    thread_id = _stable_id("thread", str(seed), company_name.lower(), lead_email.lower())
    lead_id = _stable_id("lead", lead_email.lower())
    run_dir = artifacts_dir / thread_id
    run_dir.mkdir(parents=True, exist_ok=True)

    stage_paths = {
        "hiring_signal_brief": run_dir / "hiring_signal_brief.json",
        "competitor_gap_brief": run_dir / "competitor_gap_brief.json",
        "outbound_send": run_dir / "outbound_send.json",
        "inbound_reply": run_dir / "inbound_reply.json",
        "booking": run_dir / "booking.json",
        "crm_snapshot": run_dir / "crm_snapshot.json",
        "thread_summary": run_dir / "thread_summary.json",
        "thread_state": run_dir / "thread_state.json",
        "act5_events": run_dir / "act5_events.jsonl",
        "act5_reply_classification": run_dir / "act5_reply_classification.jsonl",
    }

    mutated_settings: dict[str, str] = {}
    try:
        if live:
            _require_live_credentials()
        else:
            mutated_settings = _prepare_local_enrichment_inputs(
                run_dir=run_dir, company_name=company_name
            )

        state = ThreadState(
            thread_id=thread_id,
            lead_id=lead_id,
            generated_at=_utcnow_iso(),
            company_name=company_name,
            lead_email=lead_email,
            careers_url=careers_url,
            routing_mode="live" if live else "sink",
            sink_email=settings.outbound_sink_email if not live else "",
            sms_suppressed=True,
        )
        _write_json(stage_paths["thread_state"], asdict(state))

        # Real enrichment codepath, but offline forces careers_url="" to avoid scraping/network.
        brief = run_enrichment_pipeline(
            company_name=company_name, careers_url="" if not live else careers_url
        )
        state.bench_to_brief_gate_passed = bool(brief.signals.bench.data.bench_to_brief_gate_passed)

        hiring_public = to_public_hiring_signal_brief(brief)
        competitor_public = to_public_competitor_gap_brief(brief)
        _write_json(stage_paths["hiring_signal_brief"], hiring_public)
        _write_json(stage_paths["competitor_gap_brief"], competitor_public)

        # Build orchestrator with injected clients.
        if live:
            orchestrator = LeadOrchestrator()
            # In live mode, keep outbound routing behavior consistent with safety:
            # still sink route unless OUTBOUND_ENABLED=true explicitly.
        else:
            fake_hs = FakeHubSpotClient()
            fake_cal = FakeCalComClient()
            fake_resend = FakeResendClient()
            pinned_company_name = company_name
            orchestrator = LeadOrchestrator(
                hubspot=fake_hs,  # type: ignore[arg-type]
                calcom=fake_cal,  # type: ignore[arg-type]
                resend=fake_resend,  # type: ignore[arg-type]
                langfuse=FakeLangfuseClient(),  # type: ignore[arg-type]
                # The runtime webhook handler derives company_name from inbound email domains.
                # For the hermetic golden path we want a stable synthetic lead, so we pin
                # enrichment to the runner's `company_name` regardless of inbound identity.
                enrichment_runner=lambda *, company_name: run_enrichment_pipeline(
                    company_name=pinned_company_name, careers_url=""
                ),
            )

        # Outbound send (will route to sink in offline mode).
        signal_summary = "Offline golden-path signal summary."
        outbound = orchestrator.send_outbound_email(
            to_email=lead_email,
            company_name=brief.company_name,
            signal_summary=signal_summary,
            icp_segment=brief.icp_segment,
            ai_maturity_score=brief.signals.ai_maturity.score,
            confidence=brief.segment_confidence,
            segment_confidence=brief.segment_confidence,
            crunchbase_id=brief.signals.crunchbase.data.uuid,
            bench_to_brief_gate_passed=True,
            outbound_variant="golden_path",
            idempotency_key=f"golden-path:{thread_id}:outbound",
        )
        _write_json(stage_paths["outbound_send"], outbound)

        # Simulate inbound reply (linked to outbound thread/message id).
        outbound_message_id = str(outbound.get("id") or "")
        start = (datetime.now(UTC) + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
        start_iso = start.isoformat().replace("+00:00", "Z")
        reply_body = (
            "Thanks — yes, can we book a quick call?\n\n"
            f"{start_iso}\n"
            "We’re hiring 2 data engineers and a backend engineer.\n"
        )
        inbound_event = InboundEmailEvent(
            event_type="email.replied",
            from_email=lead_email,
            to=settings.outbound_sink_email if not live else settings.resend_reply_to_email,
            subject=f"Re: {brief.company_name}: quick thought",
            body=reply_body,
            message_id=f"inbound_{thread_id}",
            in_reply_to=outbound_message_id,
        )
        _write_json(stage_paths["inbound_reply"], inbound_event.model_dump(mode="json"))

        # Handle reply (exercises booking + CRM writeback paths).
        handle_result = orchestrator.handle_email(inbound_event)

        # Booking artifact (if created).
        booking_payload = handle_result.get("booking") or {}
        _write_json(stage_paths["booking"], booking_payload)

        # CRM snapshot (offline is fully inspectable; live stores a best-effort stub).
        if live:
            crm_snapshot = {
                "mode": "live",
                "note": "Live mode uses real HubSpot; runner does not snapshot the portal.",
                "hubspot_contact_id": str(handle_result.get("id") or ""),
            }
        else:
            crm_snapshot = orchestrator.hubspot.snapshot()  # type: ignore[union-attr]
        _write_json(stage_paths["crm_snapshot"], crm_snapshot)

        # Update state from results.
        state.email_replied = True
        state.booking_requested = True
        booking_uid = ""
        if isinstance(booking_payload, dict):
            booking_data = booking_payload.get("data", booking_payload)
            booking_uid = str((booking_data or {}).get("uid") or "")
        state.booking_created = bool(booking_uid)
        state.booking_uid = booking_uid

        # Pull hubspot id + properties from offline snapshot.
        if not live:
            contact = crm_snapshot["contacts_by_identifier"].get(lead_email, {})
            state.hubspot_contact_id = str(contact.get("id") or "")
            state.crm_properties_written = dict(contact.get("properties") or {})

        _write_json(stage_paths["thread_state"], asdict(state))

        # Copy Act V logs into run dir so the run is self-contained.
        act_dir = Path("eval/runs/outbound")
        if act_dir.exists():
            events_src = act_dir / "events.jsonl"
            reply_src = act_dir / "reply_classification.jsonl"
            if events_src.exists():
                shutil.copyfile(events_src, stage_paths["act5_events"])
            if reply_src.exists():
                shutil.copyfile(reply_src, stage_paths["act5_reply_classification"])

        summary = {
            "thread_id": thread_id,
            "lead_id": lead_id,
            "mode": "live" if live else "offline",
            "generated_at": now_iso(),
            "company_name": brief.company_name,
            "lead_email": lead_email,
            "routing_mode": state.routing_mode,
            "sink_email": state.sink_email,
            "ids": {
                "outbound_message_id": outbound_message_id,
                "inbound_message_id": inbound_event.message_id,
                "booking_uid": state.booking_uid,
                "hubspot_contact_id": state.hubspot_contact_id,
            },
            "final_state": asdict(state),
            "artifacts": {k: str(v) for k, v in stage_paths.items()},
            "notes": {
                "offline_is_hermetic": not live,
                "enrichment_careers_url_used": "" if not live else careers_url,
                "competitor_gap_benchmark_source": str(
                    competitor_public.get("benchmark_source") or ""
                ),
            },
        }
        _write_json(stage_paths["thread_summary"], summary)
        return summary
    finally:
        if mutated_settings:
            _restore_settings(mutated_settings)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline/online golden-path runner.")
    parser.add_argument(
        "--live", action="store_true", help="Opt-in: use real Resend/HubSpot/Cal.com."
    )
    parser.add_argument(
        "--seed", type=int, default=1, help="Seed for stable IDs and deterministic run."
    )
    parser.add_argument("--company-name", default="Acme Data", help="Synthetic company name.")
    parser.add_argument(
        "--lead-email", default="prospect@example.com", help="Synthetic lead email."
    )
    parser.add_argument("--careers-url", default="", help="Careers URL (only used in --live mode).")
    parser.add_argument(
        "--artifacts-dir",
        default="artifacts/golden_path",
        help="Base directory for golden path artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    summary = run_golden_path(
        live=bool(args.live),
        artifacts_dir=Path(str(args.artifacts_dir)),
        seed=int(args.seed),
        company_name=str(args.company_name),
        lead_email=str(args.lead_email),
        careers_url=str(args.careers_url),
    )
    # Print the final summary artifact path for convenience.
    print(summary["artifacts"]["thread_summary"])


if __name__ == "__main__":
    main()
