"""Synthetic method checks; no real sample or forecast performance claims."""
from datetime import date, timedelta

import pytest

from betdoctore.paired_evaluation import compare, paired_errors


def sample():
    model, baseline = [], []
    periods = []
    for year in (2023, 2024):
        start = date(year, 1, 1)
        periods.append({"start": str(start), "end": str(start+timedelta(days=39))})
        for day in range(40):
            for game in range(4):
                row = {"game_key": f"{year}-{day}-{game}",
                       "date": str(start+timedelta(days=day)),
                       "cutoff": f"{start+timedelta(days=day)}T18:00:00+00:00",
                       "prediction": 210., "actual": 220.}
                model.append(row)
                baseline.append({**row, "prediction": 215.})
    return model, baseline, periods


def test_constant_paired_difference_and_reproducibility():
    model, baseline, periods = sample()
    report = compare(model, baseline, periods, repetitions=100)
    assert report == compare(model, baseline, periods, repetitions=100)
    assert report["games"] == 320
    assert report["planning_target_met"]
    assert report["paired_mae_difference"] == 5
    assert report["interval"] == [5, 5]
    assert not report["independent_test_ready"]
    assert not report["production_ready"]
    assert not report["planning_target_is_significance_guarantee"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "cutoff", "outcome", "nonfinite"])
def test_pairing_fails_closed(mutation):
    model, baseline, _ = sample()
    if mutation == "missing":
        baseline.pop()
    elif mutation == "duplicate":
        baseline.append(baseline[0])
    elif mutation == "cutoff":
        baseline[0]["cutoff"] = "2023-01-01T17:00:00+00:00"
    elif mutation == "outcome":
        baseline[0]["actual"] = 221
    else:
        baseline[0]["prediction"] = float("nan")
    with pytest.raises(ValueError):
        paired_errors(model, baseline)


def test_periods_and_development_exclusion():
    model, baseline, periods = sample()
    with pytest.raises(ValueError, match="overlap"):
        compare(model, baseline, [periods[0], periods[0]])
    for row in model+baseline:
        row["date"] = row["date"].replace("2023", "2022")
    with pytest.raises(ValueError, match="2022"):
        compare(model, baseline, [{"start": "2022-01-01", "end": "2024-12-31"}])


def test_short_sample_cannot_manufacture_interval():
    model, baseline, periods = sample()
    report = compare(model[:4], baseline[:4], periods[:1], repetitions=100)
    assert not report["planning_target_met"]
    assert report["interval"] is None
    assert report["uncertainty_status"] == "INSUFFICIENT_TEMPORAL_SUPPORT"


def test_block_sensitivity_and_clustered_errors():
    model, baseline, periods = sample()
    for i, row in enumerate(model):
        row["prediction"] += (i//4 % 10)*2
    for block in (3, 7):
        result = compare(model, baseline, periods, block_days=block, repetitions=100)
        assert result["interval"][0] < result["interval"][1]
    assert compare(model, baseline, periods, block_days=14)["interval"] is None
