"""Certify a round's boards from the lines the viewers are given.

Certification never reads the generator's objects. It parses the rendered lines
back and checks what a team could work out from them. A round passes when:

- every line reads, no board holds two objects in one cell, and all boards are
  the same size;
- exactly one object is on every board, and it is the declared answer;
- comparing only part of an object never isolates the answer: the cells every
  board occupies, and the shape-and-color, shape-and-cell and color-and-cell
  pairs every board holds, each number at least two;
- the declared objects are exactly the objects on the boards, each held by
  exactly the boards declared for it;
- when every board is required, none can be left out: without any one board, at
  least two objects are on all the rest.

Certification reads the rendered lines because those are the only description of
a board a viewer receives.
"""

from collections.abc import Callable, Hashable, Sequence
from enum import Enum
from typing import NamedTuple

from glossogen.scenarios.spot_the_intersection.board_model import BoardObject
from glossogen.scenarios.spot_the_intersection.board_rendering import parse_board_line


class ObjectKind(str, Enum):
    """What the generator placed an object for."""

    ANSWER = "answer"
    # On every board but one.
    NEAR_MISS = "near_miss"
    # On the board missing a near-miss, in its cell, one attribute different.
    STAND_IN = "stand_in"
    # In a cell every board fills, with the shape or the color the same on all.
    CELL_TWIN = "cell_twin"
    # A shape and color every board holds, not in the same cell on all.
    LOOK_TWIN = "look_twin"
    # On more than one board and fewer than all.
    DECOY = "decoy"
    # On one board.
    FILLER = "filler"


class DeclaredObject(NamedTuple):
    """One distinct object the generator placed, its purpose, and the boards holding it.

    ``seats`` are board indices counted from 0, in the team's seat order.
    """

    kind: ObjectKind
    obj: BoardObject
    seats: frozenset[int]


class FailureReason(str, Enum):
    """Why a round's boards did not certify."""

    TOO_FEW_BOARDS = "too_few_boards"
    UNREADABLE_LINE = "unreadable_line"
    SHARED_CELL = "shared_cell"
    UNEQUAL_BOARDS = "unequal_boards"
    NO_COMMON_OBJECT = "no_common_object"
    SEVERAL_COMMON_OBJECTS = "several_common_objects"
    WRONG_ANSWER = "wrong_answer"
    PARTIAL_MATCH_SHORTCUT = "partial_match_shortcut"
    DECLARATION_MISMATCH = "declaration_mismatch"
    BOARD_NOT_NEEDED = "board_not_needed"


class CertificationFailure(NamedTuple):
    """One failed check, with the detail needed to see what broke."""

    reason: FailureReason
    detail: str


class PartialMatchCounts(NamedTuple):
    """How many values of each partial comparison every board holds."""

    cell: int
    look: int
    shape_and_cell: int
    color_and_cell: int


class BoardCertificate(NamedTuple):
    """What a certified round's boards were measured to be.

    ``candidates_without_seat[i]`` counts the objects on every board except
    board ``i``. ``dump_object_mentions`` is every board listed in full;
    ``sequential_filter_object_mentions`` is the first board listed and each
    later viewer listing what survives on its own board, in seat order.
    """

    answer: BoardObject
    candidates_without_seat: tuple[int, ...]
    partial_matches: PartialMatchCounts
    dump_object_mentions: int
    sequential_filter_object_mentions: int


class CertificationResult(NamedTuple):
    """A certificate when every check passed, otherwise the failures."""

    certificate: BoardCertificate | None
    failures: tuple[CertificationFailure, ...]


class _ParsedBoards(NamedTuple):
    boards: tuple[frozenset[BoardObject], ...]
    failures: tuple[CertificationFailure, ...]


class _PartialMatch(NamedTuple):
    name: str
    key: Callable[[BoardObject], Hashable]


def _cell_of(obj: BoardObject) -> Hashable:
    return obj.cell


def _look_of(obj: BoardObject) -> Hashable:
    return obj.look


def _shape_and_cell_of(obj: BoardObject) -> Hashable:
    return (obj.shape, obj.cell)


def _color_and_cell_of(obj: BoardObject) -> Hashable:
    return (obj.color, obj.cell)


