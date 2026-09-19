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
- data: must use real, live-sourced flight/hotel prices, not just LLM
  knowledge — same "real data, not fabricated" principle as the
  previous project. Originally planned around the Amadeus free
  self-service API; that tier was decommissioned (July 2025 — the
  portal is now Enterprise-only, sales-gated, not viable for a
  portfolio project). Revised 2026-09-19: Flight and Hotel agents use
  Claude's hosted `web_search` tool (same mechanism the Itinerary
  agent already uses for attractions) instead of a dedicated flight/
  hotel API — grounds prices in real, cited web search results rather
  than a structured price feed. Less precise than a purpose-built
  API, but avoids an unusable/enterprise-gated dependency and keeps
  the "real data" principle intact. `amadeus_client.py` removed.
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
    |-- Flight Agent (Claude + hosted web_search tool)
    |-- Hotel Agent (Claude + hosted web_search tool)
    `-- Itinerary Agent (Claude + weather tool + hosted web_search) --
                          composes the day-by-day plan from flight/hotel
                          results
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
  system prompt and its own tool(s). Flight/Hotel/Itinerary all use
  Claude's hosted `web_search` tool (capped via `max_uses`) rather
  than a bespoke scraper or a dedicated flight/hotel API.
- **tools/**: `weather_client.py` (Open-Meteo, real forecast data)

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

- Flight/Hotel search failure (Anthropic API error, no usable search
  results, or a submitted candidate that doesn't match a real search
  result) -> fall back to a cached/prior result or a clear "couldn't
  fetch live prices right now" message — never silently fabricate a
  price.
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

## 7. Landing Page / Interactive Frontend (deferred until backend works)

User wants a genuinely "wow", professional-grade interactive landing
page — not just static visual polish. Concrete moments called out:

- **Traveler count picker**: selecting party size adds/removes
  character illustrations one at a time with a bounce/fade animation
  (not an instant swap).
- **Country picker**: selecting a destination shows that country's
  representative landmark/scenery (e.g. Eiffel Tower for France, Fuji
  + torii for Japan) in a small 3D scene.
- **Trip-generation transition**: while the agents are working, show
  a "~로 떠나는 중..." moment — the user's character boards a plane/boat
  and travels, to amplify anticipation rather than a plain loading
  spinner.

Claude's own artifact/frontend-design tooling can build and integrate
the interaction logic and code, but cannot originate polished
character illustration or 3D asset design/rigging itself (no
image/3D-generation tool available). Decision: **outsource asset and
animation creation to specialized no-code tools, integrate their
exported output in code.**

- **Rive** (rive.app) — character animations driven by state machines;
  fits the traveler-count add/remove animation and the plane/boat
  trip-transition moment. Exports a `.riv` file, embedded via the
  `@rive-app/react-canvas` web runtime.
- **Spline** (spline.design) — no-code 3D scene editor with
  text-to-3D/material generation and an easy React embed
  (`@splinetool/react-spline`); fits the per-country landmark/scenery
  scene on selection.
- **LottieFiles** (lottiefiles.com) — fallback for short, lightweight
  looping transition animations if Rive proves heavier than needed for
  a given moment.

Draft prompts already written for Rive (traveler character set +
count state machine) and Spline (per-country low-poly landmark scene)
— see the session that produced this spec update; reuse and refine
them when this phase starts. Division of labor: assets/animations are
authored in Rive/Spline by the user (or a designer), Claude integrates
the exported files into the React/Next.js frontend and wires them to
app state (party size, selected country, generation-in-progress).

- Real booking/payment execution stays out of scope entirely (safety +
  complexity; the itinerary is the deliverable, not a completed
  purchase).

## 8. Next Steps

1. ~~User review of this spec (this file).~~ Done — spec approved,
   frontend direction (§7) added after user follow-up.
2. Backend implementation plan written via the writing-plans skill:
   `docs/superpowers/plans/2026-09-19-travel-agent-backend-plan.md`
   (TDD-based, 11 tasks: scaffolding+schemas+diff, TripSession
   persistence, Amadeus client, weather client, shared agent tool-use
   loop, Planner/Flight/Hotel/Itinerary agents, metrics, orchestrator,
   FastAPI app). Executed via subagent-driven-development: all 11
   tasks done, individually reviewed, plus a final whole-branch review
   (9 Important findings fixed in one wave). 60/60 tests passing.
   Opened as PR #1 (`worktree-travel-agent-backend` -> `master`) on
   `github.com/leondevazel/travel-agent`.
3. Pre-smoke-test discovery: Amadeus's free self-service API was
   decommissioned (§1 note) before a real-API smoke test could run.
   Replaced the Amadeus client in Flight/Hotel agents with Claude's
   hosted `web_search` tool (same pattern Itinerary already used) —
   see §1 and §3. `amadeus_client.py` and its tests removed;
   `flight_agent.py`/`hotel_agent.py` rewritten around `web_search`.
4. Real-API smoke test (real `ANTHROPIC_API_KEY`, no Amadeus needed
   anymore) — next up.
5. Landing page/animation work (§7) starts once the backend plan is
   fully green end-to-end against real APIs.

## Resuming this project in a new session

This spec is the persistence mechanism across sessions (a fresh session
has no memory of the conversation that produced it). To resume: open a
new session in this repo and say "read
docs/superpowers/specs/2026-09-19-travel-agent-design.md and continue
from there."
