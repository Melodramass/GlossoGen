"""The certifier refuses every way a round can be broken.

A checker nobody has seen fail proves nothing: spot_the_difference had a
uniqueness check, and it passed a round whose planted differences were not all
visible, because it checked coordinates the viewers never saw. Each test here
takes a certified round, breaks one property on purpose, and requires the
certifier to name that property.
"""

from collections.abc import Sequence
from typing import NamedTuple

from glossogen.scenarios.spot_the_intersection.board_certification import (
    DeclaredObject,
    FailureReason,
    ObjectKind,
    certify_boards,
)
from glossogen.scenarios.spot_the_intersection.board_generation import (
    BoardSettings,
    RoundBoards,
    generate_round,
)
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject
from glossogen.scenarios.spot_the_intersection.board_rendering import render_board_line

TEAM_SIZE = 4
GRID_SIZE = 6


class Mutation(NamedTuple):
    """A round's lines and declaration after a deliberate break."""

    lines: list[list[str]]
    declared: list[DeclaredObject]


def certified_round() -> RoundBoards:
    """A round from the real generator, every property intact."""
    return generate_round(
        seed=42,
        round_number=1,
        settings=BoardSettings(
            team_size=TEAM_SIZE,
            grid_size=GRID_SIZE,
            near_misses=True,
            decoy_count_values=[2],
            decoy_count_weights=[1],
            filler_count_values=[3],
            filler_count_weights=[1],
        ),
    )


def failure_reasons(
    board_lines: Sequence[Sequence[str]],
    declared: Sequence[DeclaredObject],
    require_every_board: bool,
) -> set[FailureReason]:
    """Certify and return only which checks failed."""
    result = certify_boards(
        board_lines=board_lines,
        grid_size=GRID_SIZE,
        declared=declared,
        require_every_board=require_every_board,
    )
    if not result.failures:
        assert result.certificate is not None, "no failures but no certificate either"
    return {failure.reason for failure in result.failures}


def editable_lines(round_boards: RoundBoards) -> list[list[str]]:
    """A mutable copy of every board's lines."""
    return [list(lines) for lines in round_boards.board_lines]


def swap_line(lines: list[list[str]], seat: int, old: BoardObject, new: BoardObject) -> None:
    """Replace ``old`` with ``new`` on one board, in place."""
    board = lines[seat]
    board[board.index(render_board_line(obj=old))] = render_board_line(obj=new)


def first_of(round_boards: RoundBoards, kind: ObjectKind) -> DeclaredObject:
    """The first declared object of ``kind``."""
    return next(entry for entry in round_boards.declared if entry.kind is kind)


def stand_in_for(round_boards: RoundBoards, near_miss: DeclaredObject) -> DeclaredObject:
    """The stand-in sharing ``near_miss``'s cell on the one board lacking it."""
    return next(
        entry
        for entry in round_boards.declared
        if entry.kind is ObjectKind.STAND_IN and entry.obj.cell == near_miss.obj.cell
    )


def redeclared(
    declared: Sequence[DeclaredObject],
    remove: Sequence[BoardObject],
    add: Sequence[DeclaredObject],
) -> list[DeclaredObject]:
    """The declaration with ``remove`` taken out and ``add`` appended."""
    kept = [entry for entry in declared if entry.obj not in remove]
    return kept + list(add)


def a_different_object_in(obj: BoardObject, avoid: Sequence[BoardObject]) -> BoardObject:
    """An object in ``obj``'s cell that is none of ``avoid``."""
    for color in ("red", "blue", "green", "yellow"):
        candidate = obj._replace(color=color)
        if candidate != obj and candidate not in avoid:
            return candidate
    raise AssertionError("no different object available")


def test_the_round_the_generator_produced_certifies() -> None:
    round_boards = certified_round()

    reasons = failure_reasons(
        board_lines=round_boards.board_lines,
        declared=round_boards.declared,
        require_every_board=True,
    )

    assert reasons == set()


