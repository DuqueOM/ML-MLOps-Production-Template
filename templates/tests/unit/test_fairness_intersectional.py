"""Tests for intersectional fairness (C6, v1.8.1)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SVC = Path(__file__).resolve().parents[2] / "service" / "src" / "{service}"
sys.path.insert(0, str(_SVC.parent.parent))

# The template service dir is literally "{service}" — dynamic import.
import importlib.util

spec = importlib.util.spec_from_file_location("fairness", _SVC / "fairness.py")
fairness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fairness)  # type: ignore[union-attr]


def _synth_biased(n: int = 400):
    """Synthesize a dataset where intersection (race=Black, gender=Female) is under-approved."""
    rng = np.random.default_rng(42)
    race = rng.choice(["White", "Black"], size=n, p=[0.5, 0.5])
    gender = rng.choice(["Male", "Female"], size=n, p=[0.5, 0.5])
    base_rate = np.full(n, 0.5)
    # Subgroup bias: Black Female sees lower positive rate
    subgroup = (race == "Black") & (gender == "Female")
    base_rate[subgroup] = 0.1
    y_pred = (rng.random(n) < base_rate).astype(int)
    y_true = (rng.random(n) < 0.5).astype(int)
    sensitive = pd.DataFrame({"race": race, "gender": gender})
    return y_true, y_pred, sensitive


class TestIntersectional:
    def test_intersectional_flag_off_by_default(self):
        y_true, y_pred, sensitive = _synth_biased()
        report = fairness.run_fairness_audit(y_true, y_pred, sensitive)
        assert report["_summary"]["intersectional_evaluated"] is False
        assert "_intersectional" not in report

    def test_intersectional_reports_subgroup_failure(self):
        y_true, y_pred, sensitive = _synth_biased()
        report = fairness.run_fairness_audit(
            y_true, y_pred, sensitive, intersectional=True, min_intersectional_samples=20
        )
        # Per-attribute DIR may pass, but intersection should fail for subgroup
        inter = report["_intersectional"]
        key = "(race, gender)"
        assert key in inter
        assert inter[key]["fairness"]["disparate_impact_pass"] is False
        assert "intersectional_evaluated" in report["_summary"]
        assert report["_summary"]["intersectional_evaluated"] is True

    def test_intersectional_single_attribute_skipped(self):
        y_true = np.array([0, 1, 1, 0])
        y_pred = np.array([0, 1, 0, 0])
        sensitive = pd.DataFrame({"only_one": ["A", "B", "A", "B"]})
        report = fairness.run_fairness_audit(y_true, y_pred, sensitive, intersectional=True)
        # No pairs to evaluate; intersectional section must be absent or empty
        assert report["_summary"]["intersectional_evaluated"] is False

    def test_intersectional_small_cell_marked_insufficient(self):
        n = 30
        rng = np.random.default_rng(0)
        race = rng.choice(["W", "B"], size=n, p=[0.97, 0.03])
        gender = rng.choice(["M", "F"], size=n, p=[0.97, 0.03])
        y_true = rng.integers(0, 2, size=n)
        y_pred = rng.integers(0, 2, size=n)
        sensitive = pd.DataFrame({"race": race, "gender": gender})
        report = fairness.compute_intersectional_fairness(
            y_true, y_pred, sensitive, min_samples_per_cell=5
        )
        # Rare (B, F) cells should be marked insufficient_data
        groups = report["(race, gender)"]["groups"]
        insufficient = [g for g in groups.values() if isinstance(g, dict) and g.get("status") == "insufficient_data"]
        assert len(insufficient) >= 1
