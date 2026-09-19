from travel_agent.schemas import TripBrief

CORE_FIELDS = ("destination", "origin", "additional_destinations", "start_date", "end_date", "budget_usd")
ITINERARY_FIELDS = ("interests", "pace", "must_visit")


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
