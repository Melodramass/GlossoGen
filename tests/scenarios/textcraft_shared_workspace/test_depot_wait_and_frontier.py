"""Depot waits, frontier recipe unlocking, private raw items and the nonzero depot view.

Tools are called directly, as the runner builds them, so the order of acts and
waits is the test's. A wait is started as a task and the test checks whether it
resumed after each act.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from glossogen.llm.token_counter import TokenCounter
from glossogen.runners.agent_tools import build_agent_tools, list_tool_definitions
from glossogen.runners.read_notifications_tool import RunTermination
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.scenarios.textcraft_shared_workspace.scenario import (
    TextcraftSharedWorkspaceScenario,
)
from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask, generate_task
from glossogen.testing.scenario_runtime import build_scenario

pytestmark = pytest.mark.xdist_group("textcraft_shared_workspace")

TWO_BY_TWO: dict[str, Any] = {
    "round_count": 1,
    "virtual_clock": False,
    "crafter_count": 2,
    "steps_per_agent": 2,
    "pool_agent_count": 2,
    "dag_cross_edge_density": 0.0,
    "comms_enabled": False,
}


class RecordingLogger:
    """Keeps logged events in memory."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def log(self, event: Any) -> None:
        self.events.append(event)


class WordCounter(TokenCounter):
    """Counts words, so no provider is contacted."""

    async def _count_impl(self, text: str) -> int:
        return len(text.split())


def local_token_counter(provider: str, model: str) -> TokenCounter:
    """Stand in for the provider-backed counter."""
    _ = provider, model
    return WordCounter()


class Wired:
    """A started round with each agent's tools built on demand."""

    def __init__(
        self, scenario: TextcraftSharedWorkspaceScenario, runtime: SimulationRuntime
    ) -> None:
        self.scenario = scenario
        self.runtime = runtime

    @property
    def task(self) -> WorkspaceTask:
        return self.scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]

    async def call(self, agent_id: str, tool_name: str, **arguments: Any) -> Any:
        tools = build_agent_tools(
            runtime=self.runtime, agent_id=agent_id, termination=RunTermination()
        )
        function: Any = {tool.name: tool.function for tool in tools}[tool_name]
        return await function(**arguments)

    def wait(self, agent_id: str, **arguments: Any) -> asyncio.Future[Any]:
        """Start a ``read_notifications`` call; it resumes when its wait does."""
        return asyncio.ensure_future(
            self.call(agent_id, "read_notifications", ctx=FakeContext(), **arguments)
        )

    def layer(self, index: int) -> list[str]:
        """The witness commands of one layer, in column order."""
        return [command for _, command in self.task.witness[index * 2 : (index + 1) * 2]]


class FakeContext:
    """The run context the tool reads: no sibling tool calls in the last response."""

    messages: list[Any] = []


async def wire(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, Any]) -> Wired:
    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter", local_token_counter
    )
    scenario = build_scenario(
        scenario_name="textcraft_shared_workspace",
        preset_name="knobs_default",
        overrides={**TWO_BY_TWO, **overrides},
    )
    assert isinstance(scenario, TextcraftSharedWorkspaceScenario)
    agents = scenario.get_agents("test", "self-hosted")
    sessions = {agent.agent_id: AgentSession(agent_id=agent.agent_id) for agent in agents}
    logger = RecordingLogger()
    runtime = SimulationRuntime(
        scenario=scenario,
        channels=scenario.get_channels(),
        event_logger=logger,  # type: ignore[arg-type]
        agent_sessions=sessions,
        agent_tool_allowlists={agent.agent_id: frozenset(agent.tool_names) for agent in agents},
        world_context=WorldContext(
            agent_sessions=sessions, event_logger=logger  # type: ignore[arg-type]
        ),
        agent_configs=agents,
        simulation_start_time=datetime.now(tz=UTC),
    )
    scenario.bind_runtime(runtime=runtime)
    await scenario.on_round_advanced(round_number=1)
    return Wired(scenario=scenario, runtime=runtime)


def output_of(command: str) -> str:
    """The item a ``craft N item using ...`` command makes."""
    return command.split()[2]


