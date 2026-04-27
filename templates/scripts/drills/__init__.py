"""Reproducible operational drills for {ServiceName} (PR-C3).

Each drill is a STANDALONE script that exercises a real production
code path against synthetic deterministic inputs and writes evidence
to ``docs/runbooks/drills/<drill>/<run-id>/``. The drills are wired
into the scaffold smoke chain via ``test_drills_reproducible.py``;
running them quarterly (or after any change touching the exercised
code path) produces fresh evidence with a stable verdict.
"""
