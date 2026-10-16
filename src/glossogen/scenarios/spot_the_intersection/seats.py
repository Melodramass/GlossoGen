"""Names for every team seat, and the lookup from an agent back to its seat.

A team's size is a knob, so agent ids are built rather than listed: ``viewer_1``
onward for a single team, ``viewer_a_1`` and ``viewer_b_1`` onward for two.
Seat ``i`` of each team holds board ``i`` of the round, so the two teams play
the same boards seat for seat.
"""

from typing import NamedTuple

from glossogen.engine.team_declaration import TeamSpec
from glossogen.scenarios.spot_the_intersection.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
)

_TEAM_LETTERS = {TEAM_A_ID: "a", TEAM_B_ID: "b"}
_TEAM_LABELS = {TEAM_A_ID: "Team A", TEAM_B_ID: "Team B"}
_LINKS = {TEAM_SOLO_ID: LINK_CHANNEL_ID, TEAM_A_ID: LINK_A_CHANNEL_ID, TEAM_B_ID: LINK_B_CHANNEL_ID}
_POSTMORTEMS = {
    TEAM_SOLO_ID: POSTMORTEM_CHANNEL_ID,
    TEAM_A_ID: POSTMORTEM_A_CHANNEL_ID,
    TEAM_B_ID: POSTMORTEM_B_CHANNEL_ID,
}


class Seat(NamedTuple):
    """Which team an agent is on and which board it holds, counted from 0."""

    team_id: str
    board_index: int


def team_ids_for(two_teams: bool) -> tuple[str, ...]:
    """The teams a run holds."""
    if two_teams:
        return (TEAM_A_ID, TEAM_B_ID)
    return (TEAM_SOLO_ID,)


def viewer_id(team_id: str, index: int) -> str:
    """The agent id of seat ``index`` (from 0) on ``team_id``."""
    if team_id == TEAM_SOLO_ID:
        return f"viewer_{index + 1}"
    return f"viewer_{_TEAM_LETTERS[team_id]}_{index + 1}"


def viewer_role_name(team_id: str, index: int) -> str:
    """The display name of seat ``index`` (from 0) on ``team_id``."""
    if team_id == TEAM_SOLO_ID:
        return f"Viewer {index + 1}"
    return f"Viewer {index + 1} ({_TEAM_LABELS[team_id]})"


def link_channel_id_for(team_id: str) -> str:
    """The metered link channel of ``team_id``."""
    return _LINKS[team_id]


def postmortem_channel_id_for(team_id: str) -> str:
    """The discussion channel of ``team_id``."""
    return _POSTMORTEMS[team_id]


def link_display_name_for(team_id: str) -> str:
    """What viewers are told to call ``team_id``'s link."""
    if team_id == TEAM_SOLO_ID:
        return "link"
    return f"link ({_TEAM_LABELS[team_id]})"


def postmortem_display_name_for(team_id: str) -> str:
    """What viewers are told to call ``team_id``'s discussion channel."""
    if team_id == TEAM_SOLO_ID:
        return "team discussion"
    return f"team discussion ({_TEAM_LABELS[team_id]})"


def seats_by_agent_id(teams: tuple[TeamSpec, ...]) -> dict[str, Seat]:
    """Map every declared agent to its seat, in each team's declared role order."""
    return {
        role.agent_id: Seat(team_id=team.team_id, board_index=index)
        for team in teams
        for index, role in enumerate(team.roles)
    }
