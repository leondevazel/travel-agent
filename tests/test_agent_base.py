from dataclasses import dataclass, field

import pytest

from travel_agent.agents.base import AgentError, run_agent_loop


@dataclass
class FakeBlock:
    type: str
    name: str = ""
    input: dict = field(default_factory=dict)
    id: str = "block-1"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage


class FakeMessagesAPI:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessagesAPI(responses)


async def test_single_turn_final_tool_call_returns_output():
    response = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit", input={"answer": 42})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=100, output_tokens=20),
    )
    client = FakeClient([response])

    async def executor(name, input):
        raise AssertionError("should not be called for a single-shot final tool")

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
        tool_choice={"type": "tool", "name": "submit"},
    )

    assert result.output == {"answer": 42}
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20


async def test_client_tool_is_executed_then_final_tool_returns_output():
    search_call = FakeResponse(
        content=[FakeBlock(type="tool_use", name="search", input={"q": "paris"}, id="call-1")],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=50, output_tokens=10),
    )
    final_call = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit", input={"results": ["a"]})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=60, output_tokens=15),
    )
    client = FakeClient([search_call, final_call])

    executed = []

    async def executor(name, input):
        executed.append((name, input))
        return {"found": ["a"]}

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"name": "search"}, {"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names={"search"},
    )

    assert executed == [("search", {"q": "paris"})]
    assert result.output == {"results": ["a"]}
    assert client.messages.calls[1]["messages"][-1]["content"][0]["tool_use_id"] == "call-1"


async def test_server_tool_use_block_is_skipped_not_executed():
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "paris"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(type="tool_use", name="submit", input={"ok": True}),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=10, output_tokens=5),
    )
    client = FakeClient([response])

    async def executor(name, input):
        raise AssertionError("server tools must not be routed to the local executor")

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"type": "web_search_20250305", "name": "web_search"}, {"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
    )

    assert result.output == {"ok": True}


async def test_max_turns_exceeded_raises_agent_error():
    non_final = FakeResponse(
        content=[FakeBlock(type="tool_use", name="search", input={})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=1, output_tokens=1),
    )
    client = FakeClient([non_final, non_final])

    async def executor(name, input):
        return {}

    with pytest.raises(AgentError):
        await run_agent_loop(
            client=client,
            model="claude-sonnet-5",
            system_prompt="sys",
            user_message="go",
            tools=[{"name": "search"}, {"name": "submit"}],
            final_tool_name="submit",
            tool_executor=executor,
            client_tool_names={"search"},
            max_turns=2,
        )


async def test_unrecognized_tool_use_alongside_final_tool_still_returns():
    response = FakeResponse(
        content=[
            FakeBlock(type="tool_use", name="mystery_tool", input={"x": 1}, id="call-x"),
            FakeBlock(type="tool_use", name="submit", input={"ok": True}, id="call-final"),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=10, output_tokens=5),
    )
    client = FakeClient([response])

    async def executor(name, input):
        raise AssertionError("unrecognized tools must not be routed to the local executor")

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
    )

    assert result.output == {"ok": True}
    assert len(client.messages.calls) == 1


async def test_end_turn_with_no_tool_call_is_nudged_toward_final_tool():
    # The model only used a server tool, then answered in plain text instead
    # of calling the final tool -- observed live with Haiku on the flight/
    # hotel agents (searches, then summarizes instead of submitting).
    text_only_turn = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "paris flights"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(type="text", input={}),
        ],
        stop_reason="end_turn",
        usage=FakeUsage(input_tokens=50, output_tokens=30),
    )
    final_turn = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit", input={"ok": True})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=20, output_tokens=10),
    )
    client = FakeClient([text_only_turn, final_turn])

    async def executor(name, input):
        raise AssertionError("no client tools in this scenario")

    result = await run_agent_loop(
        client=client,
        model="claude-haiku-4-5-20251001",
        system_prompt="sys",
        user_message="go",
        tools=[{"type": "web_search_20250305", "name": "web_search"}, {"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
    )

    assert result.output == {"ok": True}
    assert len(client.messages.calls) == 2
    nudge_message = client.messages.calls[1]["messages"][-1]
    assert nudge_message["role"] == "user"
    assert "submit" in nudge_message["content"]
    assert client.messages.calls[1]["tool_choice"] == {"type": "tool", "name": "submit"}


async def test_pause_turn_continues_without_nudge_message():
    paused_turn = FakeResponse(
        content=[FakeBlock(type="server_tool_use", name="web_search", input={"query": "paris hotels"})],
        stop_reason="pause_turn",
        usage=FakeUsage(input_tokens=40, output_tokens=5),
    )
    final_turn = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit", input={"ok": True})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=20, output_tokens=10),
    )
    client = FakeClient([paused_turn, final_turn])

    async def executor(name, input):
        raise AssertionError("no client tools in this scenario")

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"type": "web_search_20250305", "name": "web_search"}, {"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
    )

    assert result.output == {"ok": True}
    # No synthetic nudge message inserted -- the paused assistant turn is
    # resent unchanged, per Anthropic's documented pause_turn protocol.
    assert client.messages.calls[1]["messages"][-1]["role"] == "assistant"
    assert "tool_choice" not in client.messages.calls[1]


async def test_unrecognized_tool_use_alone_sends_error_tool_result_next_turn():
    unknown_turn = FakeResponse(
        content=[FakeBlock(type="tool_use", name="mystery_tool", input={"x": 1}, id="call-x")],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=10, output_tokens=5),
    )
    final_turn = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit", input={"ok": True}, id="call-final")],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=8, output_tokens=4),
    )
    client = FakeClient([unknown_turn, final_turn])

    async def executor(name, input):
        raise AssertionError("unrecognized tools must not be routed to the local executor")

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt="sys",
        user_message="go",
        tools=[{"name": "submit"}],
        final_tool_name="submit",
        tool_executor=executor,
        client_tool_names=set(),
    )

    assert result.output == {"ok": True}
    sent = client.messages.calls[1]["messages"][-1]["content"][0]
    assert sent["tool_use_id"] == "call-x"
    assert sent["is_error"] is True
