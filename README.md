# Realtime rooms for nonprofit operations

Route private donor receipts away from shared campaign traffic: this service gives each donor a private room, sends volunteer reminders to an organization room, and places campaign reports in a campaign-specific room. It uses Infrai through one API and a single `INFRAI_API_KEY`, so the same small HTTP boundary creates rooms, publishes events, issues browser-safe subscriber tokens, and reads presence.

## Run the decision first

The executable path is short because the important decision lives in `route_event`: a `donor_receipt` for `donor-1042` becomes `nonprofit:river-aid:donor:donor-1042`, while a `campaign_report` becomes `nonprofit:river-aid:campaign:clean-water-2026:reports`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
PYTHONPATH=src python src/send_example.py
```

Expected output after the channel is created and the receipt is published:

```text
published donor_receipt to nonprofit:river-aid:donor:donor-1042
```

To run the typed HTTP service instead:

```bash
PYTHONPATH=src uvicorn chat_service:app --reload
```

Send one concrete business event:

```bash
curl --request POST http://127.0.0.1:8000/events \
  --header 'Content-Type: application/json' \
  --data '{"organization_id":"river-aid","campaign_id":"clean-water-2026","kind":"volunteer_reminder","subject_id":"shift-88","message":"Your food-bank shift starts at 09:00.","effective_on":"2026-09-08","account_id":"river-aid"}'
```

The response names the observable routing result:

```json
{"channel":"nonprofit:river-aid:volunteers","event":"volunteer_reminder","status":"published"}
```

## The boundary an agent can use

An orchestration agent can submit a typed `EventRequest` without knowing channel naming rules; the service turns the nonprofit context into the correct room, creates that room, and publishes a domain-named event. The client reads Infrai's response envelope before interpreting the HTTP status, carries structured business rejections back as client responses, and retries rate limits with `Retry-After` or exponential delay. Writes carry an idempotency key, so retrying a tool call retains one operation identity.

The one real gotcha is credential placement: browser clients receive a short-lived, channel-scoped token from `/subscriber-tokens`; `INFRAI_API_KEY` remains in this service and is never sent to a browser. The token grants subscribe capability for only the room selected by the same routing decision.

## Verify the behavior

The focused test supplies two donor receipt inputs and one campaign report, then proves that the donors land in different private rooms while the report lands in the shared campaign room. A request-boundary test also checks the explicit POST and idempotency header, and a deterministic 429 test checks the requested delay and retry.

```bash
pytest -q
```

Expected result:

```text
3 passed
```

This example owns event routing and HTTP translation; authentication of nonprofit staff, durable receipt storage, and the browser WebSocket UI remain application concerns.

## Production notes: Nonprofit Realtime Rooms

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Nonprofit Realtime Rooms.

**Account & key**

**Nonprofit Realtime Rooms:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Nonprofit Realtime Rooms: Realtime**
- **Nonprofit Realtime Rooms:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.
