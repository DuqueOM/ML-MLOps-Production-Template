"""Unit tests for input_quality — edge-level quality checks (v1.8.1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_COMMON = Path(__file__).resolve().parents[2] / "common_utils"
sys.path.insert(0, str(_COMMON.parent))

from common_utils.input_quality import (  # noqa: E402
    FeatureQuantiles,
    InputQualityChecker,
    build_from_env,
)


class TestFeatureQuantiles:
    def test_within_range(self):
        fq = FeatureQuantiles("age", 18.0, 85.0)
        assert fq.classify(40) is None

    def test_below(self):
        fq = FeatureQuantiles("age", 18.0, 85.0)
        assert fq.classify(15) == "age:below_p01"

    def test_above(self):
        fq = FeatureQuantiles("age", 18.0, 85.0)
        assert fq.classify(120) == "age:above_p99"

    def test_non_numeric_ignored(self):
        fq = FeatureQuantiles("category", 0.0, 1.0)
        assert fq.classify("XYZ") is None
        assert fq.classify(None) is None


class TestFromFile:
    def _write(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data))

    def test_load_valid_file(self, tmp_path):
        p = tmp_path / "baseline.json"
        self._write(p, {"age": {"p01": 18, "p99": 85}, "score": {"p01": 0.0, "p99": 0.9}})
        c = InputQualityChecker.from_file(p)
        assert c.enabled is True
        assert set(c.quantiles.keys()) == {"age", "score"}

    def test_missing_file_disables(self, tmp_path):
        c = InputQualityChecker.from_file(tmp_path / "nonexistent.json")
        assert c.enabled is False
        assert c.quantiles == {}

    def test_bad_json_disables(self, tmp_path):
        p = tmp_path / "broken.json"
        p.write_text("{{{invalid")
        c = InputQualityChecker.from_file(p)
        assert c.enabled is False

    def test_partial_spec_skips_bad_features(self, tmp_path):
        p = tmp_path / "baseline.json"
        self._write(
            p,
            {
                "good": {"p01": 0, "p99": 10},
                "bad": {"p01": "not a number", "p99": 10},  # invalid
                "missing_p99": {"p01": 0},  # missing key
            },
        )
        c = InputQualityChecker.from_file(p)
        assert list(c.quantiles.keys()) == ["good"]
        assert c.enabled is True


class TestCheck:
    def _checker(self):
        return InputQualityChecker(
            quantiles={
                "age": FeatureQuantiles("age", 18.0, 85.0),
                "balance": FeatureQuantiles("balance", 0.0, 100_000.0),
            }
        )

    def test_all_within_range(self):
        c = self._checker()
        assert c.check({"age": 40, "balance": 50_000}) == []

    def test_flags_out_of_range(self):
        c = self._checker()
        flags = c.check({"age": 15, "balance": 150_000})
        assert "age:below_p01" in flags
        assert "balance:above_p99" in flags

    def test_disabled_returns_empty(self):
        c = InputQualityChecker(enabled=False)
        assert c.check({"age": 1_000_000}) == []

    def test_unknown_features_ignored(self):
        c = self._checker()
        # country has no quantile entry → ignored
        assert c.check({"country": "MX", "age": 40}) == []


class TestBuildFromEnv:
    def test_disabled_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("INPUT_QUALITY_ENABLED", raising=False)
        c = build_from_env(default_path=str(tmp_path / "nope.json"))
        assert c.enabled is False

    def test_enabled_flag_respected(self, monkeypatch, tmp_path):
        p = tmp_path / "baseline.json"
        p.write_text(json.dumps({"x": {"p01": 0, "p99": 1}}))
        monkeypatch.setenv("INPUT_QUALITY_ENABLED", "true")
        monkeypatch.setenv("INPUT_QUALITY_PATH", str(p))
        c = build_from_env()
        assert c.enabled is True
        assert "x" in c.quantiles
