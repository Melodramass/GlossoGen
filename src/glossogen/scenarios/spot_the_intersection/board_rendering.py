"""Turn a board into the lines a viewer reads, and read those lines back.

The lines are the only description of a board an agent ever receives, so they
are also what certification checks. ``parse_board_line`` inverts
``render_board_line`` exactly, and a line it cannot read raises rather than
being skipped.
"""

import re

from glossogen.scenarios.spot_the_intersection.board_model import (
    COLORS,
    SHAPES,
    BoardObject,
    cell_label,
)

_LINE_PATTERN = re.compile(r"^(?P<color>[a-z]+) (?P<shape>[a-z]+) at (?P<cell>[A-Z][0-9]+)$")
_CELL_PATTERN = re.compile(r"^(?P<column>[A-Z])(?P<row>[1-9][0-9]*)$")


def render_board_line(obj: BoardObject) -> str:
    """Render one object as ``<color> <shape> at <cell>``, e.g. ``red circle at C4``."""
    return f"{obj.color} {obj.shape} at {cell_label(column=obj.column, row=obj.row)}"


def parse_cell_label(label: str, grid_size: int) -> tuple[int, int]:
    """Return the ``(column, row)`` a label such as ``C4`` names on this grid.

    Raises ``ValueError`` for a label that is malformed or lies off the grid.
    """
    match = _CELL_PATTERN.match(label)
    if match is None:
        raise ValueError(f"{label!r} is not a cell name like A1")
    column = ord(match.group("column")) - ord("A")
    row = int(match.group("row")) - 1
    if column >= grid_size or row >= grid_size:
        raise ValueError(f"{label!r} is outside the {grid_size}x{grid_size} grid")
    return (column, row)


def parse_board_line(line: str, grid_size: int) -> BoardObject:
    """Read one rendered line back into the object it names.

    Raises ``ValueError`` for anything ``render_board_line`` could not have
    produced on this grid.
    """
    match = _LINE_PATTERN.match(line)
    if match is None:
        raise ValueError(f"{line!r} is not a board line")
    shape = match.group("shape")
    color = match.group("color")
    if shape not in SHAPES:
        raise ValueError(f"{line!r} names an unknown shape {shape!r}")
    if color not in COLORS:
        raise ValueError(f"{line!r} names an unknown color {color!r}")
    column, row = parse_cell_label(label=match.group("cell"), grid_size=grid_size)
    return BoardObject(shape=shape, color=color, column=column, row=row)
