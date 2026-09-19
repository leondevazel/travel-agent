# Travel Agent Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the multi-agent travel planning backend: a FastAPI orchestrator that runs a Planner agent to maintain a structured trip brief, diffs it turn-to-turn to decide which specialist agents (Flight, Hotel, Itinerary) actually need to re-run, executes the independent ones in parallel, and persists full session state to Postgres.

**Architecture:** Each agent is an isolated Claude tool-use loop (`agents/base.py`) over a focused system prompt and a small tool set (Amadeus flight/hotel search, Open-Meteo weather, Claude's hosted web search). The orchestrator is a pure coordination layer: it never calls Claude or Amadeus directly, only the agent functions, and its one piece of real logic is the brief-diff that decides which agents to skip.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (sync engine, JSON columns, SQLite in tests / Postgres in prod), Pydantic v2, `anthropic` SDK (`AsyncAnthropic`), `httpx.AsyncClient` for Amadeus + Open-Meteo, pytest + pytest-asyncio + respx for mocked-HTTP tests.

**Spec:** [docs/superpowers/specs/2026-09-19-travel-agent-design.md](../specs/2026-09-19-travel-agent-design.md)

## Global Constraints

- Never simulate or execute real bookings/payments — the itinerary is the deliverable (spec §7).
- On Amadeus API failure or rate limit, fall back to a cached/prior result or a clear "couldn't fetch live prices right now" message — never silently fabricate a price (spec §5).
- If one specialist agent times out during a parallel run, return a partial itinerary from the agents that did complete rather than failing the whole turn (spec §5).
- Only re-invoke the specialist agent(s) whose relevant inputs actually changed between turns (spec §2).
- Log per-agent latency, cost per completed trip plan, and API failure rate — real measured numbers, not estimates (spec §6).
- Model for all agent calls: `claude-sonnet-5`.

---

## File Structure

```
travel-agent/
  pyproject.toml
  .env.example
  logs/.gitkeep
  travel_agent/
    __init__.py
    config.py            # Settings (env vars)
    schemas.py            # Pydantic: Message, TripBrief, FlightCandidate, HotelCandidate, ItineraryDay
    diff.py                # diff_trip_brief() — the "only re-run what changed" logic
    models.py              # SQLAlchemy TripSession ORM model
    db.py                   # engine/session setup + create/load/save session
    metrics.py               # record_agent_call() -> logs/metrics.jsonl
    orchestrator.py          # handle_turn() — ties everything together
    main.py                  # FastAPI app: POST /sessions, POST /sessions/{id}/messages
    agents/
      __init__.py
      base.py                # run_agent_loop() — shared Claude tool-use loop
      planner.py             # run_planner_agent()
      flight_agent.py         # run_flight_agent()
      hotel_agent.py           # run_hotel_agent()
      itinerary_agent.py       # run_itinerary_agent()
    tools/
      __init__.py
      amadeus_client.py        # AmadeusClient — real flight + hotel search
      weather_client.py         # get_daily_summary() — Open-Meteo, no API key needed
  tests/
    conftest.py
    test_schemas_and_diff.py
    test_db.py
    test_amadeus_client.py
    test_weather_client.py
    test_agent_base.py
    test_planner_agent.py
    test_flight_hotel_agents.py
    test_itinerary_agent.py
    test_metrics.py
    test_orchestrator.py
    test_main.py
```

---

### Task 1: Project Scaffolding + Schemas + Diff Logic

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `logs/.gitkeep`
- Create: `travel_agent/__init__.py`
- Create: `travel_agent/config.py`
- Create: `travel_agent/schemas.py`
- Create: `travel_agent/diff.py`
- Test: `tests/test_schemas_and_diff.py`

**Interfaces:**
- Produces: `Message(role, content)`, `TripBrief(destination, origin, start_date, end_date, budget_usd, interests, pace)`, `FlightCandidate(carrier, price_usd, departure_time, arrival_time, origin, destination, stops)`, `HotelCandidate(name, price_usd_per_night, rating, address)`, `ItineraryDay(day_number, date, activities, notes)` — all Pydantic `BaseModel`s in `travel_agent.schemas`.
- Produces: `diff_trip_brief(old: TripBrief | None, new: TripBrief) -> set[str]` in `travel_agent.diff`, returning a subset of `{"flight", "hotel", "itinerary"}`.
- Produces: `settings` (a `Settings` instance) in `travel_agent.config` with fields `anthropic_api_key`, `amadeus_client_id`, `amadeus_client_secret`, `amadeus_base_url`, `database_url`, `metrics_log_path`.

- [ ] **Step 1: Create project scaffolding**

`pyproject.toml`:

```toml
[project]
name = "travel-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "anthropic>=0.40",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["travel_agent"]
```

`.env.example`:

```
ANTHROPIC_API_KEY=sk-ant-...
AMADEUS_CLIENT_ID=...
AMADEUS_CLIENT_SECRET=...
AMADEUS_BASE_URL=https://test.api.amadeus.com
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/travel_agent
METRICS_LOG_PATH=logs/metrics.jsonl
```

Create empty `logs/.gitkeep` and empty `travel_agent/__init__.py`.

`travel_agent/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_base_url: str = "https://test.api.amadeus.com"
    database_url: str = "sqlite:///./travel_agent.db"
    metrics_log_path: str = "logs/metrics.jsonl"


settings = Settings()
```

Install the project in editable mode with dev deps:

```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing tests for schemas and diff logic**

`tests/test_schemas_and_diff.py`:

```python
import datetime

from travel_agent.diff import diff_trip_brief
from travel_agent.schemas import (
    FlightCandidate,
    HotelCandidate,
    ItineraryDay,
    Message,
    TripBrief,
)


def test_trip_brief_defaults_to_empty():
    brief = TripBrief()
    assert brief.destination is None
    assert brief.interests == []
    assert brief.pace is None


def test_flight_candidate_round_trips():
    c = FlightCandidate(
        carrier="KE",
        price_usd=812.50,
        departure_time="2026-11-01T09:00:00",
        arrival_time="2026-11-01T15:30:00",
        origin="ICN",
        destination="CDG",
        stops=0,
    )
    assert c.price_usd == 812.50


def test_hotel_candidate_round_trips():
    h = HotelCandidate(
        name="Hotel Lumiere",
        price_usd_per_night=180.0,
        rating=4.3,
        address="12 Rue de Rivoli, Paris",
    )
    assert h.rating == 4.3


def test_itinerary_day_round_trips():
    d = ItineraryDay(
        day_number=2,
        date=datetime.date(2026, 11, 2),
        activities=["Louvre", "Seine river walk"],
        notes="Loose pace, one museum only",
    )
    assert d.day_number == 2


def test_message_rejects_unknown_role():
    import pydantic
    import pytest

    with pytest.raises(pydantic.ValidationError):
        Message(role="system", content="hi")


def _brief(**overrides):
    base = dict(
        destination="Paris",
        origin="ICN",
        start_date=datetime.date(2026, 11, 1),
        end_date=datetime.date(2026, 11, 5),
        budget_usd=2000.0,
        interests=["art", "food"],
        pace="balanced",
    )
    base.update(overrides)
    return TripBrief(**base)


def test_diff_first_run_reruns_everything():
    agents = diff_trip_brief(None, _brief())
    assert agents == {"flight", "hotel", "itinerary"}


def test_diff_no_change_reruns_nothing():
    old = _brief()
    new = _brief()
    assert diff_trip_brief(old, new) == set()


def test_diff_pace_change_reruns_itinerary_only():
    old = _brief(pace="balanced")
    new = _brief(pace="relaxed")
    assert diff_trip_brief(old, new) == {"itinerary"}


def test_diff_interests_change_reruns_itinerary_only():
    old = _brief(interests=["art"])
    new = _brief(interests=["art", "hiking"])
    assert diff_trip_brief(old, new) == {"itinerary"}


def test_diff_destination_change_reruns_everything():
    old = _brief(destination="Paris")
    new = _brief(destination="Tokyo")
    assert diff_trip_brief(old, new) == {"flight", "hotel", "itinerary"}


def test_diff_budget_change_reruns_everything():
    old = _brief(budget_usd=2000.0)
    new = _brief(budget_usd=1200.0)
    assert diff_trip_brief(old, new) == {"flight", "hotel", "itinerary"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_schemas_and_diff.py -v`
Expected: FAIL / collection error — `travel_agent.schemas` and `travel_agent.diff` do not exist yet.

- [ ] **Step 4: Implement schemas and diff logic**

`travel_agent/schemas.py`:

```python
from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TripBrief(BaseModel):
    destination: str | None = None
    origin: str | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    budget_usd: float | None = None
    interests: list[str] = Field(default_factory=list)
    pace: Literal["relaxed", "balanced", "packed"] | None = None


class FlightCandidate(BaseModel):
    carrier: str
    price_usd: float
    departure_time: str
    arrival_time: str
    origin: str
    destination: str
    stops: int


class HotelCandidate(BaseModel):
    name: str
    price_usd_per_night: float
    rating: float | None = None
    address: str


class ItineraryDay(BaseModel):
    day_number: int
    date: datetime.date
    activities: list[str]
    notes: str = ""
```

`travel_agent/diff.py`:

```python
from travel_agent.schemas import TripBrief

CORE_FIELDS = ("destination", "origin", "start_date", "end_date", "budget_usd")
ITINERARY_FIELDS = ("interests", "pace")


def diff_trip_brief(old: TripBrief | None, new: TripBrief) -> set[str]:
    """Return which specialist agents need to re-run given the brief change.

    Destination/origin/dates/budget affect flight and hotel search directly,
    so a change to any of them reruns all three agents (itinerary depends on
    flight/hotel results). Interests/pace only affect how the itinerary is
    composed, so they rerun the itinerary agent alone.
    """
    if old is None:
        return {"flight", "hotel", "itinerary"}

    core_changed = any(getattr(old, f) != getattr(new, f) for f in CORE_FIELDS)
    itinerary_changed = any(getattr(old, f) != getattr(new, f) for f in ITINERARY_FIELDS)

    agents: set[str] = set()
    if core_changed:
        agents |= {"flight", "hotel", "itinerary"}
    elif itinerary_changed:
        agents.add("itinerary")
    return agents
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_schemas_and_diff.py -v`
Expected: PASS (12 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example logs/.gitkeep travel_agent/__init__.py travel_agent/config.py travel_agent/schemas.py travel_agent/diff.py tests/test_schemas_and_diff.py
git commit -m "feat: scaffold project, add schemas and trip-brief diff logic"
```

---

### Task 2: TripSession Persistence (Postgres via SQLAlchemy, SQLite in tests)

**Files:**
- Create: `travel_agent/models.py`
- Create: `travel_agent/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Message`, `TripBrief`, `FlightCandidate`, `HotelCandidate`, `ItineraryDay` from `travel_agent.schemas` (Task 1).
- Produces: `init_engine(database_url: str | None = None)`, `create_session(session_id: str) -> None`, `load_session(session_id: str) -> TripSessionState | None`, `save_session(session_id: str, *, messages: list[Message], trip_brief: TripBrief, flight_candidates: list[FlightCandidate], hotel_candidates: list[HotelCandidate], itinerary: list[ItineraryDay]) -> None` in `travel_agent.db`.
- Produces: `TripSessionState` dataclass (`id`, `messages`, `trip_brief`, `flight_candidates`, `hotel_candidates`, `itinerary`) in `travel_agent.db`, used by the orchestrator (Task 10) and FastAPI app (Task 11).

- [ ] **Step 1: Write the failing test**

`tests/conftest.py`:

```python
import pytest

from travel_agent import db as db_module


@pytest.fixture
def db_ready(tmp_path):
    db_module.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    yield
    db_module._engine = None
    db_module._SessionLocal = None
```

`tests/test_db.py`:

```python
import datetime

from travel_agent.db import create_session, load_session, save_session
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief


def test_create_and_load_empty_session(db_ready):
    create_session("sess-1")
    state = load_session("sess-1")
    assert state.id == "sess-1"
    assert state.messages == []
    assert state.trip_brief is None
    assert state.flight_candidates == []


def test_load_missing_session_returns_none(db_ready):
    assert load_session("does-not-exist") is None


def test_save_and_reload_full_session(db_ready):
    create_session("sess-2")
    messages = [Message(role="user", content="Plan a trip to Paris")]
    brief = TripBrief(destination="Paris", origin="ICN", budget_usd=2000.0, interests=["art"], pace="balanced")
    flights = [FlightCandidate(carrier="KE", price_usd=800.0, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    hotels = [HotelCandidate(name="Hotel Lumiere", price_usd_per_night=150.0, rating=4.2, address="Paris")]
    itinerary = [ItineraryDay(day_number=1, date=datetime.date(2026, 11, 1), activities=["Louvre"], notes="")]

    save_session(
        "sess-2",
        messages=messages,
        trip_brief=brief,
        flight_candidates=flights,
        hotel_candidates=hotels,
        itinerary=itinerary,
    )

    state = load_session("sess-2")
    assert state.messages == messages
    assert state.trip_brief == brief
    assert state.flight_candidates == flights
    assert state.hotel_candidates == hotels
    assert state.itinerary == itinerary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `travel_agent.db` and `travel_agent.models` do not exist yet.

- [ ] **Step 3: Implement the model and persistence layer**

`travel_agent/models.py`:

```python
import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TripSession(Base):
    __tablename__ = "trip_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    messages: Mapped[list] = mapped_column(JSON, default=list)
    trip_brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    flight_candidates: Mapped[list] = mapped_column(JSON, default=list)
    hotel_candidates: Mapped[list] = mapped_column(JSON, default=list)
    itinerary: Mapped[list] = mapped_column(JSON, default=list)
```

`travel_agent/db.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/models.py travel_agent/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: add TripSession persistence layer"
```

---

### Task 3: Amadeus Client (Real Flight + Hotel Search)

**Files:**
- Create: `travel_agent/tools/__init__.py`
- Create: `travel_agent/tools/amadeus_client.py`
- Test: `tests/test_amadeus_client.py`

**Interfaces:**
- Produces: `AmadeusClient(client_id: str, client_secret: str, base_url: str)` with `async def search_flights(origin: str, destination: str, departure_date: str, return_date: str | None = None, adults: int = 1) -> list[dict]` and `async def search_hotels(city_code: str, check_in: str, check_out: str) -> list[dict]`, both raising `AmadeusAPIError` on failure. Used by Flight/Hotel agents (Task 7).
- Produces: `AmadeusAPIError(Exception)`.

- [ ] **Step 1: Write the failing test**

`travel_agent/tools/__init__.py`: empty file.

`tests/test_amadeus_client.py`:

```python
import httpx
import pytest
import respx

from travel_agent.tools.amadeus_client import AmadeusAPIError, AmadeusClient

BASE_URL = "https://test.api.amadeus.com"


@pytest.fixture
def client():
    return AmadeusClient(client_id="id", client_secret="secret", base_url=BASE_URL)


@respx.mock
async def test_search_flights_returns_parsed_candidates(client):
    respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "price": {"total": "812.50"},
                        "itineraries": [
                            {
                                "segments": [
                                    {
                                        "carrierCode": "KE",
                                        "departure": {"iataCode": "ICN", "at": "2026-11-01T09:00:00"},
                                        "arrival": {"iataCode": "CDG", "at": "2026-11-01T15:30:00"},
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
        )
    )

    offers = await client.search_flights("ICN", "CDG", "2026-11-01")

    assert offers == [
        {
            "carrier": "KE",
            "price_usd": 812.50,
            "departure_time": "2026-11-01T09:00:00",
            "arrival_time": "2026-11-01T15:30:00",
            "origin": "ICN",
            "destination": "CDG",
            "stops": 0,
        }
    ]


@respx.mock
async def test_search_flights_raises_on_api_error(client):
    respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(return_value=httpx.Response(429))

    with pytest.raises(AmadeusAPIError):
        await client.search_flights("ICN", "CDG", "2026-11-01")


@respx.mock
async def test_search_hotels_returns_parsed_candidates(client):
    respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    respx.get(f"{BASE_URL}/v1/reference-data/locations/hotels/by-city").mock(
        return_value=httpx.Response(200, json={"data": [{"hotelId": "HTL1"}]})
    )
    respx.get(f"{BASE_URL}/v3/shopping/hotel-offers").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "hotel": {"name": "Hotel Lumiere", "rating": "4", "address": {"lines": ["12 Rue de Rivoli"]}},
                        "offers": [{"price": {"total": "180.00"}}],
                    }
                ]
            },
        )
    )

    offers = await client.search_hotels("PAR", "2026-11-01", "2026-11-05")

    assert offers == [
        {
            "name": "Hotel Lumiere",
            "price_usd_per_night": 180.0,
            "rating": 4.0,
            "address": "12 Rue de Rivoli",
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_amadeus_client.py -v`
Expected: FAIL — `travel_agent.tools.amadeus_client` does not exist yet.

- [ ] **Step 3: Implement the Amadeus client**

`travel_agent/tools/amadeus_client.py`:

```python
import time

import httpx


class AmadeusAPIError(Exception):
    pass


class AmadeusClient:
    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_token(self, http: httpx.AsyncClient) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        resp = await http.post(
            f"{self._base_url}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        if resp.status_code != 200:
            raise AmadeusAPIError(f"token request failed: {resp.status_code}")
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = time.monotonic() + body["expires_in"] - 30
        return self._token

    async def search_flights(
        self, origin: str, destination: str, departure_date: str, return_date: str | None = None, adults: int = 1
    ) -> list[dict]:
        async with httpx.AsyncClient() as http:
            token = await self._get_token(http)
            params = {
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": departure_date,
                "adults": adults,
            }
            if return_date:
                params["returnDate"] = return_date
            resp = await http.get(
                f"{self._base_url}/v2/shopping/flight-offers",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"flight search failed: {resp.status_code}")
            data = resp.json().get("data", [])
            return [self._parse_flight_offer(offer) for offer in data]

    def _parse_flight_offer(self, offer: dict) -> dict:
        segments = offer["itineraries"][0]["segments"]
        first, last = segments[0], segments[-1]
        return {
            "carrier": first["carrierCode"],
            "price_usd": float(offer["price"]["total"]),
            "departure_time": first["departure"]["at"],
            "arrival_time": last["arrival"]["at"],
            "origin": first["departure"]["iataCode"],
            "destination": last["arrival"]["iataCode"],
            "stops": len(segments) - 1,
        }

    async def search_hotels(self, city_code: str, check_in: str, check_out: str) -> list[dict]:
        async with httpx.AsyncClient() as http:
            token = await self._get_token(http)
            headers = {"Authorization": f"Bearer {token}"}

            resp = await http.get(
                f"{self._base_url}/v1/reference-data/locations/hotels/by-city",
                params={"cityCode": city_code},
                headers=headers,
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"hotel lookup failed: {resp.status_code}")
            hotel_ids = [h["hotelId"] for h in resp.json().get("data", [])]
            if not hotel_ids:
                return []

            resp = await http.get(
                f"{self._base_url}/v3/shopping/hotel-offers",
                params={"hotelIds": ",".join(hotel_ids), "checkInDate": check_in, "checkOutDate": check_out},
                headers=headers,
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"hotel offers failed: {resp.status_code}")
            return [self._parse_hotel_offer(entry) for entry in resp.json().get("data", [])]

    def _parse_hotel_offer(self, entry: dict) -> dict:
        hotel = entry["hotel"]
        offer = entry["offers"][0]
        return {
            "name": hotel["name"],
            "price_usd_per_night": float(offer["price"]["total"]),
            "rating": float(hotel["rating"]) if hotel.get("rating") else None,
            "address": ", ".join(hotel.get("address", {}).get("lines", [])),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_amadeus_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/tools/__init__.py travel_agent/tools/amadeus_client.py tests/test_amadeus_client.py
git commit -m "feat: add Amadeus flight and hotel search client"
```

---

### Task 4: Weather Client

**Files:**
- Create: `travel_agent/tools/weather_client.py`
- Test: `tests/test_weather_client.py`

**Interfaces:**
- Produces: `async def get_daily_summary(destination: str, start_date: date, end_date: date) -> list[dict]` in `travel_agent.tools.weather_client`, each dict shaped `{"date": "2026-11-01", "temp_max_c": float, "temp_min_c": float, "condition": str}`. Used by the Itinerary agent (Task 8).
- Produces: `WeatherAPIError(Exception)`.

- [ ] **Step 1: Write the failing test**

`tests/test_weather_client.py`:

```python
import datetime

import httpx
import pytest
import respx

from travel_agent.tools.weather_client import WeatherAPIError, get_daily_summary

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


@respx.mock
async def test_get_daily_summary_returns_parsed_days():
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json={"results": [{"latitude": 48.85, "longitude": 2.35}]})
    )
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "daily": {
                    "time": ["2026-11-01", "2026-11-02"],
                    "temperature_2m_max": [14.2, 13.8],
                    "temperature_2m_min": [7.1, 6.9],
                    "weathercode": [3, 61],
                }
            },
        )
    )

    days = await get_daily_summary("Paris", datetime.date(2026, 11, 1), datetime.date(2026, 11, 2))

    assert days == [
        {"date": "2026-11-01", "temp_max_c": 14.2, "temp_min_c": 7.1, "condition": "overcast"},
        {"date": "2026-11-02", "temp_max_c": 13.8, "temp_min_c": 6.9, "condition": "rain"},
    ]


