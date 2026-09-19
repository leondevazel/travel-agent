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

        if response.stop_reason != "tool_use":
            raise AgentError(f"expected tool_use, got stop_reason={response.stop_reason!r}")

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

        if not tool_results:
            raise AgentError("tool_use turn produced no client tool results and no final answer")

        messages = messages + [{"role": "user", "content": tool_results}]

    raise AgentError(f"max_turns={max_turns} exceeded without a final answer")
