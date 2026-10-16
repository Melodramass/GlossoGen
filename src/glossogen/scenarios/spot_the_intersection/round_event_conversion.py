"""Convert a round's certified boards to the event that records them, and back.

``round_started_event`` writes the boards, every declared object and the
certificate into the event log. ``declared_from_event`` reads the declaration
back out, so a recorded run can be certified again from its own log.
"""

from glossogen.scenarios.spot_the_intersection.board_certification import (
    DeclaredObject,
    ObjectKind,
)
from glossogen.scenarios.spot_the_intersection.board_generation import RoundBoards
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject, cell_label
from glossogen.scenarios.spot_the_intersection.board_rendering import (
    parse_cell_label,
    render_board_line,
)
from glossogen.scenarios.spot_the_intersection.events import (
    IntersectionCertificateRecord,
    IntersectionObjectRecord,
    SpotTheIntersectionRoundStarted,
)


def _object_record(declared: DeclaredObject) -> IntersectionObjectRecord:
    """One declared object, with seats numbered from 1."""
    obj = declared.obj
    return IntersectionObjectRecord(
        kind=declared.kind.value,
        shape=obj.shape,
        color=obj.color,
        cell=cell_label(column=obj.column, row=obj.row),
        seat_numbers=sorted(seat + 1 for seat in declared.seats),
    )


def round_started_event(
    round_boards: RoundBoards, round_time_budget_seconds: int
) -> SpotTheIntersectionRoundStarted:
    """The event recording ``round_boards`` as the viewers will read them."""
    certificate = round_boards.certificate
    partial = certificate.partial_matches
    return SpotTheIntersectionRoundStarted(
        round_number=round_boards.round_number,
        team_size=round_boards.team_size,
        grid_size=round_boards.grid_size,
        board_size=round_boards.board_size,
        decoy_count=round_boards.decoy_count,
        filler_count=round_boards.filler_count,
        round_time_budget_seconds=round_time_budget_seconds,
        answer_line=render_board_line(obj=certificate.answer),
        boards=[list(lines) for lines in round_boards.board_lines],
        objects=[_object_record(declared=declared) for declared in round_boards.declared],
        certificate=IntersectionCertificateRecord(
            candidates_without_seat=list(certificate.candidates_without_seat),
            shared_cells=partial.cell,
            shared_looks=partial.look,
            shared_shapes_and_cells=partial.shape_and_cell,
            shared_colors_and_cells=partial.color_and_cell,
            dump_object_mentions=certificate.dump_object_mentions,
            sequential_filter_object_mentions=certificate.sequential_filter_object_mentions,
            generation_attempts=round_boards.attempts,
        ),
    )


def declared_from_event(event: SpotTheIntersectionRoundStarted) -> list[DeclaredObject]:
    """The declaration a recorded round carried, with seats counted from 0 again."""
    declared: list[DeclaredObject] = []
    for record in event.objects:
        column, row = parse_cell_label(label=record.cell, grid_size=event.grid_size)
        declared.append(
            DeclaredObject(
                kind=ObjectKind(record.kind),
                obj=BoardObject(shape=record.shape, color=record.color, column=column, row=row),
                seats=frozenset(number - 1 for number in record.seat_numbers),
            )
        )
    return declared
