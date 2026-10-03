from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from nonprofit_rooms import InfraiError, InfraiRealtime, NonprofitEvent, publish_event, route_event


class EventRequest(BaseModel):
    organization_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    kind: Literal["donor_receipt", "volunteer_reminder", "campaign_report"]
    subject_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    effective_on: date
    account_id: str = Field(min_length=1)


class TokenRequest(BaseModel):
    client_id: str = Field(min_length=1)
    event: EventRequest


app = FastAPI(title="Nonprofit realtime rooms")


def realtime_client() -> InfraiRealtime:
    return InfraiRealtime()


def event_from_request(request: EventRequest) -> NonprofitEvent:
    return NonprofitEvent(**request.model_dump(exclude={"account_id"}))


def client_error(exc: InfraiError) -> HTTPException:
    status = exc.status if 400 <= exc.status < 500 else 502
    return HTTPException(status_code=status, detail={"code": exc.code, "error": exc.detail})


@app.post("/events", status_code=202)
def send_event(request: EventRequest) -> dict[str, str]:
    try:
        delivery = publish_event(realtime_client(), event_from_request(request), request.account_id)
    except InfraiError as exc:
        raise client_error(exc) from exc
    return {"channel": delivery.channel, "event": delivery.event, "status": "published"}


@app.post("/subscriber-tokens")
def subscriber_token(request: TokenRequest) -> dict[str, object]:
    event = event_from_request(request.event)
    channel = route_event(event).channel
    try:
        token = realtime_client().issue_token(request.client_id, [channel])
    except InfraiError as exc:
        raise client_error(exc) from exc
    return {"channel": channel, "token": token}


@app.get("/rooms/{channel:path}/presence")
def room_presence(channel: str) -> dict[str, object]:
    try:
        members = realtime_client().presence(channel)
    except InfraiError as exc:
        raise client_error(exc) from exc
    return {"channel": channel, "presence": members}