_PARTIAL_MATCHES: tuple[_PartialMatch, ...] = (
    _PartialMatch(name="cell", key=_cell_of),
    _PartialMatch(name="look", key=_look_of),
    _PartialMatch(name="shape_and_cell", key=_shape_and_cell_of),
    _PartialMatch(name="color_and_cell", key=_color_and_cell_of),
)

# A partial comparison isolates the answer when only one value survives it.
_MIN_PARTIAL_MATCHES = 2


def certify_boards(
    board_lines: Sequence[Sequence[str]],
    grid_size: int,
    declared: Sequence[DeclaredObject],
    require_every_board: bool,
) -> CertificationResult:
    """Check one team's boards, read from ``board_lines``, against the declaration."""
    parsed = _parse_boards(board_lines=board_lines, grid_size=grid_size)
    if parsed.failures:
        return CertificationResult(certificate=None, failures=parsed.failures)
    boards = parsed.boards
    holders = _holders(boards=boards)
    failures: list[CertificationFailure] = []
    failures.extend(_board_size_failures(boards=boards))
    failures.extend(_answer_failures(holders=holders, seat_count=len(boards), declared=declared))
    counts = _partial_match_counts(boards=boards)
    failures.extend(_partial_match_failures(counts=counts))
    failures.extend(_declaration_failures(holders=holders, declared=declared))
    without = _candidates_without_each_seat(boards=boards)
    if require_every_board:
        failures.extend(_board_needed_failures(candidates_without_seat=without))
    if failures:
        return CertificationResult(certificate=None, failures=tuple(failures))
    return CertificationResult(
        certificate=BoardCertificate(
            answer=_declared_answers(declared=declared)[0],
            candidates_without_seat=without,
            partial_matches=counts,
            dump_object_mentions=sum(len(board) for board in boards),
            sequential_filter_object_mentions=_sequential_filter_mentions(boards=boards),
        ),
        failures=(),
    )


def _parse_boards(board_lines: Sequence[Sequence[str]], grid_size: int) -> _ParsedBoards:
    """Parse every line of every board, refusing unreadable lines and doubled cells."""
    if len(board_lines) < 2:
        failure = CertificationFailure(
            reason=FailureReason.TOO_FEW_BOARDS, detail=f"{len(board_lines)} board(s)"
        )
        return _ParsedBoards(boards=(), failures=(failure,))
    boards: list[frozenset[BoardObject]] = []
    failures: list[CertificationFailure] = []
    for seat, lines in enumerate(board_lines):
        objects: list[BoardObject] = []
        for line in lines:
            try:
                objects.append(parse_board_line(line=line, grid_size=grid_size))
            except ValueError as error:
                failures.append(
                    CertificationFailure(
                        reason=FailureReason.UNREADABLE_LINE, detail=f"board {seat}: {error}"
                    )
                )
        cells = [obj.cell for obj in objects]
        if len(set(cells)) != len(cells):
            failures.append(
                CertificationFailure(
                    reason=FailureReason.SHARED_CELL,
                    detail=f"board {seat} holds two objects in one cell",
                )
            )
        boards.append(frozenset(objects))
    return _ParsedBoards(boards=tuple(boards), failures=tuple(failures))


def _holders(boards: Sequence[frozenset[BoardObject]]) -> dict[BoardObject, frozenset[int]]:
    """Map every object to the boards holding it."""
    seats_by_object: dict[BoardObject, set[int]] = {}
    for seat, board in enumerate(boards):
        for obj in board:
            seats_by_object.setdefault(obj, set()).add(seat)
    return {obj: frozenset(seats) for obj, seats in seats_by_object.items()}


def _board_size_failures(boards: Sequence[frozenset[BoardObject]]) -> list[CertificationFailure]:
    """Every board holds the same number of objects."""
    sizes = sorted({len(board) for board in boards})
    if len(sizes) == 1:
        return []
    return [CertificationFailure(reason=FailureReason.UNEQUAL_BOARDS, detail=f"sizes {sizes}")]


def _declared_answers(declared: Sequence[DeclaredObject]) -> list[BoardObject]:
    """The objects declared as the answer."""
    return [entry.obj for entry in declared if entry.kind is ObjectKind.ANSWER]


