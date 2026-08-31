from decimal import Decimal

import pytest

from app.engine.fantasy_scoring import PRESETS, rubric_for, score, score_preset


# a WR line: 8 catches, 120 yds, 1 TD, plus 10 rushing yds
WR = {"rec": 8, "rec_yd": 120, "rec_td": 1, "rush_yd": 10}
# a QB line: 300 pass yds, 3 pass TD, 1 INT, 20 rush yds, 1 rush TD
QB = {"pass_yd": 300, "pass_td": 3, "pass_int": 1, "rush_yd": 20, "rush_td": 1}


def test_ppr_half_std_differ_only_by_receptions():
    # WR: base = 120*.1 + 6 + 10*.1 = 12 + 6 + 1 = 19, then + rec*{1, .5, 0}
    assert score_preset(WR, "ppr") == Decimal("27.00")       # +8
    assert score_preset(WR, "half_ppr") == Decimal("23.00")  # +4
    assert score_preset(WR, "std") == Decimal("19.00")       # +0


def test_qb_line_is_format_independent():
    # 300*.04 + 3*4 + (-1) + 20*.1 + 6 = 12 + 12 - 1 + 2 + 6 = 31
    expected = Decimal("31.00")
    for fmt in ("ppr", "half_ppr", "std"):
        assert score_preset(QB, fmt) == expected


def test_negatives_and_missing_stats():
    assert score({"fum_lost": 2}, PRESETS["ppr"]) == Decimal("-4.00")
    assert score({}, PRESETS["ppr"]) == Decimal("0.00")
    assert score({"unknown_stat": 99}, PRESETS["ppr"]) == Decimal("0.00")


def test_fractional_yardage_quantizes_to_cents():
    # 47 rush yds = 4.70; 83 rec yds = 8.30
    assert score({"rush_yd": 47, "rec_yd": 83}, PRESETS["std"]) == Decimal("13.00")


def test_rubric_for_defaults_to_ppr():
    assert rubric_for(None) is PRESETS["ppr"]
    assert rubric_for("nonsense") is PRESETS["ppr"]
    assert rubric_for("half_ppr") is PRESETS["half_ppr"]


def test_float_inputs_are_exact():
    # providers hand back floats; scoring must stay penny-exact
    # 5*1 + 63*0.1 + 1*6 = 5 + 6.3 + 6 = 17.30
    assert score_preset({"rec": 5.0, "rec_yd": 63.0, "rec_td": 1.0}, "ppr") == Decimal("17.30")
