"""Who wins a round that competing teams play for the fewest characters.

Defines ``fewest_characters_winners``: among the teams that passed the round's
correctness gate, the ones that sent the fewest characters. Every tied team
wins. What makes a team eligible is the scenario's rule; this is only the
comparison.
"""

from collections.abc import Mapping


def fewest_characters_winners(characters_by_eligible_team_id: Mapping[str, int]) -> frozenset[str]:
    """Return the eligible teams that spent the fewest characters (none if none are eligible)."""
    if not characters_by_eligible_team_id:
        return frozenset()
    fewest = min(characters_by_eligible_team_id.values())
    return frozenset(
        team_id
        for team_id, characters in characters_by_eligible_team_id.items()
        if characters == fewest
    )
