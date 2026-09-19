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
    # Extra cities/countries after `destination`, in the order the user
    # wants to visit them (e.g. destination="Tokyo",
    # additional_destinations=["Osaka"] for a Tokyo-then-Osaka trip).
    additional_destinations: list[str] = Field(default_factory=list)
    # Specific places the user wants guaranteed a spot in the itinerary
    # (e.g. "Eiffel Tower"), as opposed to `interests`, which are general
    # themes (e.g. "art") the Itinerary agent uses to pick activities.
    must_visit: list[str] = Field(default_factory=list)
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