@respx.mock
async def test_get_daily_summary_raises_when_city_not_found():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={"results": []}))

    with pytest.raises(WeatherAPIError):
        await get_daily_summary("Nowhereville", datetime.date(2026, 11, 1), datetime.date(2026, 11, 2))


@respx.mock
async def test_get_daily_summary_raises_on_forecast_failure():
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json={"results": [{"latitude": 48.85, "longitude": 2.35}]})
    )
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(WeatherAPIError):
        await get_daily_summary("Paris", datetime.date(2026, 11, 1), datetime.date(2026, 11, 2))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_weather_client.py -v`
Expected: FAIL — `travel_agent.tools.weather_client` does not exist yet.

- [ ] **Step 3: Implement the weather client**

`travel_agent/tools/weather_client.py`:

```python
import datetime

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CONDITIONS = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    61: "rain",
    63: "rain",
    65: "heavy rain",
    71: "snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    95: "thunderstorm",
}


class WeatherAPIError(Exception):
    pass


def _condition_for(code: int) -> str:
    return _WMO_CONDITIONS.get(code, "unknown")


async def get_daily_summary(destination: str, start_date: datetime.date, end_date: datetime.date) -> list[dict]:
    async with httpx.AsyncClient() as http:
        geo_resp = await http.get(GEOCODE_URL, params={"name": destination, "count": 1})
        if geo_resp.status_code != 200:
            raise WeatherAPIError(f"geocoding failed: {geo_resp.status_code}")
        results = geo_resp.json().get("results") or []
        if not results:
            raise WeatherAPIError(f"no location found for {destination!r}")
        lat, lon = results[0]["latitude"], results[0]["longitude"]

        forecast_resp = await http.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weathercode",
                "timezone": "auto",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        if forecast_resp.status_code != 200:
            raise WeatherAPIError(f"forecast failed: {forecast_resp.status_code}")

        daily = forecast_resp.json()["daily"]
        return [
            {
                "date": date,
                "temp_max_c": temp_max,
                "temp_min_c": temp_min,
                "condition": _condition_for(code),
            }
            for date, temp_max, temp_min, code in zip(
                daily["time"], daily["temperature_2m_max"], daily["temperature_2m_min"], daily["weathercode"]
            )
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_weather_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/tools/weather_client.py tests/test_weather_client.py
git commit -m "feat: add Open-Meteo weather client"
```

---

### Task 5: Agent Base — Shared Claude Tool-Use Loop

**Files:**
- Create: `travel_agent/agents/__init__.py`
- Create: `travel_agent/agents/base.py`
- Test: `tests/test_agent_base.py`

**Interfaces:**
- Produces: `AgentUsage(input_tokens: int, output_tokens: int, latency_ms: float)`, `AgentResult(output: dict, usage: AgentUsage)`, `AgentError(Exception)` in `travel_agent.agents.base`.
- Produces: `async def run_agent_loop(client, model: str, system_prompt: str, user_message: str, tools: list[dict], final_tool_name: str, tool_executor: Callable[[str, dict], Awaitable[dict]], client_tool_names: set[str], tool_choice: dict | None = None, max_turns: int = 5) -> AgentResult`. Used by every specialist agent (Tasks 6-8). `client_tool_names` names the tools `run_agent_loop` must execute locally via `tool_executor`; any other non-final `tool_use`/`server_tool_use` block (e.g. Claude's hosted web search) is left for Anthropic to have already resolved server-side and is skipped.

- [ ] **Step 1: Write the failing test**

`travel_agent/agents/__init__.py`: empty file.

`tests/test_agent_base.py`:

```python
from dataclasses import dataclass, field

import pytest

from travel_agent.agents.base import AgentError, run_agent_loop


@dataclass
class FakeBlock:
    type: str
    name: str = ""
    input: dict = field(default_factory=dict)
    id: str = "block-1"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage


class FakeMessagesAPI:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessagesAPI(responses)


async def test_single_turn_final_tool_call_returns_output():
    response = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit", input={"answer": 42})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=100, output_tokens=20),
    )
    client = FakeClient([response])

    async def executor(name, input):
        raise AssertionError("should not be called for a single-shot final tool")

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
        tool_choice={"type": "tool", "name": "submit"},
    )

    assert result.output == {"answer": 42}
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20


