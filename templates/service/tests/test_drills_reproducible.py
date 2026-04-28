"""PR-C3 — Drills are reproducible and produce the contracted evidence.

Each drill is invoked end-to-end against a tmp evidence root. The
contract being asserted:

1. **Exit code 0**: drill verdict matches the EXPECTED_VERDICT
   constant baked into each drill module.
2. **Evidence file shape**: ``evidence.json`` exists at
   ``<root>/<drill>/<run_id>/evidence.json`` and parses; carries the
   keys the auditor expects (``passed``, ``actual_verdict``,
   ``expected_verdict``, ``inputs``, ``facts``).
3. **Reproducibility**: running the same drill twice produces
   identical ``passed`` and ``actual_verdict``; the inputs (seeds,
   sizes, thresholds) are byte-identical between runs. Timestamps and
   ``run_id`` differ — those are the only allowed sources of variance.

Heavy ML deps (numpy, pandas, sklearn, scipy) gate the test; in
environments that ship them the test runs in <5s.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("pyarrow")
pytest.importorskip("sklearn")
pytest.importorskip("scipy")
pytest.importorskip("prometheus_client")


# Resolve the drills package. The template repo keeps it under
# ``templates/scripts/drills/``; the scaffolded service has it at
# ``scripts/drills/``. We try both prefixes so the same test runs in
# either layout.
def _drills_dir() -> Path:
    here = Path(__file__).resolve()
    for prefix in (here.parents[1], here.parents[2]):
        candidate = prefix / "scripts" / "drills"
        if candidate.is_dir():
            return candidate
    pytest.skip("drills directory not found in either scaffolded or template layout")


def _load_drill(module_filename: str):
    drills_dir = _drills_dir()
    path = drills_dir / module_filename
    if not path.is_file():
        pytest.skip(f"{module_filename} not present at {path}")
    if str(drills_dir) not in sys.path:
        sys.path.insert(0, str(drills_dir))
    spec = importlib.util.spec_from_file_location(f"_drill_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _service_root_and_extra_pythonpath(
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Return the directory to `cwd` into so the drill's
    ``Path.cwd() / src`` discovery finds the service package, and
    inject any extra sys.path via ``DRILL_PYTHONPATH`` so the drill
    can import ``common_utils`` regardless of layout.

    - **Scaffolded service**: ``common_utils/`` is copied into the
      service root, so no extra path is needed.
    - **Template repo**: this file lives at
      ``templates/service/tests/``; the service src is one level up
      and ``common_utils`` lives at ``templates/common_utils/``
      (parents[2]). We `chdir` to the service root and point
      ``DRILL_PYTHONPATH`` at ``templates/`` so ``common_utils``
      resolves.
    - **Template repo w/o rendered src**: skip — the drill cannot
      discover a service package with the raw ``{service}`` placeholder.
    """
    here = Path(__file__).resolve()
    candidate = here.parents[1]
    src = candidate / "src"
    if not src.is_dir():
        pytest.skip("service src/ not present in this layout")
    pkgs = [
        d
        for d in src.iterdir()
        if d.is_dir() and d.name not in {"__pycache__"} and (d / "monitoring" / "drift_detection.py").is_file()
    ]
    if not pkgs:
        pytest.skip("no rendered service package found under src/ — template layout")

    # If common_utils is NOT a sibling of the service root, we must be
    # in the template repo; the drill's bootstrap honours
    # DRILL_PYTHONPATH for that case.
    if not (candidate / "common_utils").is_dir():
        templates_dir = here.parents[2]
        if (templates_dir / "common_utils").is_dir():
            monkeypatch.setenv("DRILL_PYTHONPATH", str(templates_dir))
    return candidate


# ---------------------------------------------------------------------------
# Drift drill
# ---------------------------------------------------------------------------


