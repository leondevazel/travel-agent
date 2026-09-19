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
    origin: str
    destination: str
    # Optional on purpose: web search reliably yields carrier + price, but
    # rarely exact times or stop counts. Requiring them made the agent
    # refuse to submit anything at all rather than invent them.
    departure_time: str | None = None
    arrival_time: str | None = None
    stops: int | None = None
    booking_url: str | None = None


class HotelCandidate(BaseModel):
    name: str
    price_usd_per_night: float
    rating: float | None = None
    address: str
    booking_url: str | None = None


class ItineraryDay(BaseModel):
    day_number: int
    date: datetime.date
    # Every notable place visited this day, in visit order (e.g.
    # ["Gyeongbokgung Palace", "Bukchon Hanok Village", "Insadong"]). Each
    # must be specific enough to look up a real photo for -- not a vague
    # area like "downtown" or the city name alone. The frontend shows one
    # image per entry, so a day with three stops shows three photos.
    locations: list[str]
    activities: list[str]
    notes: str = ""
