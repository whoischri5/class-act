from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app import features


def make_match(day, home, away, result, hg=1, ag=0, season=2023, neutral=False):
    return SimpleNamespace(
        match_date=datetime(2023, 9, 1) + timedelta(days=day),
        season=season, home_team_id=home, away_team_id=away,
        home_goals=hg, away_goals=ag, result=result, neutral=neutral,
    )


def test_expected_score_is_half_for_equal_ratings():
    assert features.expected_score(1500, 1500) == pytest.approx(0.5)


def test_expected_scores_sum_to_one():
    assert features.expected_score(1700, 1500) + features.expected_score(1500, 1700) == pytest.approx(1)


def test_elo_update_is_zero_sum_and_rewards_winner():
    tracker = features.FeatureTracker()
    tracker.update(1, 2, "H", 2, 0)
    home, away = tracker.team(1).elo, tracker.team(2).elo
    assert home > features.BASE_ELO > away
    assert home + away == pytest.approx(2 * features.BASE_ELO)


def test_home_draw_loses_elo_because_home_was_expected_to_win():
    tracker = features.FeatureTracker()
    tracker.update(1, 2, "D", 1, 1)
    assert tracker.team(1).elo < features.BASE_ELO


def test_neutral_venue_draw_between_equals_changes_nothing():
    tracker = features.FeatureTracker()
    tracker.update(1, 2, "D", 1, 1, neutral=True)
    assert tracker.team(1).elo == pytest.approx(features.BASE_ELO)


def test_form_uses_only_the_last_window_of_matches():
    tracker = features.FeatureTracker()
    for _ in range(features.FORM_WINDOW):
        tracker.update(1, 2, "A", 0, 1)  # team 1 loses a bunch...
    for _ in range(features.FORM_WINDOW):
        tracker.update(1, 2, "H", 3, 0)  # ...then wins the last N
    assert tracker.team(1).form == 3.0
    assert tracker.team(1).goal_diff == 3.0


def test_no_leakage_snapshot_ignores_the_match_itself_and_the_future():
    """The core leakage test: changing a match's result (or any later one) must not
    change the features we computed for that match."""
    base = [make_match(0, 1, 2, "H"), make_match(7, 2, 1, "D"), make_match(14, 1, 2, "A")]
    changed = [make_match(0, 1, 2, "H"), make_match(7, 2, 1, "H", 5, 0), make_match(14, 1, 2, "H", 4, 0)]
    _, snaps_a = features.walk(base)
    _, snaps_b = features.walk(changed)
    assert snaps_a[0][1] == snaps_b[0][1]
    assert snaps_a[1][1] == snaps_b[1][1]  # match 2's own result changed, its snapshot must not


def test_walk_processes_in_date_order_even_if_input_is_shuffled():
    matches = [make_match(14, 1, 2, "A"), make_match(0, 1, 2, "H"), make_match(7, 2, 1, "D")]
    _, snaps = features.walk(matches)
    assert [m.match_date.day for m, _ in snaps] == [1, 8, 15]
    assert snaps[0][1]["home_elo_pre"] == features.BASE_ELO


def test_ratings_regress_toward_average_in_a_new_season():
    tracker = features.FeatureTracker()
    tracker.snapshot(1, 2, season=2022)
    for _ in range(10):
        tracker.update(1, 2, "H", 3, 0)
    before = tracker.team(1).elo
    snap = tracker.snapshot(1, 2, season=2023)
    assert features.BASE_ELO < snap["home_elo_pre"] < before


def test_model_inputs_match_feature_columns():
    snap = features.FeatureTracker().snapshot(1, 2)
    assert len(features.model_inputs(snap, neutral=True)) == len(features.FEATURE_COLUMNS)
