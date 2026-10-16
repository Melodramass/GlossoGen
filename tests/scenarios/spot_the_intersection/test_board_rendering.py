"""A board line reads back as exactly the object it was rendered from.

Certification checks the parsed lines, not the generator's objects, so a
rendering that dropped or merged an attribute would be certified on what the
viewers saw. These hold the two directions together.
"""

import pytest

from glossogen.scenarios.spot_the_intersection.board_model import (
    COLORS,
    MAX_GRID_SIZE,
    SHAPES,
    BoardObject,
    all_cells,
)
from glossogen.scenarios.spot_the_intersection.board_rendering import (
    parse_board_line,
    parse_cell_label,
    render_board_line,
)


@pytest.mark.parametrize("grid_size", [3, 6, 10, MAX_GRID_SIZE])
def test_every_object_on_the_grid_reads_back_as_itself(grid_size: int) -> None:
    lines: set[str] = set()
    for column, row in all_cells(grid_size=grid_size):
        for shape in SHAPES:
            for color in COLORS:
                obj = BoardObject(shape=shape, color=color, column=column, row=row)
                line = render_board_line(obj=obj)
                assert parse_board_line(line=line, grid_size=grid_size) == obj
                lines.add(line)

    assert len(lines) == grid_size * grid_size * len(SHAPES) * len(
        COLORS
    ), "two objects share a line"


def test_a_line_names_its_cell_by_letter_and_row() -> None:
    obj = BoardObject(shape="circle", color="red", column=2, row=3)

    assert render_board_line(obj=obj) == "red circle at C4"


@pytest.mark.parametrize(
    "line",
    [
        "Red circle at C4",
        "red  circle at C4",
        "red circle at c4",
        "red circle at C0",
        "red circle at G1",
        "red circle at A7",
        "purple circle at A1",
        "red hexagon at A1",
        "red circle in A1",
        "red circle at A1 ",
        "",
    ],
)
def test_a_line_render_could_not_produce_is_refused(line: str) -> None:
    with pytest.raises(ValueError):
        parse_board_line(line=line, grid_size=6)


def test_a_cell_off_the_grid_is_refused() -> None:
    assert parse_cell_label(label="F6", grid_size=6) == (5, 5)
    with pytest.raises(ValueError):
        parse_cell_label(label="F7", grid_size=6)
