"""One-time setup: create all custom contact properties required by the conversion engine.

Run once against your HubSpot Developer Sandbox:
    uv run python scripts/setup_hubspot_properties.py

Requires HUBSPOT_API_KEY in .env (the private app token from your HubSpot sandbox).
"""

from __future__ import annotations

import sys

import httpx

from agent.core.config import settings

BASE = "https://api.hubapi.com"

CUSTOM_PROPERTIES = [
    # Enrichment / firmographics
    {
        "name": "crunchbase_id",
        "label": "Crunchbase ID",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Crunchbase record ID for this lead (required for grading audit).",
    },
    {
        "name": "icp_segment",
        "label": "ICP Segment",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Tenacious ICP segment: 1=funded, 2=restructuring, 3=leadership, 4=gap.",
    },
    {
        "name": "ai_maturity_score",
        "label": "AI Maturity Score",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "AI readiness score 0-3 from public signal analysis.",
    },
    {
        "name": "enrichment_timestamp",
        "label": "Enrichment Timestamp",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "ISO-8601 timestamp of last enrichment pipeline run.",
    },
    {
        "name": "enrichment_summary",
        "label": "Enrichment Summary",
        "type": "string",
        "fieldType": "textarea",
        "groupName": "contactinformation",
        "description": "Hiring signal brief summary (funding, job velocity, layoffs, leadership).",
    },
    # Discovery call / Cal.com
    {
        "name": "discovery_call_booked",
        "label": "Discovery Call Booked",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "true/false — whether a discovery call has been booked via Cal.com.",
    },
    {
        "name": "discovery_call_start",
        "label": "Discovery Call Start",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "ISO-8601 start time of the booked discovery call.",
    },
    {
        "name": "discovery_call_booking_uid",
        "label": "Discovery Call Booking UID",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Cal.com booking UID for the discovery call.",
    },
    {
        "name": "discovery_call_booked_at",
        "label": "Discovery Call Booked At",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "ISO-8601 timestamp of when the booking was created.",
    },
    # Outbound tracking
    {
        "name": "last_outbound_email_at",
        "label": "Last Outbound Email At",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "ISO-8601 timestamp of last outbound email sent.",
    },
    {
        "name": "last_outbound_sms_at",
        "label": "Last Outbound SMS At",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "ISO-8601 timestamp of last outbound SMS sent.",
    },
    {
        "name": "last_outbound_mode",
        "label": "Last Outbound Mode",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "live or sink — outbound routing mode at time of last send.",
    },
    {
        "name": "last_outbound_draft",
        "label": "Last Outbound Was Draft",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "true/false — whether the last outbound was marked draft.",
    },
    {
        "name": "last_outbound_intended_to",
        "label": "Last Outbound Intended To",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Original intended recipient of last outbound (before sink routing).",
    },
    {
        "name": "last_outbound_routed_to",
        "label": "Last Outbound Routed To",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Actual recipient of last outbound (may be sink address).",
    },
    # Inbound email
    {
        "name": "last_email_reply_at",
        "label": "Last Email Reply At",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "ISO-8601 timestamp of last inbound email reply received.",
    },
    {
        "name": "last_email_subject",
        "label": "Last Email Subject",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Subject line of the last email received from this contact.",
    },
    {
        "name": "email_replied",
        "label": "Email Replied",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "true/false — contact has replied to at least one email.",
    },
    # Inbound SMS
    {
        "name": "last_sms_reply_text",
        "label": "Last SMS Reply Text",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Text of the last inbound SMS from this contact (first 255 chars).",
    },
    {
        "name": "sms_replied",
        "label": "SMS Replied",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "true/false — contact has replied to at least one SMS.",
    },
    # Email bounce
    {
        "name": "email_bounce_type",
        "label": "Email Bounce Type",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "Type of email bounce (hard_bounce, soft_bounce, etc.).",
    },
    {
        "name": "email_bounced_at",
        "label": "Email Bounced At",
        "type": "string",
        "fieldType": "text",
        "groupName": "contactinformation",
        "description": "ISO-8601 timestamp of last email bounce event.",
    },
]


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.hubspot_api_key}",
        "Content-Type": "application/json",
    }


def get_existing_properties(client: httpx.Client) -> set[str]:
    r = client.get(f"{BASE}/crm/v3/properties/contacts")
    r.raise_for_status()
    return {p["name"] for p in r.json().get("results", [])}


def create_property(client: httpx.Client, prop: dict) -> str:
    r = client.post(f"{BASE}/crm/v3/properties/contacts", json=prop)
    if r.status_code == 409:
        return "already_exists"
    r.raise_for_status()
    return "created"


def main() -> None:
    if not settings.hubspot_api_key:
        print("ERROR: HUBSPOT_API_KEY is not set in .env")
        sys.exit(1)

    with httpx.Client(headers=_headers(), timeout=15.0) as client:
        print("Fetching existing contact properties...")
        existing = get_existing_properties(client)
        print(f"  Found {len(existing)} existing properties.\n")

        created = skipped = failed = 0
        for prop in CUSTOM_PROPERTIES:
            name = prop["name"]
            if name in existing:
                print(f"  SKIP    {name} (already exists)")
                skipped += 1
                continue
            status = create_property(client, prop)
            if status == "created":
                print(f"  CREATE  {name}")
                created += 1
            elif status == "already_exists":
                print(f"  SKIP    {name} (409 conflict)")
                skipped += 1
            else:
                print(f"  FAIL    {name}")
                failed += 1

    print(f"\nDone. created={created}  skipped={skipped}  failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
