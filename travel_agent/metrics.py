import json
import time
from pathlib import Path

from travel_agent.config import settings

METRICS_PATH = Path(settings.metrics_log_path)

# USD per million tokens, claude-sonnet-5 pricing (docs.claude.com/pricing).
# Applied uniformly to every agent call regardless of which model actually
# served it (Flight/Hotel run on Haiku 4.5, roughly half this rate), so
# logged cost is a conservative (over-)estimate for those two agents, not
# an exact figure. Also excludes the $10/1,000-searches web_search tool fee,
# which agents using web_search (flight/hotel/itinerary) incur separately
# and this module does not currently track.
INPUT_COST_PER_MTOK = 2.0
OUTPUT_COST_PER_MTOK = 10.0


def record_agent_call(
    agent_name: str,
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    success: bool,
    session_id: str | None = None,
    turn_id: str | None = None,
    error_type: str | None = None,
) -> dict:
    """Append one JSONL metrics record.

    ``session_id``/``turn_id`` correlate every agent call within a single
    conversational turn, so cost per completed trip plan and turn-level
    wall-clock latency can be derived from the log.
    """
    cost_usd = (input_tokens / 1_000_000) * INPUT_COST_PER_MTOK + (output_tokens / 1_000_000) * OUTPUT_COST_PER_MTOK
    record = {
        "agent": agent_name,
        "session_id": session_id,
        "turn_id": turn_id,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "success": success,
        "error_type": error_type,
        "timestamp": time.time(),
    }
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record
