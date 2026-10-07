"""Pydantic models for the Agent Trajectory Interchange Format (ATIF).

Mirror the subset of Harbor's ``harbor.models.trajectories`` schema that a glossogen
run can fill. Field names and nesting follow the published spec, so
``AtifTrajectory.model_dump(mode="json", exclude_none=True)`` is a valid ATIF document.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

ATIF_SCHEMA_VERSION = "ATIF-v1.8"


class AtifStepSource(str, Enum):
    """Who originated a step."""

    SYSTEM = "system"
    USER = "user"
    AGENT = "agent"


class AtifToolCall(BaseModel):
    """One function invocation made by the agent."""

    tool_call_id: str
    function_name: str
    arguments: dict[str, Any]


class AtifObservationResult(BaseModel):
    """The result of one tool call, linked back by ``source_call_id``."""

    source_call_id: str
    content: str


class AtifObservation(BaseModel):
    """Environment feedback for the tool calls of one agent step."""

    results: list[AtifObservationResult]


class AtifMetrics(BaseModel):
    """Token usage and cost of the agent cycle one agent step closes.

    ``prompt_tokens`` includes cached tokens, as ATIF defines it.
    ``cost_usd`` is ``None`` when the model has no pricing entry.
    """

    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float | None
    extra: dict[str, Any]


class AtifStep(BaseModel):
    """One system, user, or agent turn.

    ``model_name``, ``reasoning_content``, ``tool_calls``, ``observation`` and
    ``metrics`` are only set on agent steps. ``is_copied_context`` is ``True`` on a
    step the agent received as history from another run or another seat, and
    ``None`` otherwise. ``timestamp`` is ``None`` on seed history and runner
    prompts, which record no times. ``llm_call_count`` is set on the agent step
    whose ``metrics`` aggregate a whole agent cycle: the number of responses in
    that cycle.
    """

    step_id: int
    timestamp: str | None
    source: AtifStepSource
    message: str
    model_name: str | None
    reasoning_content: str | None
    tool_calls: list[AtifToolCall] | None
    observation: AtifObservation | None
    metrics: AtifMetrics | None
    is_copied_context: bool | None
    llm_call_count: int | None
    extra: dict[str, Any]


class AtifAgent(BaseModel):
    """The agent the trajectory belongs to."""

    name: str
    version: str
    model_name: str
    tool_definitions: list[dict[str, Any]]
    extra: dict[str, Any]


class AtifFinalMetrics(BaseModel):
    """Totals over the steps played in this run.

    The token and cost totals are ``None`` when no step carries metrics, and
    ``total_cost_usd`` is also ``None`` when a model carrying usage has no pricing.
    """

    total_prompt_tokens: int | None
    total_completion_tokens: int | None
    total_cached_tokens: int | None
    total_cost_usd: float | None
    total_steps: int


class AtifTrajectory(BaseModel):
    """One agent's trajectory through one run, or through one generation of a swapped seat."""

    schema_version: Literal["ATIF-v1.8"]
    session_id: str
    trajectory_id: str
    agent: AtifAgent
    steps: list[AtifStep]
    final_metrics: AtifFinalMetrics
    extra: dict[str, Any]


class AtifAgentExport(BaseModel):
    """One agent's trajectories: a single one, or one per generation for a swapped seat."""

    trajectories: list[AtifTrajectory]