async def test_a_depot_wait_resumes_when_a_watched_item_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    first, second = wired.layer(index=0)
    await wired.call("crafter_2", "observe")
    waiting = wired.wait("crafter_2", wait_for="depot", items=[output_of(first)])
    await asyncio.sleep(0)
    await wired.call("crafter_1", "act", command=second)
    await asyncio.sleep(0)
    assert not waiting.done()
    await wired.call("crafter_1", "act", command=first)
    woke = json.loads(await asyncio.wait_for(waiting, timeout=5))
    assert woke["wake_reasons"] == ["released: a watched item increased"]
    assert output_of(first) in woke["workspace"]


async def test_a_depot_wait_resumes_at_once_on_an_increase_the_agent_has_not_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    first, _ = wired.layer(index=0)
    await wired.call("crafter_2", "observe")
    await wired.call("crafter_1", "act", command=first)
    woke = json.loads(
        await asyncio.wait_for(
            wired.wait("crafter_2", wait_for="depot", items=[output_of(first)]), timeout=5
        )
    )
    assert woke["wake_reasons"] == ["released: a watched item increased"]


async def test_items_only_go_with_a_depot_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    refused = await wired.call(
        "crafter_1", "read_notifications", ctx=FakeContext(), wait_for="any", items=["x"]
    )
    assert "items applies only to wait_for='depot'" in refused


async def test_frontier_briefing_lists_only_the_first_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={"recipe_reveal": "frontier"})
    briefing = wired.scenario.get_injection(round_number=1, agent_id="crafter_1")
    assert "UNLOCKED RECIPES (2 of 4" in briefing
    for command in wired.layer(index=0):
        assert command in briefing
    for command in wired.layer(index=1):
        assert command not in briefing


async def test_frontier_recipes_unlock_for_everyone_when_their_inputs_land(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={"recipe_reveal": "frontier"})
    first, second = wired.layer(index=0)
    later = [command for command in wired.layer(index=1) if output_of(first) in command.split()][0]
    refused = await wired.call("crafter_1", "act", command=later)
    assert refused.startswith("Invalid command.")
    await wired.call("crafter_2", "observe")
    waiting = wired.wait("crafter_2", wait_for="depot", items=[output_of(second)])
    await asyncio.sleep(0)
    await wired.call("crafter_1", "act", command=first)
    woke = json.loads(await asyncio.wait_for(waiting, timeout=5))
    assert woke["wake_reasons"] == ["released: a recipe unlocked"]
    assert later in woke["workspace"]
    crafted = await wired.call("crafter_2", "act", command=later)
    assert crafted.startswith("Crafted")


async def test_full_reveal_never_announces_unlocks(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    first, _ = wired.layer(index=0)
    seen = await wired.call("crafter_1", "act", command=first)
    assert "Recipes unlocked" not in seen


async def test_nonzero_view_leaves_out_depleted_items(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={"depot_view": "nonzero"})
    first, _ = wired.layer(index=0)
    seen = await wired.call("crafter_1", "act", command=first)
    snapshot = seen.split("\n")[1]
    assert "unlisted items are 0" in snapshot
    assert "=0" not in snapshot


def test_private_raw_items_belong_to_one_column() -> None:
    task = generate_task(
        seed=7,
        width=6,
        span=3,
        quantity_scale=3,
        resource_slack_fraction=0.2,
        max_fan_in=2,
        cross_edge_density=0.5,
        raw_material_count=2,
        max_raw_inputs=2,
        raw_ownership="private",
    )
    users: dict[str, set[str]] = {}
    for column, card in task.cards.items():
        for item in card.recipes[0].inputs:
            users.setdefault(item, set()).add(column)
    assert len(users) == 12
    assert all(len(columns) == 1 for columns in users.values())


async def test_the_depot_wait_is_in_the_recorded_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    definitions = {
        definition.name: definition for definition in list_tool_definitions(runtime=wired.runtime)
    }
    schema = definitions["read_notifications"].input_schema
    assert "depot" in schema["properties"]["wait_for"]["enum"]
    assert "items" in schema["properties"]
