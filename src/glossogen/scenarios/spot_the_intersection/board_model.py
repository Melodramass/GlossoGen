"""The objects on a spot_the_intersection board and the grid they sit on.

An object is a shape and a color in one cell of a square grid. A cell is named
by a column letter and a row number, ``A1`` at the top left, and every board in
a run uses the same names, so two viewers naming the same cell mean the same
place.
"""

from typing import Literal, NamedTuple, get_args

# The types the submit tool's schema is built from, so what a viewer may submit
# and what a board may hold are one list.
Shape = Literal["circle", "square", "triangle", "star"]
Color = Literal["red", "blue", "green", "yellow"]

SHAPES: tuple[str, ...] = get_args(Shape)
COLORS: tuple[str, ...] = get_args(Color)

# One letter per column.
MAX_GRID_SIZE = 26


class BoardObject(NamedTuple):
    """A shape and a color at a ``(column, row)`` cell, both counted from 0."""

    shape: str
    color: str
    column: int
    row: int

    @property
    def cell(self) -> tuple[int, int]:
        """The ``(column, row)`` this object sits in."""
        return (self.column, self.row)

    @property
    def look(self) -> tuple[str, str]:
        """The ``(shape, color)`` pair, the object without its cell."""
        return (self.shape, self.color)


def column_letter(column: int) -> str:
    """Return the letter naming ``column`` (``A`` for 0)."""
    return chr(ord("A") + column)


def cell_label(column: int, row: int) -> str:
    """Name a cell by its column letter and 1-based row (``C4`` is column 2, row 3)."""
    return f"{column_letter(column=column)}{row + 1}"


def all_cells(grid_size: int) -> list[tuple[int, int]]:
    """Every ``(column, row)`` of a ``grid_size`` x ``grid_size`` grid, column by column."""
    return [(column, row) for column in range(grid_size) for row in range(grid_size)]
