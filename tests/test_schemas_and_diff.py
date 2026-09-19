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
        locations=["Louvre"],
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


def test_diff_additional_destinations_change_reruns_everything():
    old = _brief(additional_destinations=[])
    new = _brief(additional_destinations=["Tokyo"])
    assert diff_trip_brief(old, new) == {"flight", "hotel", "itinerary"}


def test_diff_must_visit_change_reruns_itinerary_only():
    old = _brief(must_visit=[])
    new = _brief(must_visit=["Eiffel Tower"])
    assert diff_trip_brief(old, new) == {"itinerary"}