def test_a_near_miss_copied_onto_the_board_lacking_it_is_a_second_answer() -> None:
    """The failure the user named first: two objects on every board."""
    round_boards = certified_round()
    near_miss = first_of(round_boards=round_boards, kind=ObjectKind.NEAR_MISS)
    stand_in = stand_in_for(round_boards=round_boards, near_miss=near_miss)
    (lacking_seat,) = stand_in.seats
    lines = editable_lines(round_boards=round_boards)
    swap_line(lines=lines, seat=lacking_seat, old=stand_in.obj, new=near_miss.obj)
    honest = redeclared(
        declared=round_boards.declared,
        remove=[near_miss.obj, stand_in.obj],
        add=[
            DeclaredObject(
                kind=ObjectKind.NEAR_MISS, obj=near_miss.obj, seats=frozenset(range(TEAM_SIZE))
            )
        ],
    )

    reasons = failure_reasons(board_lines=lines, declared=honest, require_every_board=True)

    assert FailureReason.SEVERAL_COMMON_OBJECTS in reasons


def test_the_same_second_answer_left_off_the_declaration_is_also_a_mismatch() -> None:
    round_boards = certified_round()
    near_miss = first_of(round_boards=round_boards, kind=ObjectKind.NEAR_MISS)
    stand_in = stand_in_for(round_boards=round_boards, near_miss=near_miss)
    (lacking_seat,) = stand_in.seats
    lines = editable_lines(round_boards=round_boards)
    swap_line(lines=lines, seat=lacking_seat, old=stand_in.obj, new=near_miss.obj)

    reasons = failure_reasons(
        board_lines=lines, declared=round_boards.declared, require_every_board=True
    )

    assert {FailureReason.SEVERAL_COMMON_OBJECTS, FailureReason.DECLARATION_MISMATCH} <= reasons


def test_an_answer_missing_from_one_board_leaves_no_common_object() -> None:
    round_boards = certified_round()
    answer = round_boards.certificate.answer
    lines = editable_lines(round_boards=round_boards)
    swap_line(
        lines=lines,
        seat=0,
        old=answer,
        new=a_different_object_in(obj=answer, avoid=[answer]),
    )

    reasons = failure_reasons(
        board_lines=lines, declared=round_boards.declared, require_every_board=True
    )

    assert FailureReason.NO_COMMON_OBJECT in reasons


def make_board_redundant(round_boards: RoundBoards, seat: int) -> Mutation:
    """Take one holder from every object that only ``seat``'s board rules out.

    Those are the objects on every board but ``seat``'s: the near-miss planted
    for that seat, and any cell twin that happens to have the same holders.
    Each loses one holder to a fresh filler, so the other boards alone narrow
    to the answer.
    """
    lines = editable_lines(round_boards=round_boards)
    declared = list(round_boards.declared)
    others = frozenset(range(TEAM_SIZE)) - {seat}
    taken = [entry.obj for entry in round_boards.declared]
    for entry in round_boards.declared:
        if entry.seats != others:
            continue
        holder = min(entry.seats)
        replacement = a_different_object_in(obj=entry.obj, avoid=taken)
        taken.append(replacement)
        swap_line(lines=lines, seat=holder, old=entry.obj, new=replacement)
        declared = redeclared(
            declared=declared,
            remove=[entry.obj],
            add=[
                entry._replace(seats=entry.seats - {holder}),
                DeclaredObject(kind=ObjectKind.FILLER, obj=replacement, seats=frozenset({holder})),
            ],
        )
    return Mutation(lines=lines, declared=declared)


def test_a_board_that_rules_nothing_out_is_not_needed() -> None:
    """Without anything only it can rule out, one viewer can stay silent."""
    round_boards = certified_round()
    mutation = make_board_redundant(round_boards=round_boards, seat=0)

    result = certify_boards(
        board_lines=mutation.lines,
        grid_size=GRID_SIZE,
        declared=mutation.declared,
        require_every_board=True,
    )

    needed = [f for f in result.failures if f.reason is FailureReason.BOARD_NOT_NEEDED]
    assert [failure.detail.split(",")[0] for failure in needed] == ["without board 0"]


def test_a_redundant_board_is_allowed_when_not_every_board_is_required() -> None:
    round_boards = certified_round()
    mutation = make_board_redundant(round_boards=round_boards, seat=0)

    reasons = failure_reasons(
        board_lines=mutation.lines, declared=mutation.declared, require_every_board=False
    )

    assert FailureReason.BOARD_NOT_NEEDED not in reasons


