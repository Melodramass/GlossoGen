"""The oracle-communication knobs: the team activity feed and the list-schedule plan."""

from glossogen.scenarios.textcraft_shared_workspace.oracle_plan import list_schedule
from glossogen.scenarios.textcraft_shared_workspace.state import DepotState
from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask, generate_task

SEATS = ["crafter_1", "crafter_2"]


def layered_task(width: int, span: int) -> WorkspaceTask:
    return generate_task(
        seed=7,
        width=width,
        span=span,
        quantity_scale=2,
        resource_slack_fraction=0.0,
        max_fan_in=2,
        cross_edge_density=0.3,
        raw_material_count=1,
        max_raw_inputs=1,
        raw_ownership="private",
    )


def feed_depot(task: WorkspaceTask, team_feed: bool) -> DepotState:
    return DepotState(
        task=task,
        seats=SEATS,
        uncraft_enabled=True,
        recipe_reveal="full",
        depot_view="full",
        team_feed=team_feed,
    )


def test_feed_names_teammate_crafts_and_not_own() -> None:
    task = layered_task(width=2, span=2)
    state = feed_depot(task=task, team_feed=True)
    _, first = task.witness[0]
    pending = state.start(agent_id="crafter_1", command=first).pending
    assert pending is not None
    teammate_view = state.observe(agent_id="crafter_2")
    assert f"crafter_1 started: {first}" in teammate_view
    assert "crafter_1: " in teammate_view
    assert "started" not in state.observe(agent_id="crafter_1")
    state.finish(pending=pending)
    assert f"crafter_1 finished: {first}" in state.observe(agent_id="crafter_2")


def test_no_feed_keeps_actors_hidden() -> None:
    task = layered_task(width=2, span=2)
    state = feed_depot(task=task, team_feed=False)
    _, first = task.witness[0]
    state.start(agent_id="crafter_1", command=first)
    view = state.observe(agent_id="crafter_2")
    assert "crafter_1" not in view


def test_plan_covers_every_craft_once_in_dependency_order() -> None:
    task = layered_task(width=6, span=4)
    seats = [f"crafter_{i}" for i in range(1, 4)]
    plan = list_schedule(task=task, seats=seats)
    planned = [command for crafts in plan.values() for command in crafts]
    assert sorted(planned) == sorted(command for _, command in task.witness)
    assert max(len(crafts) for crafts in plan.values()) == 8
