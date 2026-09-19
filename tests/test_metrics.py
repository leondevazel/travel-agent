import json

from travel_agent import metrics


def test_record_agent_call_appends_jsonl_and_computes_cost(tmp_path, monkeypatch):
    log_path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", log_path)

    record = metrics.record_agent_call(
        agent_name="planner", latency_ms=123.4, input_tokens=1000, output_tokens=200, success=True
    )

    assert record["agent"] == "planner"
    assert record["success"] is True
    assert record["cost_usd"] == round(
        (1000 / 1_000_000) * metrics.INPUT_COST_PER_MTOK + (200 / 1_000_000) * metrics.OUTPUT_COST_PER_MTOK, 6
    )

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["agent"] == "planner"


def test_record_agent_call_appends_multiple_records(tmp_path, monkeypatch):
    log_path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", log_path)

    metrics.record_agent_call(agent_name="flight", latency_ms=50.0, input_tokens=10, output_tokens=2, success=True)
    metrics.record_agent_call(agent_name="hotel", latency_ms=999.0, input_tokens=0, output_tokens=0, success=False)

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["success"] is False
