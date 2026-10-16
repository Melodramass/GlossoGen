"""Seeded generation of one round's boards, accepted only once certified.

Every viewer seat on a team gets a board, and both teams get the same boards
seat for seat. A round is planted in this order:

1. the answer, on every board;
2. with ``near_misses`` on and three or more seats, one near-miss per seat: an
   object on every board except that seat's, whose board holds a stand-in in
   the same cell differing in exactly one attribute;
3. two cell twins: a cell every board fills, one with the shape the same on
   all boards and one with the color the same, never the whole object;
4. two look twins: each a shape and color every board holds, not all in one
   cell, drawn from every shape and color including the answer's, so the
   answer's look is as common on a board as any other object's;
5. ``decoy_count`` decoys, each on more than one board and fewer than all;
6. fillers, each on one board, until every board holds the same number.

No placement repeats an object another board already holds in that cell, so
every object is held by exactly the boards it was planted on. The boards are
then rendered, shuffled, and handed to :func:`certify_boards`; a round that
fails is redrawn from the same random stream, and a round that never passes
raises :class:`BoardGenerationError` rather than being played.

Each round draws from its own stream, keyed by the seed and the round number,
so a round's boards do not depend on how many rounds the run has. Line order
comes from a second stream, so where the answer is listed is independent of
what the boards hold.
"""

import random
from collections.abc import Sequence
from typing import NamedTuple

from glossogen.scenarios.spot_the_intersection.board_certification import (
    BoardCertificate,
    CertificationFailure,
    DeclaredObject,
    ObjectKind,
    certify_boards,
)
from glossogen.scenarios.spot_the_intersection.board_model import (
    COLORS,
    SHAPES,
    BoardObject,
    all_cells,
)
from glossogen.scenarios.spot_the_intersection.board_rendering import render_board_line

MAX_GENERATION_ATTEMPTS = 200

# Objects every board holds before decoys and fillers: the answer, two cell
# twins and two look twins, plus, with near-misses, the other seats'
# near-misses and the board's own stand-in.
_PLANTED_WITHOUT_NEAR_MISSES = 5


class BoardGenerationError(RuntimeError):
    """Raised when a round produces no certified boards within the attempt limit."""


class _NoFreeCell(Exception):
    """An attempt ran out of cells to place an object in; the attempt is redrawn."""


class BoardSettings(NamedTuple):
    """The knobs that shape a round's boards."""

    team_size: int
    grid_size: int
    near_misses: bool
    decoy_count_values: Sequence[int]
    decoy_count_weights: Sequence[int]
    filler_count_values: Sequence[int]
    filler_count_weights: Sequence[int]


class RoundBoards(NamedTuple):
    """One round's certified boards, as shown and as declared.

    ``boards[i]`` and ``board_lines[i]`` are seat ``i``'s board in the order its
    viewer reads it. ``declared`` names every distinct object with its purpose
    and holders, and ``attempts`` counts the draws it took to certify.
    """

    round_number: int
    grid_size: int
    team_size: int
    board_size: int
    decoy_count: int
    filler_count: int
    boards: tuple[tuple[BoardObject, ...], ...]
    board_lines: tuple[tuple[str, ...], ...]
    declared: tuple[DeclaredObject, ...]
    certificate: BoardCertificate
    attempts: int


class _Plan(NamedTuple):
    boards: list[dict[tuple[int, int], BoardObject]]
    declared: list[DeclaredObject]


def planted_per_board(team_size: int, near_misses: bool) -> int:
    """How many objects every board holds before decoys and fillers."""
    if near_misses and team_size >= 3:
        return _PLANTED_WITHOUT_NEAR_MISSES + team_size
    return _PLANTED_WITHOUT_NEAR_MISSES


def board_size_for(settings: BoardSettings, decoy_count: int, filler_count: int) -> int:
    """The number of objects on every board for one round's draws."""
    planted = planted_per_board(team_size=settings.team_size, near_misses=settings.near_misses)
    return planted + decoy_count + filler_count


def generate_rounds(seed: int, round_count: int, settings: BoardSettings) -> list[RoundBoards]:
    """Generate and certify the boards of rounds ``1..round_count``."""
    return [
        generate_round(seed=seed, round_number=round_number, settings=settings)
        for round_number in range(1, round_count + 1)
    ]


