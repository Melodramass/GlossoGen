"""Oracle communication: the plan a perfect coordinator would hand each crafter.

Every witness craft takes one slot; a craft is ready once the crafts making its
inputs are done. Each slot, the free crafters take the ready crafts with the
longest remaining chain first (highest-level-first list scheduling), which
reaches the 3.0x / 9.0x ceilings of the 12 x 6 scaling bank.
"""

from glossogen.scenarios.textcraft_shared_workspace.tasks import WorkspaceTask


def list_schedule(task: WorkspaceTask, seats: list[str]) -> dict[str, list[str]]:
    """Each seat's crafting commands in the order it should run them."""
    recipes = {r.command: r for card in task.cards.values() for r in card.recipes}
    crafts = [command for _, command in task.witness]
    producer = {recipes[c].output: c for c in crafts}
    parents = {c: [producer[i] for i in recipes[c].inputs if i in producer] for c in crafts}
    children: dict[str, list[str]] = {c: [] for c in crafts}
    for c, ps in parents.items():
        for p in ps:
            children[p].append(c)
    level: dict[str, int] = {}
    for c in reversed(crafts):  # the witness is in dependency order
        level[c] = 1 + max((level[k] for k in children[c]), default=0)
    done: set[str] = set()
    plan: dict[str, list[str]] = {s: [] for s in seats}
    while len(done) < len(crafts):
        ready = sorted(
            (c for c in crafts if c not in done and all(p in done for p in parents[c])),
            key=lambda c: (-level[c], crafts.index(c)),
        )[: len(seats)]
        for seat, c in zip(seats, ready, strict=False):
            plan[seat].append(c)
        done.update(ready)
    return plan