async def test_client_tool_is_executed_then_final_tool_returns_output():
    search_call = FakeResponse(
        content=[FakeBlock(type="tool_use", name="search", input={"q": "paris"}, id="call-1")],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=50, output_tokens=10),
    )
    final_call = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit", input={"results": ["a"]})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=60, output_tokens=15),
    )
    client = FakeClient([search_call, final_call])

    executed = []

    async def executor(name, input):
        executed.append((name, input))
        return {"found": ["a"]}

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"name": "search"}, {"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names={"search"},
    )

    assert executed == [("search", {"q": "paris"})]
    assert result.output == {"results": ["a"]}
    assert client.messages.calls[1]["messages"][-1]["content"][0]["tool_use_id"] == "call-1"


async def test_server_tool_use_block_is_skipped_not_executed():
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "paris"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(type="tool_use", name="submit", input={"ok": True}),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=10, output_tokens=5),
    )
    client = FakeClient([response])

    async def executor(name, input):
        raise AssertionError("server tools must not be routed to the local executor")

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"type": "web_search_20250305", "name": "web_search"}, {"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
    )

    assert result.output == {"ok": True}


async def test_max_turns_exceeded_raises_agent_error():
    non_final = FakeResponse(
        content=[FakeBlock(type="tool_use", name="search", input={})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=1, output_tokens=1),
    )
    client = FakeClient([non_final, non_final])

    async def executor(name, input):
        return {}

    with pytest.raises(AgentError):
        await run_agent_loop(
            client=client,
            model="claude-sonnet-5",
            system_prompt="sys",
            user_message="go",
            tools=[{"name": "search"}, {"name": "submit"}],
            final_tool_name="submit",
            tool_executor=executor,
            client_tool_names={"search"},
            max_turns=2,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_base.py -v`
Expected: FAIL — `travel_agent.agents.base` does not exist yet.

- [ ] **Step 3: Implement the agent base loop**

`travel_agent/agents/base.py`:

```python
import json
import time
from dataclasses import dataclass
from typing import Awaitable, Callable


class AgentError(Exception):
    pass


@dataclass
class AgentUsage:
    input_tokens: int
    output_tokens: int
    latency_ms: float


@dataclass
class AgentResult:
    output: dict
    usage: AgentUsage


async def run_agent_loop(
    client,
    model: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    final_tool_name: str,
    tool_executor: Callable[[str, dict], Awaitable[dict]],
    client_tool_names: set[str],
    tool_choice: dict | None = None,
    max_turns: int = 5,
) -> AgentResult:
    start = time.monotonic()
    messages: list[dict] = [{"role": "user", "content": user_message}]
    input_tokens = 0
    output_tokens = 0

    for _ in range(max_turns):
        create_kwargs = dict(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice

        response = await client.messages.create(**create_kwargs)
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        if response.stop_reason != "tool_use":
            raise AgentError(f"expected tool_use, got stop_reason={response.stop_reason!r}")

        messages.append({"role": "assistant", "content": response.content})

        final_output = None
        tool_results = []
        for block in response.content:
            if block.type == "tool_use" and block.name == final_tool_name:
                final_output = block.input
            elif block.type == "tool_use" and block.name in client_tool_names:
                result = await tool_executor(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
                )
            # server_tool_use / web_search_tool_result / other server-executed
            # blocks are already resolved by Anthropic and need no local action.

        if final_output is not None:
            return AgentResult(
                output=final_output,
                usage=AgentUsage(input_tokens, output_tokens, (time.monotonic() - start) * 1000),
            )

        if not tool_results:
            raise AgentError("tool_use turn produced no client tool results and no final answer")

        messages.append({"role": "user", "content": tool_results})

    raise AgentError(f"max_turns={max_turns} exceeded without a final answer")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_base.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/agents/__init__.py travel_agent/agents/base.py tests/test_agent_base.py
git commit -m "feat: add shared Claude tool-use loop for specialist agents"
```

---

### Task 6: Planner Agent

**Files:**
- Create: `travel_agent/agents/planner.py`
- Test: `tests/test_planner_agent.py`

**Interfaces:**
- Consumes: `run_agent_loop`, `AgentUsage` from `travel_agent.agents.base` (Task 5); `Message`, `TripBrief` from `travel_agent.schemas` (Task 1).
- Produces: `async def run_planner_agent(client, messages: list[Message], previous_brief: TripBrief | None) -> tuple[TripBrief, AgentUsage]` in `travel_agent.agents.planner`. Used by the orchestrator (Task 10).

- [ ] **Step 1: Write the failing test**

`tests/test_planner_agent.py`:

```python
from dataclasses import dataclass, field

from travel_agent.agents.planner import run_planner_agent
from travel_agent.schemas import Message, TripBrief


@dataclass
class FakeBlock:
    type: str
    name: str = ""
    input: dict = field(default_factory=dict)
    id: str = "block-1"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage


class FakeMessagesAPI:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessagesAPI(response)


async def test_planner_extracts_brief_from_conversation():
    response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_trip_brief",
                input={
                    "destination": "Paris",
                    "origin": "ICN",
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-05",
                    "budget_usd": 2000.0,
                    "interests": ["art", "food"],
                    "pace": "balanced",
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=200, output_tokens=40),
    )
    client = FakeClient(response)
    messages = [Message(role="user", content="Plan a 5 day trip to Paris from Seoul, budget $2000, into art and food")]

    brief, usage = await run_planner_agent(client, messages, previous_brief=None)

    assert brief == TripBrief(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-05",
        budget_usd=2000.0,
        interests=["art", "food"],
        pace="balanced",
    )
    assert usage.input_tokens == 200
    assert client.messages.calls[0]["tool_choice"] == {"type": "tool", "name": "submit_trip_brief"}


async def test_planner_passes_previous_brief_in_prompt():
    response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_trip_brief",
                input={
                    "destination": "Paris",
                    "origin": "ICN",
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-05",
                    "budget_usd": 2000.0,
                    "interests": ["art"],
                    "pace": "relaxed",
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=210, output_tokens=42),
    )
    client = FakeClient(response)
    previous_brief = TripBrief(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-05",
        budget_usd=2000.0,
        interests=["art"],
        pace="balanced",
    )
    messages = [
        Message(role="user", content="Plan a trip to Paris"),
        Message(role="assistant", content="Sure, here's a plan..."),
        Message(role="user", content="2일차 느슨하게 바꿔줘"),
    ]

    brief, _ = await run_planner_agent(client, messages, previous_brief)

    sent_user_message = client.messages.calls[0]["messages"][0]["content"]
    assert "느슨하게" in sent_user_message
    assert '"pace":"balanced"' in sent_user_message.replace(" ", "") or "balanced" in sent_user_message
    assert brief.pace == "relaxed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planner_agent.py -v`
