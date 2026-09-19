import json
import time
from pathlib import Path

from travel_agent.config import settings

METRICS_PATH = Path(settings.metrics_log_path)

# USD per million tokens (docs.claude.com/pricing), per model, since the
# agents deliberately don't all run on the same one. Still excludes the
# $10/1,000-searches web_search tool fee, which the search-using agents
# (flight/hotel/itinerary) incur separately and this module doesn't track.
MODEL_PRICING = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}
INPUT_COST_PER_MTOK, OUTPUT_COST_PER_MTOK = MODEL_PRICING["claude-sonnet-5"]


def _pricing(model: str | None) -> tuple[float, float]:
    """Unknown or missing model prices as Sonnet, i.e. never under-reports."""
    return MODEL_PRICING.get(model or "", (INPUT_COST_PER_MTOK, OUTPUT_COST_PER_MTOK))


def record_agent_call(
    agent_name: str,
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    success: bool,
    session_id: str | None = None,
    turn_id: str | None = None,
    error_type: str | None = None,
    model: str | None = None,
) -> dict:
    """Append one JSONL metrics record.

    ``session_id``/``turn_id`` correlate every agent call within a single
    conversational turn, so cost per completed trip plan and turn-level
    wall-clock latency can be derived from the log.
    """
    input_price, output_price = _pricing(model)
    cost_usd = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    record = {
        "agent": agent_name,
        "session_id": session_id,
        "turn_id": turn_id,
        "model": model,
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