def test_a_declared_holder_that_does_not_hold_the_object_is_a_mismatch() -> None:
    round_boards = certified_round()
    filler = first_of(round_boards=round_boards, kind=ObjectKind.FILLER)
    (seat,) = filler.seats
    wrong = redeclared(
        declared=round_boards.declared,
        remove=[filler.obj],
        add=[filler._replace(seats=frozenset({(seat + 1) % TEAM_SIZE}))],
    )

    reasons = failure_reasons(
        board_lines=round_boards.board_lines, declared=wrong, require_every_board=True
    )

    assert reasons == {FailureReason.DECLARATION_MISMATCH}


def test_declaring_a_decoy_as_the_answer_is_caught() -> None:
    round_boards = certified_round()
    answer = first_of(round_boards=round_boards, kind=ObjectKind.ANSWER)
    decoy = first_of(round_boards=round_boards, kind=ObjectKind.DECOY)
    swapped = redeclared(
        declared=round_boards.declared,
        remove=[answer.obj, decoy.obj],
        add=[
            answer._replace(kind=ObjectKind.DECOY),
            decoy._replace(kind=ObjectKind.ANSWER),
        ],
    )

    reasons = failure_reasons(
        board_lines=round_boards.board_lines, declared=swapped, require_every_board=True
    )

    assert reasons == {FailureReason.WRONG_ANSWER}


def test_a_line_no_viewer_could_read_is_caught() -> None:
    round_boards = certified_round()
    lines = editable_lines(round_boards=round_boards)
    lines[1][0] = lines[1][0].capitalize()

    reasons = failure_reasons(
        board_lines=lines, declared=round_boards.declared, require_every_board=True
    )

    assert reasons == {FailureReason.UNREADABLE_LINE}


def test_two_objects_in_one_cell_are_caught() -> None:
    round_boards = certified_round()
    lines = editable_lines(round_boards=round_boards)
    answer = round_boards.certificate.answer
    lines[2].append(render_board_line(obj=a_different_object_in(obj=answer, avoid=[answer])))

    reasons = failure_reasons(
        board_lines=lines, declared=round_boards.declared, require_every_board=True
    )

    assert FailureReason.SHARED_CELL in reasons


def test_boards_of_different_sizes_are_caught() -> None:
    round_boards = certified_round()
    filler = first_of(round_boards=round_boards, kind=ObjectKind.FILLER)
    (seat,) = filler.seats
    lines = editable_lines(round_boards=round_boards)
    lines[seat].remove(render_board_line(obj=filler.obj))
    honest = redeclared(declared=round_boards.declared, remove=[filler.obj], add=[])

    reasons = failure_reasons(board_lines=lines, declared=honest, require_every_board=True)

    assert reasons == {FailureReason.UNEQUAL_BOARDS}


def test_boards_sharing_only_the_answer_cell_give_a_cell_shortcut() -> None:
    """Comparing cells alone would find the answer without naming a single color."""
    answer = BoardObject(shape="star", color="red", column=0, row=0)
    left = BoardObject(shape="square", color="blue", column=1, row=0)
    right = BoardObject(shape="square", color="blue", column=2, row=0)
    declared = [
        DeclaredObject(kind=ObjectKind.ANSWER, obj=answer, seats=frozenset({0, 1})),
        DeclaredObject(kind=ObjectKind.FILLER, obj=left, seats=frozenset({0})),
        DeclaredObject(kind=ObjectKind.FILLER, obj=right, seats=frozenset({1})),
    ]
    lines = [
        [render_board_line(obj=answer), render_board_line(obj=left)],
        [render_board_line(obj=answer), render_board_line(obj=right)],
    ]

    result = certify_boards(
        board_lines=lines, grid_size=GRID_SIZE, declared=declared, require_every_board=True
    )

    shortcuts = {
        failure.detail.split(" ")[0]
        for failure in result.failures
        if failure.reason is FailureReason.PARTIAL_MATCH_SHORTCUT
    }
    assert shortcuts == {"cell", "shape_and_cell", "color_and_cell"}


def test_a_single_board_is_refused() -> None:
    round_boards = certified_round()

    reasons = failure_reasons(
        board_lines=round_boards.board_lines[:1],
        declared=round_boards.declared,
        require_every_board=True,
    )

    assert reasons == {FailureReason.TOO_FEW_BOARDS}
