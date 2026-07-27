import pytest

from sc2_replay_reviewer.time import (
    format_dual_time,
    loops_to_game_seconds,
    loops_to_real_seconds,
)


def test_normal_loop_conversion():
    assert loops_to_game_seconds(16) == pytest.approx(1.0)
    assert loops_to_real_seconds(16, "Normal") == pytest.approx(1.0)


def test_faster_real_seconds():
    assert loops_to_real_seconds(22.4, "Faster") == pytest.approx(1.0)
    assert loops_to_real_seconds(960 * 16, "Faster") == pytest.approx(685.7142857)


def test_twelve_minute_dual_time():
    assert format_dual_time(12 * 60 * 16, "Faster") == "12:00 game / 8:34 real"


def test_fastest_is_only_an_input_alias():
    assert loops_to_real_seconds(22.4, "Fastest") == pytest.approx(1.0)