Expected: FAIL — `travel_agent.agents.planner` does not exist yet.

- [ ] **Step 3: Implement the planner agent**

`travel_agent/agents/planner.py`:

```python
from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import Message, TripBrief

PLANNER_SYSTEM_PROMPT = """You are the Planner agent for a travel planning system.
Read the full conversation and the previous structured trip brief (if any),
then produce the updated trip brief by calling submit_trip_brief.

Rules:
- Keep every field from the previous brief unless the conversation clearly
  changes it. Never null out a field the user hasn't mentioned again.
- interests is a cumulative list of the user's stated interests/activities.
- pace is one of "relaxed", "balanced", "packed" — infer it from phrasing
  like "느슨하게"/relaxed, "빡빡하게"/packed, etc.
- Dates must be ISO format (YYYY-MM-DD). origin/destination are city or
  airport names as the user said them; do not invent an IATA code here.
"""

SUBMIT_TRIP_BRIEF_TOOL = {
    "name": "submit_trip_brief",
    "description": "Submit the updated structured trip brief extracted from the conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {"type": ["string", "null"]},
            "origin": {"type": ["string", "null"]},
            "start_date": {"type": ["string", "null"], "description": "ISO date"},
            "end_date": {"type": ["string", "null"], "description": "ISO date"},
            "budget_usd": {"type": ["number", "null"]},
            "interests": {"type": "array", "items": {"type": "string"}},
            "pace": {"type": ["string", "null"], "enum": ["relaxed", "balanced", "packed", None]},
        },
        "required": ["interests"],
    },
}


async def _no_op_executor(name: str, tool_input: dict) -> dict:
    raise AssertionError(f"planner agent has no client tools, got {name!r}")


async def run_planner_agent(
    client, messages: list[Message], previous_brief: TripBrief | None
) -> tuple[TripBrief, AgentUsage]:
    conversation_text = "\n".join(f"{m.role}: {m.content}" for m in messages)
    previous_json = previous_brief.model_dump_json() if previous_brief else "null"
    user_message = (
        f"Conversation so far:\n{conversation_text}\n\n"
        f"Previous trip brief (JSON):\n{previous_json}\n\n"
        "Extract/update the trip brief and call submit_trip_brief."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[SUBMIT_TRIP_BRIEF_TOOL],
        final_tool_name="submit_trip_brief",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        tool_choice={"type": "tool", "name": "submit_trip_brief"},
        max_turns=1,
    )

    return TripBrief(**result.output), result.usage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planner_agent.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/agents/planner.py tests/test_planner_agent.py
git commit -m "feat: add Planner agent"
```

