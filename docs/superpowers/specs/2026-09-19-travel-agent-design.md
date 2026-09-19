# AI Travel Planning Agent — Design Spec

Status: design approved by user (backend architecture), implementation not started.
Path: architectural (per superpowers:brainstorming skill).

## 1. Purpose

Build a genuinely "wow" project — for both interviewers and the general
public — after concluding that the prior project (enterprise-ai-search,
a measured BM25-vs-vector search console) was strong for interview
depth but not a scroll-stopping first impression.

Explicit goal from the user: "면접관이든 대중이든 진짜 와 하게 만드는
그런거" (something that makes either interviewers or the general public
go "wow"). Landed on a travel planning agent after narrowing:
- wow source: undecided upfront, converged on "an agent that actually
  does something impressive" rather than pure visual polish or a novel
  concept
- task: a multi-agent system that autonomously researches and produces
  a high-completeness trip itinerary (NOT an agent that executes real
  bookings/payments — out of scope, and safer)
- data: must use real flight/hotel price APIs (e.g. Amadeus free tier),
  not just LLM knowledge — same "real data, not fabricated" principle
  as the previous project
- interaction: chat-based, multi-turn refinement (e.g. "2일차 느슨하게
  바꿔줘" should only re-run what's actually affected)
- architecture: explicitly chose multi-agent (planner + specialist
  agents) over a single tool-calling agent or a deterministic pipeline,
  accepting the added complexity for the more impressive
  architecture story

## 2. Architecture

```
User (chat)
    |
Orchestrator (FastAPI)
    |
Planner Agent (Claude) -- extracts/updates structured trip brief from
    |                      the conversation (destination, dates, budget,
    |                      interests, pace)
    | (re-runs only the specialist agents affected by what changed)
    |-- Flight Agent (Claude + Amadeus flight search tool)
    |-- Hotel Agent (Claude + Amadeus hotel search tool)
    `-- Itinerary Agent (Claude + weather/attractions tools) -- composes
                          the day-by-day plan from flight/hotel results
    |
Response + updated itinerary (persisted per session)
```

Key design decision: the orchestrator diffs the trip brief between
turns and only re-invokes the specialist agent(s) whose relevant inputs
actually changed (e.g. "make day 2 more relaxed" only re-runs the
Itinerary Agent, not Flight/Hotel). This is deliberately the same "don't
use AI everywhere, only where needed" principle from the previous
project — cuts cost and latency, and is a concrete talking point for
interviews ("parallelized what could run concurrently, skipped what
didn't need to re-run").

## 3. Components

- **TripSession** (Postgres): session id, message history, trip brief
  (JSON), flight candidates (JSON), hotel candidates (JSON), current
  itinerary (JSON)
- **agents/**: `planner.py`, `flight_agent.py`, `hotel_agent.py`,
  `itinerary_agent.py` — each a separate Claude call with a focused
  system prompt and its own tool(s)
- **tools/**: `amadeus_client.py` (real flight + hotel search),
  `weather_client.py`; attraction/things-to-do info via Claude's
  built-in web search tool rather than a bespoke scraper

## 4. Data Flow

1. User sends a chat message.
2. Planner Agent updates the structured trip brief from the full
   conversation so far.
3. Orchestrator diffs the new brief against the previous one to decide
   which specialist agent(s) need to re-run.
4. Flight Agent and Hotel Agent (when needed) run in parallel.
5. Itinerary Agent composes/updates the day-by-day plan from the trip
   brief + flight/hotel results (+ weather/attractions).
6. Response returned to the user; full state persisted to TripSession
   for the next turn.

## 5. Error Handling

- Amadeus API failure or rate limit -> fall back to a cached/prior
  result or a clear "couldn't fetch live prices right now" message —
  never silently fabricate a price.
- If one specialist agent times out during a parallel run, return a
  partial itinerary from the agents that did complete rather than
  failing the whole turn.

## 6. Measurement (lighter than the previous project, but not absent)

Not a Recall@K/MRR-style eval this time (different problem shape), but
still log: per-agent latency, cost per completed trip plan, API
failure rate. Enough to say in an interview "parallelizing flight+hotel
search cut planning time from X to Y seconds" — with a real measured
number, not an estimate, consistent with the "never estimate, always
measure" rule carried over from the prior project.

## 7. Explicitly Out of Scope (for now)

- Real booking/payment execution (safety + complexity; the itinerary
  is the deliverable, not a completed purchase).
- The landing page's 3D/animation treatment — user wants a genuinely
  cute, travel-themed (planes, landscapes, characters) 3D-feeling
  landing page. Discussed but deliberately deferred until the backend
  is working:
  - Bespoke custom 3D character modeling is out of reach (no 3D
    modeling/rigging tool or text-to-3D generator available) — noted
    explicitly to the user, not glossed over.
  - Realistic path discussed: Three.js (hand-coded low-poly 3D scenes)
    + free CC0 3D assets (e.g. Kenney.nl, Sketchfab CC0) + possibly
    Lottie animations for 2.5D illustrated moments. No final decision
    made yet — revisit once backend works.

## 8. Next Steps

1. User review of this spec (this file).
2. Invoke the writing-plans skill to produce an implementation plan
   (TDD-based, per superpowers workflow) for the backend
   (Planner/Flight/Hotel/Itinerary agents + orchestrator + TripSession
   persistence) — landing page/animation work comes after the backend
   works end-to-end.

## Resuming this project in a new session

This spec is the persistence mechanism across sessions (a fresh session
has no memory of the conversation that produced it). To resume: open a
new session in this repo and say "read
docs/superpowers/specs/2026-09-19-travel-agent-design.md and continue
from there."
