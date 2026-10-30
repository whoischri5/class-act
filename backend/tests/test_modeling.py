import numpy as np
import pytest

from app.modeling import choose_split, log_loss


def test_log_loss_perfect_and_uniform():
    y = np.array(["H", "D", "A"])
    assert log_loss(y, np.eye(3)) == pytest.approx(0, abs=1e-9)
    assert log_loss(y, np.full((3, 3), 1 / 3)) == pytest.approx(np.log(3))


def test_split_is_chronological_and_skips_warmup_season():
    seasons = np.repeat([2019, 2020, 2021, 2022, 2023], 125)
    train, test, extra = choose_split(seasons)
    assert train == [2020, 2021, 2022] and test == 2023 and extra == []


def test_in_progress_season_is_not_the_test_season():
    seasons = np.concatenate([np.repeat([2021, 2022, 2023, 2024], 125), np.repeat(2025, 20)])
    train, test, extra = choose_split(seasons)
    assert test == 2024 and extra == [2025] and max(train) < test