---

### Task 7: Flight Agent + Hotel Agent

**Files:**
- Create: `travel_agent/agents/flight_agent.py`
- Create: `travel_agent/agents/hotel_agent.py`
- Test: `tests/test_flight_hotel_agents.py`

**Interfaces:**
- Consumes: `run_agent_loop`, `AgentUsage` from `travel_agent.agents.base` (Task 5); `TripBrief`, `FlightCandidate`, `HotelCandidate` from `travel_agent.schemas` (Task 1); `AmadeusClient` from `travel_agent.tools.amadeus_client` (Task 3).
- Produces: `async def run_flight_agent(client, brief: TripBrief, amadeus: AmadeusClient) -> tuple[list[FlightCandidate], AgentUsage]` in `travel_agent.agents.flight_agent`.
- Produces: `async def run_hotel_agent(client, brief: TripBrief, amadeus: AmadeusClient) -> tuple[list[HotelCandidate], AgentUsage]` in `travel_agent.agents.hotel_agent`.
- Both used by the orchestrator (Task 10), run concurrently via `asyncio.gather`.

- [ ] **Step 1: Write the failing test**

`tests/test_flight_hotel_agents.py`:

```python
from dataclasses import dataclass, field

from travel_agent.agents.flight_agent import run_flight_agent
from travel_agent.agents.hotel_agent import run_hotel_agent
from travel_agent.schemas import FlightCandidate, HotelCandidate, TripBrief


@dataclass
class FakeBlock:
    type: str
    name: str = ""
    input: dict = field(default_factory=dict)
    id: str = "block-1"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage


class FakeMessagesAPI:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessagesAPI(responses)


class FakeAmadeus:
    def __init__(self, flight_results=None, hotel_results=None):
        self.flight_results = flight_results or []
        self.hotel_results = hotel_results or []
        self.flight_calls = []
        self.hotel_calls = []

    async def search_flights(self, origin, destination, departure_date, return_date=None, adults=1):
        self.flight_calls.append((origin, destination, departure_date, return_date))
        return self.flight_results

    async def search_hotels(self, city_code, check_in, check_out):
        self.hotel_calls.append((city_code, check_in, check_out))
        return self.hotel_results


def _brief():
    return TripBrief(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-05",
        budget_usd=2000.0,
        interests=["art"],
        pace="balanced",
    )


async def test_run_flight_agent_searches_then_submits():
    search_call = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="search_flights",
                input={"origin": "ICN", "destination": "CDG", "departure_date": "2026-11-01", "return_date": "2026-11-05"},
                id="call-1",
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=100, output_tokens=20),
    )
    submit_call = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_flight_candidates",
                input={
                    "candidates": [
                        {
                            "carrier": "KE",
                            "price_usd": 812.5,
                            "departure_time": "t1",
                            "arrival_time": "t2",
                            "origin": "ICN",
                            "destination": "CDG",
                            "stops": 0,
                        }
                    ]
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=60, output_tokens=15),
    )
    client = FakeClient([search_call, submit_call])
    amadeus = FakeAmadeus(
        flight_results=[
            {
                "carrier": "KE",
                "price_usd": 812.5,
                "departure_time": "t1",
                "arrival_time": "t2",
                "origin": "ICN",
                "destination": "CDG",
                "stops": 0,
            }
        ]
    )

    candidates, usage = await run_flight_agent(client, _brief(), amadeus)

    assert candidates == [
        FlightCandidate(carrier="KE", price_usd=812.5, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)
    ]
    assert amadeus.flight_calls == [("ICN", "CDG", "2026-11-01", "2026-11-05")]
    assert usage.input_tokens == 160


async def test_run_hotel_agent_searches_then_submits():
    search_call = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="search_hotels",
                input={"city_code": "PAR", "check_in": "2026-11-01", "check_out": "2026-11-05"},
                id="call-1",
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=90, output_tokens=18),
    )
    submit_call = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_hotel_candidates",
                input={
                    "candidates": [
                        {"name": "Hotel Lumiere", "price_usd_per_night": 180.0, "rating": 4.3, "address": "Paris"}
                    ]
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=55, output_tokens=12),
    )
    client = FakeClient([search_call, submit_call])
    amadeus = FakeAmadeus(
        hotel_results=[{"name": "Hotel Lumiere", "price_usd_per_night": 180.0, "rating": 4.3, "address": "Paris"}]
    )

    candidates, usage = await run_hotel_agent(client, _brief(), amadeus)

    assert candidates == [HotelCandidate(name="Hotel Lumiere", price_usd_per_night=180.0, rating=4.3, address="Paris")]
    assert amadeus.hotel_calls == [("PAR", "2026-11-01", "2026-11-05")]
    assert usage.input_tokens == 145
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_flight_hotel_agents.py -v`
Expected: FAIL — `travel_agent.agents.flight_agent` / `hotel_agent` do not exist yet.

- [ ] **Step 3: Implement the flight and hotel agents**

`travel_agent/agents/flight_agent.py`:

```python
from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import FlightCandidate, TripBrief
from travel_agent.tools.amadeus_client import AmadeusClient

FLIGHT_SYSTEM_PROMPT = """You are the Flight agent for a travel planning system.
Given a trip brief, call search_flights with the correct IATA airport codes
for the origin and destination cities and the trip's start/end dates, then
call submit_flight_candidates with up to 3 options ranked by best value
(balance of price and directness) within the stated budget when possible.
"""

SEARCH_FLIGHTS_TOOL = {
    "name": "search_flights",
    "description": "Search real flight offers via Amadeus.",
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "3-letter IATA airport code"},
            "destination": {"type": "string", "description": "3-letter IATA airport code"},
            "departure_date": {"type": "string", "description": "ISO date"},
            "return_date": {"type": ["string", "null"], "description": "ISO date"},
        },
        "required": ["origin", "destination", "departure_date"],
    },
}

_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "carrier": {"type": "string"},
        "price_usd": {"type": "number"},
        "departure_time": {"type": "string"},
        "arrival_time": {"type": "string"},
        "origin": {"type": "string"},
        "destination": {"type": "string"},
        "stops": {"type": "integer"},
    },
    "required": ["carrier", "price_usd", "departure_time", "arrival_time", "origin", "destination", "stops"],
}

SUBMIT_FLIGHT_CANDIDATES_TOOL = {
    "name": "submit_flight_candidates",
    "description": "Submit the final ranked list of flight candidates.",
    "input_schema": {
        "type": "object",
        "properties": {"candidates": {"type": "array", "items": _CANDIDATE_SCHEMA}},
        "required": ["candidates"],
    },
}


async def run_flight_agent(client, brief: TripBrief, amadeus: AmadeusClient) -> tuple[list[FlightCandidate], AgentUsage]:
    async def executor(name: str, tool_input: dict) -> dict:
        offers = await amadeus.search_flights(
            origin=tool_input["origin"],
            destination=tool_input["destination"],
            departure_date=tool_input["departure_date"],
            return_date=tool_input.get("return_date"),
        )
        return {"offers": offers}

    user_message = (
        f"Trip brief: origin city/airport={brief.origin}, destination={brief.destination}, "
        f"depart={brief.start_date}, return={brief.end_date}, budget_usd={brief.budget_usd}. "
        "Search for flights and submit up to 3 ranked candidates."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=FLIGHT_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[SEARCH_FLIGHTS_TOOL, SUBMIT_FLIGHT_CANDIDATES_TOOL],
        final_tool_name="submit_flight_candidates",
        tool_executor=executor,
        client_tool_names={"search_flights"},
        max_turns=3,
    )

    candidates = [FlightCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
```

