import asyncio
import uuid

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from travel_agent import db
from travel_agent.config import settings
from travel_agent.orchestrator import TurnResult, handle_turn
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, TripBrief
from travel_agent.tools.amadeus_client import AmadeusClient

app = FastAPI(title="Travel Agent")

_amadeus = AmadeusClient(
    client_id=settings.amadeus_client_id,
    client_secret=settings.amadeus_client_secret,
    base_url=settings.amadeus_base_url,
)


def _anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


class MessageRequest(BaseModel):
    content: str


class SessionResponse(BaseModel):
    session_id: str


class TurnResponse(BaseModel):
    reply: str
    trip_brief: TripBrief
    flight_candidates: list[FlightCandidate]
    hotel_candidates: list[HotelCandidate]
    itinerary: list[ItineraryDay]
    warnings: list[str]


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session_endpoint():
    session_id = str(uuid.uuid4())
    await asyncio.to_thread(db.create_session, session_id)
    return SessionResponse(session_id=session_id)


@app.post("/sessions/{session_id}/messages", response_model=TurnResponse)
async def post_message_endpoint(session_id: str, body: MessageRequest):
    state = await asyncio.to_thread(db.load_session, session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")

    result: TurnResult = await handle_turn(
        client=_anthropic_client(), amadeus=_amadeus, session=state, user_message=body.content
    )

    await asyncio.to_thread(
        db.save_session,
        session_id,
        messages=state.messages + [_user_and_reply_messages(body.content, result.reply)][0],
        trip_brief=result.trip_brief,
        flight_candidates=result.flight_candidates,
        hotel_candidates=result.hotel_candidates,
        itinerary=result.itinerary,
    )

    return TurnResponse(
        reply=result.reply,
        trip_brief=result.trip_brief,
        flight_candidates=result.flight_candidates,
        hotel_candidates=result.hotel_candidates,
        itinerary=result.itinerary,
        warnings=result.warnings,
    )


def _user_and_reply_messages(user_content: str, reply: str):
    from travel_agent.schemas import Message

    return [Message(role="user", content=user_content), Message(role="assistant", content=reply)]
