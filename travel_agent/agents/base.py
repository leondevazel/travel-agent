import json
import time
from dataclasses import dataclass
from typing import Awaitable, Callable


class AgentError(Exception):
    pass


@dataclass
class AgentUsage:
    input_tokens: int
    output_tokens: int
    latency_ms: float


@dataclass
class AgentResult:
    output: dict
    usage: AgentUsage


# stop_reasons that mean "the turn produced something usable, keep going":
# tool_use is the normal case, end_turn can happen when the model only used
# a server tool (e.g. web_search) and then answered in plain text instead of
# calling the final tool, and pause_turn is Anthropic's documented mid-search
# continuation signal. Anything else (e.g. max_tokens) is a real failure.
_CONTINUABLE_STOP_REASONS = {"tool_use", "end_turn", "pause_turn"}


async def run_agent_loop(
    client,
    model: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    final_tool_name: str,
    tool_executor: Callable[[str, dict], Awaitable[dict]],
    client_tool_names: set[str],
    tool_choice: dict | None = None,
    max_turns: int = 5,
) -> AgentResult:
    start = time.monotonic()
    messages: list[dict] = [{"role": "user", "content": user_message}]
    input_tokens = 0
    output_tokens = 0

    for _ in range(max_turns):
        create_kwargs = dict(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice

        response = await client.messages.create(**create_kwargs)
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        if response.stop_reason not in _CONTINUABLE_STOP_REASONS:
            raise AgentError(f"unexpected stop_reason={response.stop_reason!r}")

        messages = messages + [{"role": "assistant", "content": response.content}]

        final_output = None
        tool_results = []
        for block in response.content:
            if block.type == "tool_use" and block.name == final_tool_name:
                final_output = block.input
            elif block.type == "tool_use" and block.name in client_tool_names:
                result = await tool_executor(block.name, block.input)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)}
                )
            elif block.type == "tool_use":
                # Unknown client tool: still answer it, otherwise the next
                # request would carry a tool_use with no matching tool_result
                # and the API would reject the whole conversation.
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"error: unrecognized tool {block.name!r}",
                        "is_error": True,
                    }
                )
            # server_tool_use / web_search_tool_result / other server-executed
            # blocks are already resolved by Anthropic and need no local action.

        if final_output is not None:
            return AgentResult(
                output=final_output,
                usage=AgentUsage(input_tokens, output_tokens, (time.monotonic() - start) * 1000),
            )

        if tool_results:
            messages = messages + [{"role": "user", "content": tool_results}]
            continue

        if response.stop_reason == "pause_turn":
            # Anthropic's documented mid-search continuation: resend the
            # paused assistant message (already appended above) unchanged.
            continue

        # stop_reason was "end_turn" with no client tool call and no final
        # tool call -- the model used only server tools (or none at all) and
        # then answered in plain text instead of submitting its final
        # answer. Nudge it to call the final tool explicitly rather than
        # treating this as a hard failure.
        messages = messages + [
            {
                "role": "user",
                "content": f"Call {final_tool_name} now with your final answer based on what you found.",
            }
        ]
        tool_choice = {"type": "tool", "name": final_tool_name}

    raise AgentError(f"max_turns={max_turns} exceeded without a final answer")