`travel_agent/agents/hotel_agent.py`:

```python
from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import HotelCandidate, TripBrief
from travel_agent.tools.amadeus_client import AmadeusClient

HOTEL_SYSTEM_PROMPT = """You are the Hotel agent for a travel planning system.
Given a trip brief, call search_hotels with the 3-letter IATA city code for
the destination and the trip's check-in/check-out dates, then call
submit_hotel_candidates with up to 3 options ranked by best value within
the stated budget when possible.
"""

SEARCH_HOTELS_TOOL = {
    "name": "search_hotels",
    "description": "Search real hotel offers via Amadeus.",
    "input_schema": {
        "type": "object",
        "properties": {
            "city_code": {"type": "string", "description": "3-letter IATA city code"},
            "check_in": {"type": "string", "description": "ISO date"},
            "check_out": {"type": "string", "description": "ISO date"},
        },
        "required": ["city_code", "check_in", "check_out"],
    },
}

_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "price_usd_per_night": {"type": "number"},
        "rating": {"type": ["number", "null"]},
        "address": {"type": "string"},
    },
    "required": ["name", "price_usd_per_night", "address"],
}

SUBMIT_HOTEL_CANDIDATES_TOOL = {
    "name": "submit_hotel_candidates",
    "description": "Submit the final ranked list of hotel candidates.",
    "input_schema": {
        "type": "object",
        "properties": {"candidates": {"type": "array", "items": _CANDIDATE_SCHEMA}},
        "required": ["candidates"],
    },
}


async def run_hotel_agent(client, brief: TripBrief, amadeus: AmadeusClient) -> tuple[list[HotelCandidate], AgentUsage]:
    async def executor(name: str, tool_input: dict) -> dict:
        offers = await amadeus.search_hotels(
            city_code=tool_input["city_code"],
            check_in=tool_input["check_in"],
            check_out=tool_input["check_out"],
        )
        return {"offers": offers}

    user_message = (
        f"Trip brief: destination={brief.destination}, check_in={brief.start_date}, "
        f"check_out={brief.end_date}, budget_usd={brief.budget_usd}. "
        "Search for hotels and submit up to 3 ranked candidates."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=HOTEL_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[SEARCH_HOTELS_TOOL, SUBMIT_HOTEL_CANDIDATES_TOOL],
        final_tool_name="submit_hotel_candidates",
        tool_executor=executor,
        client_tool_names={"search_hotels"},
        max_turns=3,
    )

    candidates = [HotelCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_flight_hotel_agents.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/agents/flight_agent.py travel_agent/agents/hotel_agent.py tests/test_flight_hotel_agents.py
git commit -m "feat: add Flight and Hotel agents"
```

---

### Task 8: Itinerary Agent

**Files:**
- Create: `travel_agent/agents/itinerary_agent.py`
- Test: `tests/test_itinerary_agent.py`

**Interfaces:**
- Consumes: `run_agent_loop`, `AgentUsage` from `travel_agent.agents.base` (Task 5); `TripBrief`, `FlightCandidate`, `HotelCandidate`, `ItineraryDay` from `travel_agent.schemas` (Task 1).
- Produces: `async def run_itinerary_agent(client, brief: TripBrief, flights: list[FlightCandidate], hotels: list[HotelCandidate], weather: list[dict]) -> tuple[list[ItineraryDay], AgentUsage]` in `travel_agent.agents.itinerary_agent`. Used by the orchestrator (Task 10).

- [ ] **Step 1: Write the failing test**

`tests/test_itinerary_agent.py`:

```python
from dataclasses import dataclass, field

from travel_agent.agents.itinerary_agent import run_itinerary_agent
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, TripBrief


@dataclass
class FakeBlock:
    type: str
    name: str = ""
    input: dict = field(default_factory=dict)
    id: str = "block-1"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage


class FakeMessagesAPI:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessagesAPI(responses)


def _brief(**overrides):
    base = dict(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-02",
        budget_usd=2000.0,
        interests=["art"],
        pace="relaxed",
    )
    base.update(overrides)
    return TripBrief(**base)


async def test_itinerary_agent_composes_days_from_context_in_one_turn():
    # A single response can contain server-executed web_search blocks
    # followed directly by the final submit_itinerary tool call.
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "Paris museums"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(
                type="tool_use",
                name="submit_itinerary",
                input={
                    "days": [
                        {"day_number": 1, "date": "2026-11-01", "activities": ["Louvre"], "notes": "relaxed pace"},
                    ]
                },
            ),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=300, output_tokens=80),
    )
    client = FakeClient([response])

    days, usage = await run_itinerary_agent(
        client,
        _brief(),
        flights=[FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)],
        hotels=[HotelCandidate(name="Hotel Lumiere", price_usd_per_night=150, rating=4.2, address="Paris")],
        weather=[{"date": "2026-11-01", "temp_max_c": 14.0, "temp_min_c": 7.0, "condition": "overcast"}],
    )

    assert days == [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="relaxed pace")]
    assert usage.input_tokens == 300
    sent_message = client.messages.calls[0]["messages"][0]["content"]
    assert "overcast" in sent_message
    assert "Hotel Lumiere" in sent_message


async def test_itinerary_agent_includes_web_search_tool():
    response = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit_itinerary", input={"days": []})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=10, output_tokens=5),
    )
    client = FakeClient([response])

    await run_itinerary_agent(client, _brief(), flights=[], hotels=[], weather=[])

    tool_types = {t.get("type") for t in client.messages.calls[0]["tools"]}
    assert "web_search_20250305" in tool_types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_itinerary_agent.py -v`
Expected: FAIL — `travel_agent.agents.itinerary_agent` does not exist yet.

- [ ] **Step 3: Implement the itinerary agent**

`travel_agent/agents/itinerary_agent.py`:

