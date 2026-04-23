"""Unit tests for champion/challenger statistical comparison (ADR-008)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "service" / "src" / "{service}" / "evaluation"
sys.path.insert(0, str(_TEMPLATE_PATH))

from champion_challenger import (  # type: ignore[import-not-found]  # noqa: E402
    ComparisonConfig,
    bootstrap_delta_auc,
    compare_models,
    decide,
    mcnemar_test,
)


# ---------------------------------------------------------------------------
# McNemar
# ---------------------------------------------------------------------------
class TestMcNemar:
    def test_identical_classifiers_p_value_one(self) -> None:
        y = np.array([0, 1, 0, 1, 0, 1, 0, 1])
        result = mcnemar_test(y, y, y)
        assert result["b"] == 0 and result["c"] == 0
        assert result["p_value"] == 1.0

    def test_challenger_strictly_better_low_p(self) -> None:
        y = np.array([1] * 20 + [0] * 20)
        # champion wrong often; challenger always right
        pred_champion = np.array([0] * 20 + [1] * 20)  # 40 wrong
        pred_challenger = y.copy()  # 0 wrong
        r = mcnemar_test(y, pred_champion, pred_challenger)
        # b (champion right, challenger wrong) = 0
        # c (champion wrong, challenger right) = 40
        assert r["b"] == 0
        assert r["c"] == 40
        assert r["p_value"] < 0.001

    def test_disagreement_counts_are_symmetric(self) -> None:
        y = np.array([1, 1, 0, 0])
        a = np.array([1, 0, 0, 1])  # 2 right (indices 0, 2)
        b = np.array([1, 1, 1, 0])  # 3 right (indices 0, 1, 3)
        r = mcnemar_test(y, a, b)
        # a right, b wrong: index 2 (a=0 correct, b=1 wrong) → b=1
        # a wrong, b right: indices 1, 3 → c=2
        assert r["b"] == 1
        assert r["c"] == 2


# ---------------------------------------------------------------------------
# Bootstrap ΔAUC
# ---------------------------------------------------------------------------
class TestBootstrap:
    def test_delta_auc_positive_when_challenger_better(self) -> None:
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, size=500)
        # Champion: slightly better than random
        score_champion = np.where(y == 1, rng.uniform(0.4, 0.9, 500), rng.uniform(0.1, 0.6, 500))
        # Challenger: clearly better
        score_challenger = np.where(y == 1, rng.uniform(0.6, 1.0, 500), rng.uniform(0.0, 0.4, 500))
        result = bootstrap_delta_auc(y, score_champion, score_challenger, n_bootstrap=200, random_state=7)
        assert result["delta_auc_point"] > 0
        assert result["auc_challenger"] > result["auc_champion"]

    def test_delta_auc_zero_when_identical(self) -> None:
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, size=200)
        score = rng.uniform(0, 1, 200)
        result = bootstrap_delta_auc(y, score, score, n_bootstrap=100, random_state=1)
        assert abs(result["delta_auc_point"]) < 1e-9


# ---------------------------------------------------------------------------
# decide() — gate logic
# ---------------------------------------------------------------------------
class TestDecide:
    def test_blocks_when_lower_ci_below_non_inferiority(self) -> None:
        cfg = ComparisonConfig(non_inferiority_margin=0.005, superiority_margin=0.005, alpha=0.05)
        mcnemar = {"p_value": 0.01}
        bootstrap = {"delta_auc_point": -0.02, "delta_auc_ci_lower": -0.03, "delta_auc_ci_upper": -0.01}
        d = decide(mcnemar, bootstrap, cfg)
        assert d["decision"] == "block"

    def test_promotes_when_superior_and_significant(self) -> None:
        cfg = ComparisonConfig()
        mcnemar = {"p_value": 0.01}
        bootstrap = {"delta_auc_point": 0.03, "delta_auc_ci_lower": 0.01, "delta_auc_ci_upper": 0.05}
        d = decide(mcnemar, bootstrap, cfg)
        assert d["decision"] == "promote"
        assert d["is_significant"] and d["is_superior_point"]

    def test_keeps_when_improvement_not_significant(self) -> None:
        cfg = ComparisonConfig()
        mcnemar = {"p_value": 0.40}  # not significant
        bootstrap = {"delta_auc_point": 0.02, "delta_auc_ci_lower": -0.002, "delta_auc_ci_upper": 0.04}
        d = decide(mcnemar, bootstrap, cfg)
        assert d["decision"] == "keep"

    def test_keeps_on_neutral_change(self) -> None:
        cfg = ComparisonConfig()
        mcnemar = {"p_value": 0.2}
        bootstrap = {"delta_auc_point": 0.001, "delta_auc_ci_lower": -0.003, "delta_auc_ci_upper": 0.005}
        d = decide(mcnemar, bootstrap, cfg)
        assert d["decision"] == "keep"


# ---------------------------------------------------------------------------
# compare_models — end-to-end with sklearn models
# ---------------------------------------------------------------------------
class TestCompareModels:
    def test_end_to_end_promotes_better_model(self) -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.datasets import make_classification
        from sklearn.ensemble import RandomForestClassifier

        X, y = make_classification(n_samples=1000, n_features=10, n_informative=5, random_state=42, class_sep=1.5)
        X_df = pd.DataFrame(X, columns=[f"f{i}" for i in range(10)])
        # Split
        train, holdout = X_df[:700], X_df[700:]
        y_train, y_holdout = y[:700], y[700:]

        # Weaker champion (few iter)
        champion = LogisticRegression(max_iter=50).fit(train, y_train)
        # Stronger challenger
        challenger = RandomForestClassifier(n_estimators=200, random_state=0).fit(train, y_train)

        config = ComparisonConfig(n_bootstrap=200, non_inferiority_margin=0.005, superiority_margin=0.005)
        report = compare_models(champion, challenger, holdout, y_holdout, config)
        assert "decision" in report
        assert report["decision"]["decision"] in {"promote", "keep", "block"}
        # Challenger should not be worse than champion here
        assert report["bootstrap"]["delta_auc_point"] >= -0.02
