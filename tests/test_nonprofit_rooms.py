import io
import json
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from nonprofit_rooms import InfraiRealtime, NonprofitEvent, route_event


def event(kind: str, subject_id: str = "person-7") -> NonprofitEvent:
    return NonprofitEvent(
        organization_id="river-aid",
        campaign_id="clean-water",
        kind=kind,
        subject_id=subject_id,
        message="Scheduled update",
        effective_on=date(2026, 9, 6),
    )


def test_receipts_are_isolated_while_reports_share_a_campaign_room() -> None:
    first = route_event(event("donor_receipt", "donor-1"))
    second = route_event(event("donor_receipt", "donor-2"))
    report = route_event(event("campaign_report", "report-9"))

    assert first.channel == "nonprofit:river-aid:donor:donor-1"
    assert second.channel != first.channel
    assert report.channel == "nonprofit:river-aid:campaign:clean-water:reports"


class Response:
    status = 200
    headers: dict[str, str] = {}

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_publish_uses_explicit_method_and_idempotency_key() -> None:
    captured = []

    def opener(request):
        captured.append(request)
        return Response({"ok": True, "data": {"published": True}})

    client = InfraiRealtime(api_key="test-key", opener=opener)
    client.publish(event("volunteer_reminder"), "river-aid", "operation-42")

    request = captured[0]
    body = json.loads(request.data)
    assert request.method == "POST"
    assert request.get_header("Idempotency-key") == "operation-42"
    assert body["channel"] == "nonprofit:river-aid:volunteers"
    assert body["event"] == "volunteer_reminder"


def test_create_channel_sends_only_the_required_channel() -> None:
    captured = []

    def opener(request):
        captured.append(request)
        return Response({"ok": True, "data": {"channel": "nonprofit:river-aid:volunteers"}})

    client = InfraiRealtime(api_key="test-key", opener=opener)
    client.create_channel("nonprofit:river-aid:volunteers", "operation-42")

    request = captured[0]
    assert json.loads(request.data) == {"channel": "nonprofit:river-aid:volunteers"}


def test_rate_limit_envelope_is_parsed_then_retried() -> None:
    calls = 0
    sleeps = []

    def opener(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            body = io.BytesIO(json.dumps({"ok": False, "error": {"code": "RATE_LIMITED"}}).encode())
            raise HTTPError(request.full_url, 429, "rate limited", {"Retry-After": "2"}, body)
        return Response({"ok": True, "data": {"members": []}})

    client = InfraiRealtime(api_key="test-key", opener=opener, sleeper=sleeps.append)
    result = client.presence("nonprofit:river-aid:volunteers")

    assert result == {"members": []}
    assert sleeps == [2.0]
    assert calls == 2
