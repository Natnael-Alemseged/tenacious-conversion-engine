# Cal.com Self-Hosted Setup

Notes on running Act 2 e2e against the self-hosted Cal.com Docker image.

## Container

The project uses `calcom/cal.com:v6.2.0-arm` which ships **only** the Next.js
web app (`@calcom/web`). The separate `@calcom/api` service that handles
`/v2/bookings` (port 5555) is not included. All booking calls therefore use
the internal Next.js route `/api/book/event` instead.

```
calcom-app      calcom/cal.com:v6.2.0-arm   port 3000
calcom-postgres postgres:15-alpine           port 5433
```

## .env settings

```
CALCOM_BASE_URL=http://localhost:3000/api
CALCOM_EVENT_TYPE_ID=2
CALCOM_USERNAME=natnael
CALCOM_API_KEY=cal_live_<generated — see below>
```

## One-time database setup

The free self-hosted image restricts API key creation in the UI. Generate one
directly in Postgres and also seed the availability schedule (required for
the booking route to find a free slot).

### 1. Generate an API key

```bash
python3 -c "
import secrets, hashlib
raw = 'cal_live_' + secrets.token_hex(32)
hashed = hashlib.sha256(raw.encode()).hexdigest()
print('KEY:', raw)
print('HASH:', hashed)
"
```

Insert into the database (replace `<hash>` with the HASH output above):

```bash
psql "postgresql://calcom:calcom@localhost:5433/calcom" -c "
INSERT INTO \"ApiKey\" (id, \"userId\", note, \"hashedKey\")
VALUES ('conversion-engine-key', 1, 'conversion-engine e2e', '<hash>');
"
```

Set the KEY value as `CALCOM_API_KEY` in `.env`.

### 2. Create availability schedule

```bash
psql "postgresql://calcom:calcom@localhost:5433/calcom" <<'SQL'
INSERT INTO "Schedule" ("userId", name, "timeZone")
VALUES (1, 'Default', 'Africa/Addis_Ababa');

INSERT INTO "Availability" ("userId", "scheduleId", days, "startTime", "endTime")
VALUES (1, 1, '{1,2,3,4,5}', '09:00:00', '17:00:00');

UPDATE users SET "defaultScheduleId" = 1 WHERE id = 1;

UPDATE "EventType" SET "scheduleId" = 1 WHERE id = 2;

INSERT INTO "_user_eventtype" ("A", "B") VALUES (1, 2);
SQL
```

Days array uses JavaScript `Date.getDay()` convention: 0 = Sunday, 1 = Monday … 6 = Saturday.
`{1,2,3,4,5}` = Monday–Friday.

Availability times are in the schedule's timezone (`Africa/Addis_Ababa`, UTC+3):
- 09:00 EAT = 06:00 UTC
- 17:00 EAT = 14:00 UTC

## Testing the booking endpoint

Use a weekday slot within 06:00–14:00 UTC:

```bash
curl -s -X POST https://<ngrok-url>/bookings/discovery-call \
  -H "Content-Type: application/json" \
  -d '{
    "attendee_name": "Natnael Alemseged",
    "attendee_email": "natnaela@10academy.org",
    "start": "2026-04-27T13:00:00Z",
    "timezone": "Africa/Addis_Ababa",
    "length_in_minutes": 30
  }'
```

Expected response includes `"uid"` and `"status": "ACCEPTED"`. The booking is
then written back to HubSpot via `booking_crm_writeback.py`.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `404 /v2/bookings` | API service not running | Already handled — client uses `/book/event` |
| `500 /api/v2/bookings` | API service not running (proxied to port 5555) | Same as above |
| `no_available_users_found_error` | No schedule / wrong day of week | Run the DB setup above; use a weekday slot |
| `409 no_available_users_found_error` | Slot already booked | Use a different time |
| Missing `uid` in response | API key placeholder not replaced | Set real `CALCOM_API_KEY` in `.env` |