def _answer_failures(
    holders: dict[BoardObject, frozenset[int]], seat_count: int, declared: Sequence[DeclaredObject]
) -> list[CertificationFailure]:
    """Exactly one object is on every board, and it is the one declared."""
    common = sorted(obj for obj, seats in holders.items() if len(seats) == seat_count)
    if not common:
        return [CertificationFailure(reason=FailureReason.NO_COMMON_OBJECT, detail="")]
    if len(common) > 1:
        return [
            CertificationFailure(
                reason=FailureReason.SEVERAL_COMMON_OBJECTS, detail=f"on every board: {common}"
            )
        ]
    answers = _declared_answers(declared=declared)
    if answers != common:
        return [
            CertificationFailure(
                reason=FailureReason.WRONG_ANSWER,
                detail=f"on every board: {common[0]}, declared: {answers}",
            )
        ]
    return []


def _shared_values(
    boards: Sequence[frozenset[BoardObject]], key: Callable[[BoardObject], Hashable]
) -> set[Hashable]:
    """The values of ``key`` that every board holds."""
    shared = {key(obj) for obj in boards[0]}
    for board in boards[1:]:
        shared &= {key(obj) for obj in board}
    return shared


def _partial_match_counts(boards: Sequence[frozenset[BoardObject]]) -> PartialMatchCounts:
    """Count the values every board shares under each partial comparison."""
    counts = {
        match.name: len(_shared_values(boards=boards, key=match.key)) for match in _PARTIAL_MATCHES
    }
    return PartialMatchCounts(**counts)


def _partial_match_failures(counts: PartialMatchCounts) -> list[CertificationFailure]:
    """No partial comparison narrows the boards to a single value."""
    return [
        CertificationFailure(
            reason=FailureReason.PARTIAL_MATCH_SHORTCUT, detail=f"{name} shared by all: {count}"
        )
        for name, count in counts._asdict().items()
        if count < _MIN_PARTIAL_MATCHES
    ]


def _declaration_failures(
    holders: dict[BoardObject, frozenset[int]], declared: Sequence[DeclaredObject]
) -> list[CertificationFailure]:
    """The declaration names every object once, each with exactly its holders."""
    failures: list[CertificationFailure] = []
    declared_objects = [entry.obj for entry in declared]
    if len(set(declared_objects)) != len(declared_objects):
        failures.append(
            CertificationFailure(
                reason=FailureReason.DECLARATION_MISMATCH, detail="an object is declared twice"
            )
        )
    for entry in declared:
        actual = holders.get(entry.obj, frozenset())
        if actual != entry.seats:
            failures.append(
                CertificationFailure(
                    reason=FailureReason.DECLARATION_MISMATCH,
                    detail=(
                        f"{entry.kind.value} {entry.obj} declared on {sorted(entry.seats)}, "
                        f"found on {sorted(actual)}"
                    ),
                )
            )
    undeclared = set(holders) - set(declared_objects)
    if undeclared:
        failures.append(
            CertificationFailure(
                reason=FailureReason.DECLARATION_MISMATCH,
                detail=f"undeclared objects: {sorted(undeclared)}",
            )
        )
    return failures


def _candidates_without_each_seat(boards: Sequence[frozenset[BoardObject]]) -> tuple[int, ...]:
    """For each board, how many objects are on every other board."""
    counts: list[int] = []
    for seat in range(len(boards)):
        others = [board for index, board in enumerate(boards) if index != seat]
        remaining = set(others[0])
        for board in others[1:]:
            remaining &= board
        counts.append(len(remaining))
    return tuple(counts)


def _board_needed_failures(candidates_without_seat: tuple[int, ...]) -> list[CertificationFailure]:
    """Leaving any one board out leaves the answer ambiguous."""
    return [
        CertificationFailure(
            reason=FailureReason.BOARD_NOT_NEEDED,
            detail=f"without board {seat}, {count} candidate(s) remain",
        )
        for seat, count in enumerate(candidates_without_seat)
        if count < 2
    ]


def _sequential_filter_mentions(boards: Sequence[frozenset[BoardObject]]) -> int:
    """Objects named when each viewer in turn lists what survives on its board."""
    survivors = set(boards[0])
    mentions = len(survivors)
    for board in boards[1:]:
        survivors &= board
        mentions += len(survivors)
    return mentions
