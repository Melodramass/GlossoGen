"""The fewest-characters comparison competing teams are ranked by."""

from glossogen.engine.fewest_characters_winner import fewest_characters_winners


def test_the_eligible_team_with_fewest_characters_wins() -> None:
    assert fewest_characters_winners(
        characters_by_eligible_team_id={"team_a": 120, "team_b": 80}
    ) == frozenset({"team_b"})


def test_tied_teams_both_win() -> None:
    assert fewest_characters_winners(
        characters_by_eligible_team_id={"team_a": 80, "team_b": 80}
    ) == frozenset({"team_a", "team_b"})


def test_no_eligible_team_means_no_winner() -> None:
    assert fewest_characters_winners(characters_by_eligible_team_id={}) == frozenset()
