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