```python
from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, TripBrief

ITINERARY_SYSTEM_PROMPT = """You are the Itinerary agent for a travel planning system.
Compose a day-by-day plan from the trip brief, the chosen flight/hotel
candidates, and the daily weather forecast. Use web_search for specific
attractions, opening hours, or events worth knowing about at the
destination. Respect the requested pace ("relaxed" = 1-2 activities/day,
"balanced" = 2-3, "packed" = 4+). When finished, call submit_itinerary
with one entry per day of the trip.
"""

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}

SUBMIT_ITINERARY_TOOL = {
    "name": "submit_itinerary",
    "description": "Submit the final day-by-day itinerary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day_number": {"type": "integer"},
                        "date": {"type": "string"},
                        "activities": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                    "required": ["day_number", "date", "activities", "notes"],
                },
            },
        },
        "required": ["days"],
    },
}


async def _no_op_executor(name: str, tool_input: dict) -> dict:
    raise AssertionError(f"itinerary agent has no local client tools, got {name!r}")


def _format_weather(weather: list[dict]) -> str:
    if not weather:
        return "no forecast available"
    return "; ".join(f"{d['date']}: {d['condition']}, {d['temp_min_c']}-{d['temp_max_c']}C" for d in weather)


def _format_flights(flights: list[FlightCandidate]) -> str:
    if not flights:
        return "none selected"
    return "; ".join(f"{f.carrier} {f.origin}->{f.destination} ${f.price_usd}" for f in flights)


def _format_hotels(hotels: list[HotelCandidate]) -> str:
    if not hotels:
        return "none selected"
    return "; ".join(f"{h.name} (${h.price_usd_per_night}/night, {h.address})" for h in hotels)


async def run_itinerary_agent(
    client,
    brief: TripBrief,
    flights: list[FlightCandidate],
    hotels: list[HotelCandidate],
    weather: list[dict],
) -> tuple[list[ItineraryDay], AgentUsage]:
    user_message = (
        f"Destination: {brief.destination}. Dates: {brief.start_date} to {brief.end_date}. "
        f"Interests: {', '.join(brief.interests) or 'unspecified'}. Pace: {brief.pace or 'balanced'}.\n"
        f"Flights: {_format_flights(flights)}\n"
        f"Hotels: {_format_hotels(hotels)}\n"
        f"Weather: {_format_weather(weather)}\n"
        "Compose the day-by-day itinerary and call submit_itinerary."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=ITINERARY_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[WEB_SEARCH_TOOL, SUBMIT_ITINERARY_TOOL],
        final_tool_name="submit_itinerary",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        max_turns=4,
    )

    days = [ItineraryDay(**d) for d in result.output["days"]]
    return days, result.usage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_itinerary_agent.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/agents/itinerary_agent.py tests/test_itinerary_agent.py
git commit -m "feat: add Itinerary agent"
```

---

### Task 9: Metrics Logging

**Files:**
- Create: `travel_agent/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: `settings.metrics_log_path` from `travel_agent.config` (Task 1).
- Produces: `def record_agent_call(agent_name: str, latency_ms: float, input_tokens: int, output_tokens: int, success: bool) -> dict` in `travel_agent.metrics`. Used by the orchestrator (Task 10). Appends one JSON line to the configured metrics log path and returns the record.

- [ ] **Step 1: Write the failing test**

`tests/test_metrics.py`:

```python
import json

from travel_agent import metrics


def test_record_agent_call_appends_jsonl_and_computes_cost(tmp_path, monkeypatch):
    log_path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", log_path)

    record = metrics.record_agent_call(
        agent_name="planner", latency_ms=123.4, input_tokens=1000, output_tokens=200, success=True
    )

    assert record["agent"] == "planner"
    assert record["success"] is True
    assert record["cost_usd"] == round(
        (1000 / 1_000_000) * metrics.INPUT_COST_PER_MTOK + (200 / 1_000_000) * metrics.OUTPUT_COST_PER_MTOK, 6
    )

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["agent"] == "planner"


def test_record_agent_call_appends_multiple_records(tmp_path, monkeypatch):
    log_path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", log_path)

    metrics.record_agent_call(agent_name="flight", latency_ms=50.0, input_tokens=10, output_tokens=2, success=True)
    metrics.record_agent_call(agent_name="hotel", latency_ms=999.0, input_tokens=0, output_tokens=0, success=False)

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["success"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL — `travel_agent.metrics` does not exist yet.

- [ ] **Step 3: Implement metrics logging**

`travel_agent/metrics.py`:

```python
import json
import time
from pathlib import Path

from travel_agent.config import settings

METRICS_PATH = Path(settings.metrics_log_path)

# USD per million tokens, claude-sonnet-5 pricing.
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0


def record_agent_call(agent_name: str, latency_ms: float, input_tokens: int, output_tokens: int, success: bool) -> dict:
    cost_usd = (input_tokens / 1_000_000) * INPUT_COST_PER_MTOK + (output_tokens / 1_000_000) * OUTPUT_COST_PER_MTOK
    record = {
        "agent": agent_name,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "success": success,
        "timestamp": time.time(),
    }
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_metrics.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/metrics.py tests/test_metrics.py
git commit -m "feat: add per-agent metrics logging"
```

---

### Task 10: Orchestrator

**Files:**
- Create: `travel_agent/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `diff_trip_brief` (Task 1); `run_planner_agent` (Task 6); `run_flight_agent` (Task 7); `run_hotel_agent` (Task 7); `run_itinerary_agent` (Task 8); `get_daily_summary` (Task 4); `record_agent_call` (Task 9); `AgentError` (Task 5); `AmadeusAPIError` (Task 3); `WeatherAPIError` (Task 4); `TripSessionState` (Task 2).
- Produces: `TurnResult(reply: str, trip_brief: TripBrief, flight_candidates: list[FlightCandidate], hotel_candidates: list[HotelCandidate], itinerary: list[ItineraryDay], warnings: list[str])` and `async def handle_turn(client, amadeus, session: TripSessionState, user_message: str) -> TurnResult` in `travel_agent.orchestrator`. Used by the FastAPI app (Task 11).
- This task monkeypatches `travel_agent.orchestrator.run_planner_agent` etc. directly (not the agent modules) — `orchestrator.py` must import each agent function by name (`from travel_agent.agents.planner import run_planner_agent`), not the module, so tests can patch the name in place.

- [ ] **Step 1: Write the failing test**

`tests/test_orchestrator.py`:

```python
import asyncio

import pytest

from travel_agent import orchestrator
from travel_agent.agents.base import AgentError, AgentUsage
from travel_agent.db import TripSessionState
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief
from travel_agent.tools.amadeus_client import AmadeusAPIError


def _usage():
    return AgentUsage(input_tokens=10, output_tokens=5, latency_ms=12.0)


def _empty_session():
    return TripSessionState(
        id="s1", messages=[], trip_brief=None, flight_candidates=[], hotel_candidates=[], itinerary=[]
    )


async def test_first_turn_runs_all_agents(monkeypatch):
    new_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    hotels = [HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")]
    days = [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="")]

    async def fake_planner(client, messages, previous_brief):
        return new_brief, _usage()

    async def fake_flight(client, brief, amadeus):
        return flights, _usage()

    async def fake_hotel(client, brief, amadeus):
        return hotels, _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        assert flights_ == flights and hotels_ == hotels
        return days, _usage()

    async def fake_weather(destination, start_date, end_date):
        return [{"date": "2026-11-01", "temp_max_c": 10.0, "temp_min_c": 2.0, "condition": "clear"}]

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fake_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=_empty_session(), user_message="Plan a trip to Paris")

    assert result.trip_brief == new_brief
    assert result.flight_candidates == flights
    assert result.hotel_candidates == hotels
    assert result.itinerary == days
    assert result.warnings == []


async def test_pace_only_change_skips_flight_and_hotel(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    new_brief = previous_brief.model_copy(update={"pace": "relaxed"})
    cached_flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    cached_hotels = [HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")]
    new_days = [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre, slower pace"], notes="")]

    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=cached_flights, hotel_candidates=cached_hotels, itinerary=[],
    )

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("flight/hotel agent must not run when only pace changed")

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        assert flights_ == cached_flights
        assert hotels_ == cached_hotels
        return new_days, _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=session, user_message="2일차 느슨하게 바꿔줘")

    assert result.flight_candidates == cached_flights
    assert result.hotel_candidates == cached_hotels
    assert result.itinerary == new_days


async def test_flight_agent_failure_falls_back_to_cached_and_warns(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    new_brief = previous_brief.model_copy(update={"budget_usd": 1500.0})
    cached_flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    new_hotels = [HotelCandidate(name="H2", price_usd_per_night=90, rating=4.1, address="Paris")]

    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=cached_flights, hotel_candidates=[], itinerary=[],
    )

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def failing_flight(client, brief, amadeus):
        raise AmadeusAPIError("rate limited")

    async def fake_hotel(client, brief, amadeus):
        return new_hotels, _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", failing_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=session, user_message="lower budget to 1500")

    assert result.flight_candidates == cached_flights
    assert result.hotel_candidates == new_hotels
    assert any("flight" in w for w in result.warnings)


async def test_agent_timeout_falls_back_without_failing_whole_turn(monkeypatch):
    previous_brief = None
    new_brief = TripBrief(destination="Tokyo", origin="ICN", start_date="2026-12-01", end_date="2026-12-03", budget_usd=1000.0, interests=[], pace="balanced")

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def slow_flight(client, brief, amadeus):
        await asyncio.sleep(10)
        return [], _usage()

    async def fake_hotel(client, brief, amadeus):
        return [], _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", slow_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator, "AGENT_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=_empty_session(), user_message="Plan a trip to Tokyo")

    assert result.flight_candidates == []
    assert any("flight" in w for w in result.warnings)