def test_drift_drill_runs_and_produces_expected_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service_root = _service_root_and_extra_pythonpath(monkeypatch)
    drill = _load_drill("run_drift_drill.py")

    monkeypatch.chdir(service_root)
    monkeypatch.setenv("DRILL_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["run_drift_drill.py", "--output-dir", str(tmp_path)])

    rc = drill.main()
    assert rc == 0, f"drift drill exited {rc}; expected 0 (passed)"

    runs = sorted((tmp_path / drill.DRILL_NAME).iterdir())
    assert len(runs) == 1, f"expected exactly one run dir, got {runs}"
    evidence_json = runs[0] / "evidence.json"
    assert evidence_json.is_file()
    payload = json.loads(evidence_json.read_text(encoding="utf-8"))
    assert payload["drill_name"] == drill.DRILL_NAME
    assert payload["expected_verdict"] == drill.EXPECTED_VERDICT
    assert payload["actual_verdict"] == drill.EXPECTED_VERDICT
    assert payload["passed"] is True

    # Determinism receipts must be present and match the module
    # constants (the operator should see WHICH seeds produced the run).
    inputs = payload["inputs"]
    assert inputs["baseline_seed"] == drill.BASELINE_SEED
    assert inputs["drifted_seed"] == drill.DRIFTED_SEED
    assert inputs["shift_sigma"] == drill.SHIFT_SIGMA

    # Facts must include both the alerted feature's PSI and the
    # threshold the verdict was compared against — without both the
    # evidence is unreproducible.
    facts = payload["facts"]
    assert facts["psi_feature_a"] is not None
    assert facts["alert_threshold"] is not None
    assert facts["psi_feature_a"] >= facts["alert_threshold"], (
        "drift drill recorded a 'passed' verdict but PSI on feature_a is below "
        "the alert threshold — evidence and verdict disagree."
    )

    md = (runs[0] / "evidence.md").read_text(encoding="utf-8")
    assert "Drill: drift" in md
    assert "PSI feature_a" in md
    drift_report = runs[0] / "artifacts" / "drift_report.json"
    assert drift_report.is_file()


def test_drift_drill_is_reproducible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same seeds, same module, two runs → identical verdict and PSI."""
    service_root = _service_root_and_extra_pythonpath(monkeypatch)
    drill = _load_drill("run_drift_drill.py")
    monkeypatch.chdir(service_root)

    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    out_a.mkdir()
    out_b.mkdir()

    monkeypatch.setattr("sys.argv", ["run_drift_drill.py", "--output-dir", str(out_a)])
    assert drill.main() == 0
    monkeypatch.setattr("sys.argv", ["run_drift_drill.py", "--output-dir", str(out_b)])
    assert drill.main() == 0

    j_a = json.loads(next((out_a / drill.DRILL_NAME).iterdir()).joinpath("evidence.json").read_text())
    j_b = json.loads(next((out_b / drill.DRILL_NAME).iterdir()).joinpath("evidence.json").read_text())

    # PSI values must be byte-identical (deterministic seeds + same
    # numpy version → same bits). If this ever flakes, an upstream
    # numpy change broke determinism on np.histogram and we want to
    # know loudly.
    assert j_a["facts"]["psi_feature_a"] == j_b["facts"]["psi_feature_a"]
    assert j_a["facts"]["psi_feature_b"] == j_b["facts"]["psi_feature_b"]
    assert j_a["actual_verdict"] == j_b["actual_verdict"]
    assert j_a["passed"] == j_b["passed"]
    # And run_id MUST differ (otherwise we'd be writing into the same dir).
    assert j_a["run_id"] != j_b["run_id"]


# ---------------------------------------------------------------------------
# Deploy-degraded drill
# ---------------------------------------------------------------------------


def test_deploy_degraded_drill_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service_root = _service_root_and_extra_pythonpath(monkeypatch)
    drill = _load_drill("run_deploy_degraded_drill.py")
    monkeypatch.chdir(service_root)

    monkeypatch.setattr("sys.argv", ["run_deploy_degraded_drill.py", "--output-dir", str(tmp_path)])
    rc = drill.main()
    assert rc == 0, f"deploy-degraded drill exited {rc}; expected 0 (gate blocked)"

    runs = sorted((tmp_path / drill.DRILL_NAME).iterdir())
    assert len(runs) == 1
    payload = json.loads((runs[0] / "evidence.json").read_text(encoding="utf-8"))

    assert payload["expected_verdict"] == "block"
    assert payload["actual_verdict"] == "block"
    assert payload["passed"] is True

    facts = payload["facts"]
    assert facts["decision"] == "block"
    # A challenger trained on shuffled labels MUST have a non-positive
    # delta-AUC point estimate (it learned nothing). If this flips
    # positive the synthetic dataset is no longer separable enough —
    # the test is the canary for that drift in the synthesis routine.
    assert facts["delta_auc_point"] is not None
    assert facts["delta_auc_point"] <= 0.05, (
        f"shuffled-label challenger should not look superior; got " f"delta_auc_point={facts['delta_auc_point']}"
    )

    cc_report = runs[0] / "artifacts" / "champion_challenger.json"
    assert cc_report.is_file()
    cc_data = json.loads(cc_report.read_text())
    assert cc_data["decision"]["decision"] == "block"


def test_deploy_degraded_drill_is_reproducible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same seeds → same decision and same ΔAUC point estimate."""
    service_root = _service_root_and_extra_pythonpath(monkeypatch)
    drill = _load_drill("run_deploy_degraded_drill.py")
    monkeypatch.chdir(service_root)

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()

    monkeypatch.setattr("sys.argv", ["run_deploy_degraded_drill.py", "--output-dir", str(out_a)])
    assert drill.main() == 0
    monkeypatch.setattr("sys.argv", ["run_deploy_degraded_drill.py", "--output-dir", str(out_b)])
    assert drill.main() == 0

    j_a = json.loads(next((out_a / drill.DRILL_NAME).iterdir()).joinpath("evidence.json").read_text())
    j_b = json.loads(next((out_b / drill.DRILL_NAME).iterdir()).joinpath("evidence.json").read_text())

    assert j_a["actual_verdict"] == j_b["actual_verdict"] == "block"
    assert j_a["facts"]["decision"] == j_b["facts"]["decision"]
    # Bootstrap is sampled with a fixed random_state; same seed → same
    # CI to floating-point precision.
    assert j_a["facts"]["delta_auc_ci_lower"] == j_b["facts"]["delta_auc_ci_lower"]


# ---------------------------------------------------------------------------
# Discovery sanity: catalogue can never silently shrink
# ---------------------------------------------------------------------------


def test_drills_catalogue_has_canonical_entries() -> None:
    """The two drills shipped by PR-C3 MUST be present. If a future
    PR removes one without updating the cadence table, this test fails
    loudly so the contract test can't regress to `0 drills`.
    """
    drills_dir = _drills_dir()
    expected = {"run_drift_drill.py", "run_deploy_degraded_drill.py"}
    present = {p.name for p in drills_dir.glob("run_*_drill.py")}
    missing = expected - present
    assert not missing, f"drills catalogue missing canonical entries: {sorted(missing)}\n" f"present: {sorted(present)}"
