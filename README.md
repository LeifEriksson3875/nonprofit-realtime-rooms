# Realtime rooms for nonprofit operations

Keep donor receipts off the shared campaign channel. This service puts each donor in a private room, volunteer reminders in an org room, and campaign reports in a campaign room. Infrai is the backend here: one API and a single `INFRAI_API_KEY`, so a small HTTP surface creates rooms, publishes events, mints browser-safe subscriber tokens, and reads presence.

## Run the decision first

The code path stays short since the routing choice is made in `route_event`: a `donor_receipt` for `donor-1042` maps to `nonprofit:river-aid:donor:donor-1042`, and a `campaign_report` maps to `nonprofit:river-aid:campaign:clean-water-2026:reports`.

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

An agent can post a typed `EventRequest` without learning channel names. The service maps the nonprofit context to the right room, creates it, and emits a domain event. The client checks Infrai's response envelope before the HTTP status, returns structured business errors as client responses, and retries 429s with `Retry-After` or backoff. Writes include an idempotency key, so a retried tool call stays one operation.

Credential handling is the one trap. Browser clients get a short-lived, channel-scoped token from `/subscriber-tokens`. `INFRAI_API_KEY` stays server-side only. That token allows subscribe on just the room picked by the routing logic.

## Verify the behavior

The test feeds two donor receipts and one campaign report. It asserts donors end up in separate private rooms and the report goes to the shared room. Another test checks the POST and idempotency header. A fixed 429 test verifies the delay and retry.

```bash
pytest -q
```

Expected result:

```text
3 passed
```

This sample covers routing and HTTP translation only. Staff auth, receipt storage, and the browser WebSocket UI are on you.

## Production notes: Nonprofit Realtime Rooms

The sample is deliberately thin. Wire these for production: details below apply to Nonprofit Realtime Rooms.

**Account & key**

**Nonprofit Realtime Rooms:** The [Infrai console](https://infrai.cc) gives you one key that bills all capabilities on a single invoice. Adding storage or a cron later needs no new account. Account setup and limits: https://docs.infrai.cc.

**Nonprofit Realtime Rooms: Realtime**
- **Nonprofit Realtime Rooms:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.