async def test_unrelated_message_does_not_rerun_specialists(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=[], hotel_candidates=[], itinerary=[ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="")],
    )

    async def fake_planner(client, messages, previous_brief_):
        return previous_brief, _usage()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("no specialist agent should run when the brief is unchanged")

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fail_if_called)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=session, user_message="thanks!")

    assert result.itinerary == session.itinerary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL — `travel_agent.orchestrator` does not exist yet.

- [ ] **Step 3: Implement the orchestrator**

`travel_agent/orchestrator.py`:

```python
import asyncio
import time
from dataclasses import dataclass

from travel_agent import metrics
from travel_agent.agents.base import AgentError
from travel_agent.agents.flight_agent import run_flight_agent
from travel_agent.agents.hotel_agent import run_hotel_agent
from travel_agent.agents.itinerary_agent import run_itinerary_agent
from travel_agent.agents.planner import run_planner_agent
from travel_agent.db import TripSessionState
from travel_agent.diff import diff_trip_brief
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief
from travel_agent.tools.amadeus_client import AmadeusAPIError
from travel_agent.tools.weather_client import WeatherAPIError, get_daily_summary

AGENT_TIMEOUT_SECONDS = 30
_FALLIBLE_ERRORS = (AmadeusAPIError, WeatherAPIError, AgentError, asyncio.TimeoutError)


@dataclass
class TurnResult:
    reply: str
    trip_brief: TripBrief
    flight_candidates: list[FlightCandidate]
    hotel_candidates: list[HotelCandidate]
    itinerary: list[ItineraryDay]
    warnings: list[str]


async def _run_with_fallback(agent_name: str, coro, cached):
    start = time.monotonic()
    try:
        result, usage = await asyncio.wait_for(coro, timeout=AGENT_TIMEOUT_SECONDS)
        metrics.record_agent_call(
            agent_name=agent_name,
            latency_ms=usage.latency_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            success=True,
        )
        return result, None
    except _FALLIBLE_ERRORS:
        latency_ms = (time.monotonic() - start) * 1000
        metrics.record_agent_call(
            agent_name=agent_name, latency_ms=latency_ms, input_tokens=0, output_tokens=0, success=False
        )
        warning = (
            f"couldn't fetch live {agent_name} data right now, showing previous results"
            if cached
            else f"couldn't fetch live {agent_name} data right now"
        )
        return cached, warning


async def handle_turn(client, amadeus, session: TripSessionState, user_message: str) -> TurnResult:
    messages = session.messages + [Message(role="user", content=user_message)]

    new_brief, planner_usage = await run_planner_agent(client, messages, session.trip_brief)
    metrics.record_agent_call(
        agent_name="planner",
        latency_ms=planner_usage.latency_ms,
        input_tokens=planner_usage.input_tokens,
        output_tokens=planner_usage.output_tokens,
        success=True,
    )

    agents_to_run = diff_trip_brief(session.trip_brief, new_brief)
    warnings: list[str] = []
    flight_candidates = session.flight_candidates
    hotel_candidates = session.hotel_candidates
    itinerary = session.itinerary

    if "flight" in agents_to_run or "hotel" in agents_to_run:
        (flight_candidates, flight_warning), (hotel_candidates, hotel_warning) = await asyncio.gather(
            _run_with_fallback("flight", run_flight_agent(client, new_brief, amadeus), session.flight_candidates),
            _run_with_fallback("hotel", run_hotel_agent(client, new_brief, amadeus), session.hotel_candidates),
        )
        for w in (flight_warning, hotel_warning):
            if w:
                warnings.append(w)

    if agents_to_run:
        if new_brief.destination and new_brief.start_date and new_brief.end_date:
            try:
                weather = await get_daily_summary(new_brief.destination, new_brief.start_date, new_brief.end_date)
            except WeatherAPIError:
                weather = []
        else:
            weather = []
        itinerary, itin_warning = await _run_with_fallback(
            "itinerary",
            run_itinerary_agent(client, new_brief, flight_candidates, hotel_candidates, weather),
            session.itinerary,
        )
        if itin_warning:
            warnings.append(itin_warning)

    reply = _build_reply(new_brief, itinerary, warnings)
    return TurnResult(
        reply=reply,
        trip_brief=new_brief,
        flight_candidates=flight_candidates,
        hotel_candidates=hotel_candidates,
        itinerary=itinerary,
        warnings=warnings,
    )


def _build_reply(brief: TripBrief, itinerary: list[ItineraryDay], warnings: list[str]) -> str:
    lines = [f"Updated your trip to {brief.destination or 'your destination'}."]
    for day in itinerary:
        lines.append(f"Day {day.day_number} ({day.date}): {', '.join(day.activities)}")
    for warning in warnings:
        lines.append(f"Note: {warning}.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add travel_agent/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add orchestrator tying diff, parallel agents, and fallback together"
```

---

### Task 11: FastAPI App

**Files:**
- Create: `travel_agent/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `create_session`, `load_session`, `save_session` from `travel_agent.db` (Task 2); `handle_turn`, `TurnResult` from `travel_agent.orchestrator` (Task 10); `settings` from `travel_agent.config` (Task 1).
- Produces: `app` (FastAPI instance) in `travel_agent.main`, with `POST /sessions -> {"session_id": str}` (201) and `POST /sessions/{session_id}/messages` body `{"content": str}` -> `{"reply": str, "trip_brief": {...}, "flight_candidates": [...], "hotel_candidates": [...], "itinerary": [...], "warnings": [...]}` (200), or 404 if the session doesn't exist.

- [ ] **Step 1: Write the failing test**

`tests/test_main.py`:

```python
import pytest
from fastapi.testclient import TestClient

from travel_agent import main
from travel_agent.orchestrator import TurnResult
from travel_agent.schemas import TripBrief


@pytest.fixture
def api_client(db_ready):
    return TestClient(main.app)


def test_create_session_returns_id(api_client):
    resp = api_client.post("/sessions")
    assert resp.status_code == 201
    assert "session_id" in resp.json()


def test_post_message_to_missing_session_returns_404(api_client):
    resp = api_client.post("/sessions/does-not-exist/messages", json={"content": "hi"})
    assert resp.status_code == 404


async def test_post_message_returns_turn_result(api_client, monkeypatch):
    create_resp = api_client.post("/sessions")
    session_id = create_resp.json()["session_id"]

    fake_result = TurnResult(
        reply="Here's your plan.",
        trip_brief=TripBrief(destination="Paris", interests=[]),
        flight_candidates=[],
        hotel_candidates=[],
        itinerary=[],
        warnings=["couldn't fetch live flight data right now"],
    )

    async def fake_handle_turn(client, amadeus, session, user_message):
        assert user_message == "Plan a trip to Paris"
        return fake_result

    monkeypatch.setattr(main, "handle_turn", fake_handle_turn)

    resp = api_client.post(f"/sessions/{session_id}/messages", json={"content": "Plan a trip to Paris"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Here's your plan."
    assert body["trip_brief"]["destination"] == "Paris"
    assert body["warnings"] == ["couldn't fetch live flight data right now"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `travel_agent.main` does not exist yet.

- [ ] **Step 3: Implement the FastAPI app**

`travel_agent/main.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests across all tasks — roughly 40 tests)

- [ ] **Step 6: Commit**

```bash
git add travel_agent/main.py tests/test_main.py
git commit -m "feat: add FastAPI endpoints for session creation and chat turns"
```

---

## Post-Plan Notes

- `AMADEUS_BASE_URL` defaults to Amadeus's free "test" environment (`https://test.api.amadeus.com`), which has limited/synthetic inventory but real request/response shapes — sufficient for the "real API, not fabricated data" goal without needing a production Amadeus contract.
- `DATABASE_URL` defaults to local SQLite for zero-config `uvicorn travel_agent.main:app` runs; set it to a Postgres URL (per spec §3) for anything beyond local development.
- The landing page / 3D treatment (spec §7) is explicitly out of scope for this plan — revisit once `pytest -v` is green end-to-end and the API has been exercised manually (e.g. via `curl` or the FastAPI `/docs` page) with real `ANTHROPIC_API_KEY`/`AMADEUS_CLIENT_ID`/`AMADEUS_CLIENT_SECRET` values.
