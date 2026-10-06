"""Convert single simulation events into ATIF steps.

One function per event kind. Each takes the ``step_id`` the trajectory assigns, so
numbering stays with the trajectory builder.
"""

from glossogen.atif_export.atif_models import (
    AtifMetrics,
    AtifObservation,
    AtifObservationResult,
    AtifStep,
    AtifStepSource,
    AtifToolCall,
)
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    ContextCompacted,
    InjectionDelivered,
    LLMResponseReceived,
    ToolResultReceived,
    WorldEventDelivered,
)
from glossogen.models.event_base import TokenUsage
from glossogen.token_pricing import TokenPricing, compute_token_cost_usd


def build_system_prompt_step(step_id: int, registration: AgentRegistered) -> AtifStep:
    """The system prompt the agent was registered with."""
    return AtifStep(
        step_id=step_id,
        timestamp=registration.timestamp.isoformat(),
        source=AtifStepSource.SYSTEM,
        message=registration.system_prompt,
        model_name=None,
        reasoning_content=None,
        tool_calls=None,
        observation=None,
        metrics=None,
        extra={"kind": "system_prompt", "round_number": registration.round_number},
    )


def build_delivered_text_step(
    step_id: int,
    event: InjectionDelivered | WorldEventDelivered,
) -> AtifStep:
    """A scenario injection or world notification, which reaches the agent as a user turn."""
    if isinstance(event, InjectionDelivered):
        kind = "injection"
    else:
        kind = "world_event"
    return AtifStep(
        step_id=step_id,
        timestamp=event.timestamp.isoformat(),
        source=AtifStepSource.USER,
        message=event.text,
        model_name=None,
        reasoning_content=None,
        tool_calls=None,
        observation=None,
        metrics=None,
        extra={"kind": kind, "round_number": event.round_number},
    )


def build_compaction_step(step_id: int, event: ContextCompacted) -> AtifStep:
    """The summary that replaced the agent's earlier history when the provider compacted it."""
    return AtifStep(
        step_id=step_id,
        timestamp=event.timestamp.isoformat(),
        source=AtifStepSource.SYSTEM,
        message=event.summary_text,
        model_name=None,
        reasoning_content=None,
        tool_calls=None,
        observation=None,
        metrics=None,
        extra={
            "kind": "compaction",
            "round_number": event.round_number,
            "provider_name": event.provider_name,
            "summary_char_count": event.summary_char_count,
        },
    )


def build_agent_step(
    step_id: int,
    event: LLMResponseReceived,
    model_name: str,
    pricing: TokenPricing | None,
    results_by_call_id: dict[str, ToolResultReceived],
    failed_cycles: list[AgentRunCycleFailed],
) -> AtifStep:
    """One LLM response, its tool calls, and the results those calls returned.

    ``failed_cycles`` are the cycles that raised since the previous response; they
    are recorded on this step because a failed cycle produced no turn of its own.
    """
    extra: dict[str, object] = {
        "round_number": event.round_number,
        "stop_reason": event.stop_reason,
    }
    if failed_cycles:
        extra["failed_cycles"] = [
            {"cycle": failure.cycle, "error_type": failure.error_type, "message": failure.message}
            for failure in failed_cycles
        ]
    message = ""
    if event.text is not None:
        message = event.text
    return AtifStep(
        step_id=step_id,
        timestamp=event.timestamp.isoformat(),
        source=AtifStepSource.AGENT,
        message=message,
        model_name=model_name,
        reasoning_content=event.thinking,
        tool_calls=_build_tool_calls(event=event),
        observation=_build_observation(event=event, results_by_call_id=results_by_call_id),
        metrics=build_step_metrics(usage=event.usage, pricing=pricing),
        extra=extra,
    )


def build_step_metrics(usage: TokenUsage, pricing: TokenPricing | None) -> AtifMetrics | None:
    """ATIF metrics from the token usage logged on one response, or ``None`` when it logged none.

    The runner records usage once per agent cycle, on the cycle's last response, and
    zeros on the others. A step's metrics therefore cover every LLM call of the cycle
    it closes, which ``extra.usage_scope`` states. Cost is ``None`` for an unpriced model.
    """
    if (
        usage.input_tokens
        + usage.output_tokens
        + usage.cache_read_input_tokens
        + usage.cache_creation_input_tokens
        == 0
    ):
        return None
    cost_usd: float | None = None
    if pricing is not None:
        cost_usd = compute_token_cost_usd(
            pricing=pricing,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens,
            cache_write_tokens=usage.cache_creation_input_tokens,
        )
    return AtifMetrics(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
        cached_tokens=usage.cache_read_input_tokens,
        cost_usd=cost_usd,
        extra={
            "usage_scope": "agent_cycle",
            "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        },
    )


def _build_tool_calls(event: LLMResponseReceived) -> list[AtifToolCall] | None:
    if not event.tool_calls:
        return None
    return [
        AtifToolCall(
            tool_call_id=call.call_id,
            function_name=call.tool_name,
            arguments=call.arguments,
        )
        for call in event.tool_calls
    ]


def _build_observation(
    event: LLMResponseReceived,
    results_by_call_id: dict[str, ToolResultReceived],
) -> AtifObservation | None:
    results = [
        AtifObservationResult(
            source_call_id=call.call_id,
            content=results_by_call_id[call.call_id].result,
        )
        for call in event.tool_calls
        if call.call_id in results_by_call_id
    ]
    if not results:
        return None
    return AtifObservation(results=results)
