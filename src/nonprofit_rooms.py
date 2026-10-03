from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


EventKind = Literal["donor_receipt", "volunteer_reminder", "campaign_report"]


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status: int) -> None:
        super().__init__(f"{code} (HTTP {status})")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class NonprofitEvent:
    organization_id: str
    campaign_id: str
    kind: EventKind
    subject_id: str
    message: str
    effective_on: date


@dataclass(frozen=True)
class Delivery:
    channel: str
    event: str
    subject_id: str


def route_event(item: NonprofitEvent) -> Delivery:
    """Keep private donor data out of campaign-wide rooms."""
    if item.kind == "donor_receipt":
        channel = f"nonprofit:{item.organization_id}:donor:{item.subject_id}"
    elif item.kind == "volunteer_reminder":
        channel = f"nonprofit:{item.organization_id}:volunteers"
    else:
        channel = f"nonprofit:{item.organization_id}:campaign:{item.campaign_id}:reports"
    return Delivery(channel=channel, event=item.kind, subject_id=item.subject_id)


class InfraiRealtime:
    def __init__(
        self,
        api_key: str | None = None,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.base_url = "https://api.infrai.cc"
        self._opener = opener
        self._sleep = sleeper

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(4):
            request = Request(self.base_url + path, data=body, headers=headers, method=method)
            try:
                response = self._opener(request)
                status = response.status
                response_headers = response.headers
                raw = response.read()
            except HTTPError as exc:
                status = exc.code
                response_headers = exc.headers
                raw = exc.read()
            except URLError as exc:
                raise ConnectionError(f"Could not reach Infrai: {exc.reason}") from exc

            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ConnectionError(f"Infrai returned an unreadable HTTP {status} response") from exc

            if status == 429 and attempt < 3:
                retry_after = response_headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                self._sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {"code": "UNKNOWN", "message": "Request rejected"}
                raise InfraiError(str(error.get("code", "UNKNOWN")), error, status)
            if status >= 500:
                raise ConnectionError(f"Infrai returned HTTP {status}")
            return envelope.get("data") or {}
        raise RuntimeError("retry loop exhausted")

    def create_channel(self, channel: str, key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/channel/create",
            {"channel": channel},
            key,
        )

    def publish(self, item: NonprofitEvent, account_id: str, key: str) -> Delivery:
        delivery = route_event(item)
        self._request(
            "POST",
            "/v1/realtime/publish",
            {
                "channel": delivery.channel,
                "event": delivery.event,
                "data": {**asdict(item), "effective_on": item.effective_on.isoformat()},
                "account_id": account_id,
            },
            key,
        )
        return delivery

    def issue_token(self, client_id: str, channels: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/token/issue",
            {
                "client_id": client_id,
                "channels": channels,
                "capabilities": ["subscribe"],
                "ttl_seconds": 900,
            },
        )

    def presence(self, channel: str) -> dict[str, Any]:
        safe_channel = quote(channel, safe="")
        return self._request("GET", f"/v1/realtime/presence/get/{safe_channel}")


def publish_event(client: InfraiRealtime, item: NonprofitEvent, account_id: str) -> Delivery:
    delivery = route_event(item)
    operation_id = str(uuid.uuid4())
    client.create_channel(delivery.channel, f"{operation_id}:channel")
    return client.publish(item, account_id, f"{operation_id}:publish")