def generate_round(seed: int, round_number: int, settings: BoardSettings) -> RoundBoards:
    """Draw one round's boards until they certify; raise if they never do."""
    rng = random.Random(f"spot_the_intersection:{seed}:{round_number}")
    order_rng = random.Random(f"spot_the_intersection:{seed}:{round_number}:order")
    decoy_count = rng.choices(
        population=list(settings.decoy_count_values), weights=list(settings.decoy_count_weights)
    )[0]
    filler_count = rng.choices(
        population=list(settings.filler_count_values), weights=list(settings.filler_count_weights)
    )[0]
    board_size = board_size_for(
        settings=settings, decoy_count=decoy_count, filler_count=filler_count
    )
    last_failures: tuple[CertificationFailure, ...] = ()
    last_shortfall = ""
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            plan = _plan_boards(
                rng=rng, settings=settings, decoy_count=decoy_count, board_size=board_size
            )
        except _NoFreeCell as shortfall:
            last_shortfall = str(shortfall)
            continue
        boards = _ordered_boards(plan=plan, order_rng=order_rng)
        board_lines = tuple(tuple(render_board_line(obj=obj) for obj in board) for board in boards)
        result = certify_boards(
            board_lines=board_lines,
            grid_size=settings.grid_size,
            declared=plan.declared,
            require_every_board=settings.near_misses,
        )
        if result.certificate is not None:
            return RoundBoards(
                round_number=round_number,
                grid_size=settings.grid_size,
                team_size=settings.team_size,
                board_size=board_size,
                decoy_count=decoy_count,
                filler_count=filler_count,
                boards=boards,
                board_lines=board_lines,
                declared=tuple(plan.declared),
                certificate=result.certificate,
                attempts=attempt,
            )
        last_failures = result.failures
    raise BoardGenerationError(
        f"round {round_number}: no certified boards in {MAX_GENERATION_ATTEMPTS} attempts "
        f"(team_size={settings.team_size}, grid_size={settings.grid_size}, "
        f"board_size={board_size}); last failures: {list(last_failures)}; "
        f"last placement shortfall: {last_shortfall!r}"
    )


def _ordered_boards(plan: _Plan, order_rng: random.Random) -> tuple[tuple[BoardObject, ...], ...]:
    """Put each board's objects in a random order drawn apart from their content."""
    ordered: list[tuple[BoardObject, ...]] = []
    for board in plan.boards:
        objects = sorted(board.values())
        order_rng.shuffle(objects)
        ordered.append(tuple(objects))
    return tuple(ordered)


def _plan_boards(
    rng: random.Random, settings: BoardSettings, decoy_count: int, board_size: int
) -> _Plan:
    """Place every object of one attempt on the boards."""
    plan = _Plan(boards=[{} for _ in range(settings.team_size)], declared=[])
    all_seats = frozenset(range(settings.team_size))
    _place(
        plan=plan,
        kind=ObjectKind.ANSWER,
        obj=_random_object(
            rng=rng, cell=_choose_cell(rng=rng, cells=_cells_free_on(plan=plan, settings=settings))
        ),
        seats=all_seats,
    )
    if settings.near_misses and settings.team_size >= 3:
        _plant_near_misses(rng=rng, plan=plan, settings=settings)
    _plant_cell_twin(rng=rng, plan=plan, settings=settings, shared_attribute="shape")
    _plant_cell_twin(rng=rng, plan=plan, settings=settings, shared_attribute="color")
    _plant_look_twin(rng=rng, plan=plan, settings=settings)
    _plant_look_twin(rng=rng, plan=plan, settings=settings)
    if settings.team_size >= 3:
        for _ in range(decoy_count):
            _plant_decoy(rng=rng, plan=plan, settings=settings)
    for seat in range(settings.team_size):
        while len(plan.boards[seat]) < board_size:
            _plant_filler(rng=rng, plan=plan, settings=settings, seat=seat)
    return plan


def _place(plan: _Plan, kind: ObjectKind, obj: BoardObject, seats: frozenset[int]) -> BoardObject:
    """Put ``obj`` on the ``seats`` boards and declare it."""
    for seat in seats:
        plan.boards[seat][obj.cell] = obj
    plan.declared.append(DeclaredObject(kind=kind, obj=obj, seats=seats))
    return obj


def _random_object(rng: random.Random, cell: tuple[int, int]) -> BoardObject:
    """A uniformly random shape and color in ``cell``."""
    return BoardObject(
        shape=rng.choice(SHAPES), color=rng.choice(COLORS), column=cell[0], row=cell[1]
    )


def _cells_free_on(plan: _Plan, settings: BoardSettings) -> list[tuple[int, int]]:
    """Cells empty on every board."""
    return [
        cell
        for cell in all_cells(grid_size=settings.grid_size)
        if all(cell not in board for board in plan.boards)
    ]


def _choose_cell(rng: random.Random, cells: Sequence[tuple[int, int]]) -> tuple[int, int]:
    """A random cell of ``cells``; an empty choice redraws the attempt."""
    if not cells:
        raise _NoFreeCell("no free cell left")
    return rng.choice(cells)


def _objects_in_cell(plan: _Plan, cell: tuple[int, int]) -> set[BoardObject]:
    """Every object any board holds in ``cell``."""
    return {board[cell] for board in plan.boards if cell in board}


