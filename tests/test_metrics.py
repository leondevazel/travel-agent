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


def test_session_and_turn_ids_default_to_none(tmp_path, monkeypatch):
    log_path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", log_path)

    record = metrics.record_agent_call(
        agent_name="planner", latency_ms=1.0, input_tokens=1, output_tokens=1, success=True
    )

    assert record["session_id"] is None
    assert record["turn_id"] is None
    assert json.loads(log_path.read_text().strip())["turn_id"] is None


def test_session_and_turn_ids_are_recorded_when_given(tmp_path, monkeypatch):
    log_path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", log_path)

    record = metrics.record_agent_call(
        agent_name="turn",
        latency_ms=1234.0,
        input_tokens=0,
        output_tokens=0,
        success=True,
        session_id="sess-1",
        turn_id="turn-1",
    )

    assert record["session_id"] == "sess-1"
    assert record["turn_id"] == "turn-1"
    logged = json.loads(log_path.read_text().strip())
    assert logged["session_id"] == "sess-1"
    assert logged["turn_id"] == "turn-1"


def test_cost_is_priced_per_model(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "METRICS_PATH", tmp_path / "m.jsonl")

    sonnet = metrics.record_agent_call(
        agent_name="itinerary", latency_ms=1.0, input_tokens=1_000_000,
        output_tokens=0, success=True, model="claude-sonnet-5",
    )
    haiku = metrics.record_agent_call(
        agent_name="flight", latency_ms=1.0, input_tokens=1_000_000,
        output_tokens=0, success=True, model="claude-haiku-4-5-20251001",
    )
    unknown = metrics.record_agent_call(
        agent_name="flight", latency_ms=1.0, input_tokens=1_000_000,
        output_tokens=0, success=True, model="something-new",
    )

    assert sonnet["cost_usd"] == 2.0
    assert haiku["cost_usd"] == 1.0
    # An unrecognised model must not silently under-report.
    assert unknown["cost_usd"] == 2.0
