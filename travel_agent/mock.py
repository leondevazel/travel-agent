"""Offline sample trip, for working on the UI without spending API money.

Enabled with MOCK_MODE=1. Every agent is skipped, so a turn costs nothing
and returns instantly, while still exercising the whole frontend: multiple
days, several photo-able locations per day, flights with and without a
booking link, hotels, and a warning banner.
"""

import datetime

from travel_agent.orchestrator import TurnResult
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, TripBrief

MOCK_WARNING = "MOCK MODE: 실제 검색 없이 샘플 데이터입니다 (요금 발생 없음)"


def mock_turn(user_message: str) -> TurnResult:
    start = datetime.date(2026, 11, 1)
    brief = TripBrief(
        destination="Seoul",
        origin="Busan",
        start_date=start,
        end_date=start + datetime.timedelta(days=2),
        budget_usd=500.0,
        interests=["history", "food"],
        pace="balanced",
    )

    itinerary = [
        ItineraryDay(
            day_number=1,
            date=start,
            locations=["Gyeongbokgung Palace", "Bukchon Hanok Village", "Insadong"],
            activities=[
                "Morning: Gyeongbokgung Palace and the royal guard-changing ceremony",
                "Afternoon: the hanok alleys of Bukchon",
                "Evening: tea houses and craft shops in Insadong",
            ],
            notes="Jongno district, all walkable.",
        ),
        ItineraryDay(
            day_number=2,
            date=start + datetime.timedelta(days=1),
            locations=["Jongmyo Shrine", "Gwangjang Market", "Cheonggyecheon"],
            activities=[
                "Morning: Jongmyo Shrine, the UNESCO-listed royal ancestral shrine",
                "Lunch: bindaetteok and mayak gimbap at Gwangjang Market",
                "Afternoon: walk the Cheonggyecheon stream",
            ],
            notes="Moves west to east across the old city.",
        ),
        ItineraryDay(
            day_number=3,
            date=start + datetime.timedelta(days=2),
            locations=["Changdeokgung Palace", "Namdaemun Market"],
            activities=[
                "Morning: Changdeokgung and its Secret Garden",
                "Midday: lunch and browsing at Namdaemun Market",
            ],
            notes="Lighter final day before the flight home.",
        ),
    ]

    flights = [
        FlightCandidate(
            carrier="Air Busan",
            price_usd=92.0,
            origin="Busan",
            destination="Seoul",
            booking_url="https://www.google.com/travel/flights",
        ),
        # Deliberately link-less, so the non-clickable row state gets exercised.
        FlightCandidate(carrier="Jin Air", price_usd=107.0, origin="Busan", destination="Seoul"),
    ]

    hotels = [
        HotelCandidate(
            name="Hotel Gracery Seoul",
            price_usd_per_night=95.0,
            rating=8.9,
            address="Jongno, Seoul",
            booking_url="https://www.booking.com",
        ),
        HotelCandidate(
            name="Toyoko Inn Seoul Dongdaemun",
            price_usd_per_night=70.0,
            rating=8.4,
            address="Dongdaemun, Seoul",
            booking_url="https://www.booking.com",
        ),
    ]

    reply = f"[mock] Updated your trip to Seoul. (echo: {user_message[:60]})"
    return TurnResult(
        reply=reply,
        trip_brief=brief,
        flight_candidates=flights,
        hotel_candidates=hotels,
        itinerary=itinerary,
        warnings=[MOCK_WARNING],
    )
