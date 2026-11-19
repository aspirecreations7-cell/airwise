import os
from typing import get_args

from app.config import load_env_file
from app.schemas import CommuteMode
from app.services.impact import commute_saving, load_factors


def test_car_commute_shows_weekly_saving():
    result = commute_saving("car", 10)
    assert result["kg_co2e_saved_per_week"] > 0
    assert result["commute_switch_to"] == "public_transport"


def test_clean_modes_have_no_saving():
    for mode in ("walk", "cycle", "work_from_home", "public_transport", "two_wheeler"):
        assert commute_saving(mode, 10) == {}


def test_zero_distance_has_no_saving():
    assert commute_saving("car", 0) == {}


def test_factors_cover_every_commute_mode():
    factors = load_factors()["commute_kg_co2e_per_km"]
    assert set(get_args(CommuteMode)) <= set(factors)


def test_load_env_file_sets_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nAIRWISE_TEST_KEY='abc'\n", encoding="utf-8")
    try:
        load_env_file(str(env))
        assert os.environ["AIRWISE_TEST_KEY"] == "abc"
    finally:
        os.environ.pop("AIRWISE_TEST_KEY", None)


def test_load_env_file_ignores_missing_file(tmp_path):
    load_env_file(str(tmp_path / "missing.env"))
