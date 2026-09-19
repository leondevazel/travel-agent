from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession
from sqlalchemy.orm import sessionmaker

from travel_agent.config import settings
from travel_agent.models import Base, TripSession
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief

_engine = None
_SessionLocal = None


def init_engine(database_url: str | None = None):
    global _engine, _SessionLocal
    url = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def _session() -> SASession:
    if _SessionLocal is None:
        init_engine()
    return _SessionLocal()


@dataclass
class TripSessionState:
    id: str
    messages: list[Message]
    trip_brief: TripBrief | None
    flight_candidates: list[FlightCandidate]
    hotel_candidates: list[HotelCandidate]
    itinerary: list[ItineraryDay]


def create_session(session_id: str) -> None:
    with _session() as db:
        db.add(
            TripSession(
                id=session_id,
                messages=[],
                trip_brief=None,
                flight_candidates=[],
                hotel_candidates=[],
                itinerary=[],
            )
        )
        db.commit()


def load_session(session_id: str) -> TripSessionState | None:
    with _session() as db:
        row = db.get(TripSession, session_id)
        if row is None:
            return None
        return TripSessionState(
            id=row.id,
            messages=[Message(**m) for m in row.messages],
            trip_brief=TripBrief(**row.trip_brief) if row.trip_brief else None,
            flight_candidates=[FlightCandidate(**c) for c in row.flight_candidates],
            hotel_candidates=[HotelCandidate(**c) for c in row.hotel_candidates],
            itinerary=[ItineraryDay(**d) for d in row.itinerary],
        )


def save_session(
    session_id: str,
    *,
    messages: list[Message],
    trip_brief: TripBrief,
    flight_candidates: list[FlightCandidate],
    hotel_candidates: list[HotelCandidate],
    itinerary: list[ItineraryDay],
) -> None:
    with _session() as db:
        row = db.get(TripSession, session_id)
        row.messages = [m.model_dump(mode="json") for m in messages]
        row.trip_brief = trip_brief.model_dump(mode="json")
        row.flight_candidates = [c.model_dump(mode="json") for c in flight_candidates]
        row.hotel_candidates = [c.model_dump(mode="json") for c in hotel_candidates]
        row.itinerary = [d.model_dump(mode="json") for d in itinerary]
        db.commit()