def _plant_near_misses(rng: random.Random, plan: _Plan, settings: BoardSettings) -> None:
    """One near-miss per seat, with that seat's stand-in in the same cell.

    Any two near-misses share a board once there are three seats, so their
    cells are distinct. Stand-ins alternate between changing the color and
    changing the shape, so both cell-based partial comparisons see a near-miss
    cell that is not the answer's.
    """
    free = _cells_free_on(plan=plan, settings=settings)
    if len(free) < settings.team_size:
        raise _NoFreeCell(f"{len(free)} free cells for {settings.team_size} near-misses")
    cells = rng.sample(free, settings.team_size)
    all_seats = frozenset(range(settings.team_size))
    for seat, cell in enumerate(cells):
        near_miss = _place(
            plan=plan,
            kind=ObjectKind.NEAR_MISS,
            obj=_random_object(rng=rng, cell=cell),
            seats=all_seats - {seat},
        )
        if seat % 2 == 0:
            stand_in = near_miss._replace(
                color=rng.choice([color for color in COLORS if color != near_miss.color])
            )
        else:
            stand_in = near_miss._replace(
                shape=rng.choice([shape for shape in SHAPES if shape != near_miss.shape])
            )
        _place(plan=plan, kind=ObjectKind.STAND_IN, obj=stand_in, seats=frozenset({seat}))


def _plant_cell_twin(
    rng: random.Random, plan: _Plan, settings: BoardSettings, shared_attribute: str
) -> None:
    """Fill one cell on every board with ``shared_attribute`` the same and the other not."""
    cell = _choose_cell(rng=rng, cells=_cells_free_on(plan=plan, settings=settings))
    if shared_attribute == "shape":
        shape = rng.choice(SHAPES)
        varying = _not_all_equal(rng=rng, values=COLORS, count=settings.team_size)
        objects = [
            BoardObject(shape=shape, color=color, column=cell[0], row=cell[1]) for color in varying
        ]
    else:
        color = rng.choice(COLORS)
        varying = _not_all_equal(rng=rng, values=SHAPES, count=settings.team_size)
        objects = [
            BoardObject(shape=shape, color=color, column=cell[0], row=cell[1]) for shape in varying
        ]
    _place_grouped(plan=plan, kind=ObjectKind.CELL_TWIN, objects=objects)


def _plant_look_twin(rng: random.Random, plan: _Plan, settings: BoardSettings) -> None:
    """Give every board one random shape and color, not all in one cell.

    The look may be the answer's, so the answer's look is as common on a board as
    any other object's.
    """
    shape = rng.choice(SHAPES)
    color = rng.choice(COLORS)
    free = _cells_free_on(plan=plan, settings=settings)
    if len(free) < 2:
        raise _NoFreeCell(f"{len(free)} free cell(s) for the look twin")
    cells = [rng.choice(free) for _ in range(settings.team_size)]
    while len(set(cells)) < 2:
        cells = [rng.choice(free) for _ in range(settings.team_size)]
    objects = [BoardObject(shape=shape, color=color, column=cell[0], row=cell[1]) for cell in cells]
    _place_grouped(plan=plan, kind=ObjectKind.LOOK_TWIN, objects=objects)


def _plant_decoy(rng: random.Random, plan: _Plan, settings: BoardSettings) -> None:
    """Put one object on more than one board and fewer than all."""
    holder_count = rng.randint(2, settings.team_size - 1)
    seats = frozenset(rng.sample(range(settings.team_size), holder_count))
    free = [
        cell
        for cell in all_cells(grid_size=settings.grid_size)
        if all(cell not in plan.boards[seat] for seat in seats)
    ]
    cell = _choose_cell(rng=rng, cells=free)
    obj = _object_new_to_cell(rng=rng, plan=plan, cell=cell)
    _place(plan=plan, kind=ObjectKind.DECOY, obj=obj, seats=seats)


def _plant_filler(rng: random.Random, plan: _Plan, settings: BoardSettings, seat: int) -> None:
    """Put one object on ``seat``'s board alone."""
    free = [
        cell for cell in all_cells(grid_size=settings.grid_size) if cell not in plan.boards[seat]
    ]
    cell = _choose_cell(rng=rng, cells=free)
    obj = _object_new_to_cell(rng=rng, plan=plan, cell=cell)
    _place(plan=plan, kind=ObjectKind.FILLER, obj=obj, seats=frozenset({seat}))


def _object_new_to_cell(rng: random.Random, plan: _Plan, cell: tuple[int, int]) -> BoardObject:
    """A random object for ``cell`` that no board already holds there.

    Repeating one would silently add a holder to an object already declared.
    """
    taken = _objects_in_cell(plan=plan, cell=cell)
    candidates = [
        BoardObject(shape=shape, color=color, column=cell[0], row=cell[1])
        for shape in SHAPES
        for color in COLORS
    ]
    return rng.choice([obj for obj in candidates if obj not in taken])


def _not_all_equal(rng: random.Random, values: Sequence[str], count: int) -> list[str]:
    """``count`` random draws from ``values`` with at least two different ones."""
    drawn = [rng.choice(values) for _ in range(count)]
    while len(set(drawn)) < 2:
        drawn = [rng.choice(values) for _ in range(count)]
    return drawn


def _place_grouped(plan: _Plan, kind: ObjectKind, objects: Sequence[BoardObject]) -> None:
    """Place ``objects[seat]`` on each seat's board, declaring each distinct object once."""
    seats_by_object: dict[BoardObject, set[int]] = {}
    for seat, obj in enumerate(objects):
        seats_by_object.setdefault(obj, set()).add(seat)
    for obj, seats in seats_by_object.items():
        _place(plan=plan, kind=kind, obj=obj, seats=frozenset(seats))
