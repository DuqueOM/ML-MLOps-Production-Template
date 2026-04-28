# Developer Certificate of Origin (DCO)

This project uses the Developer Certificate of Origin (DCO) for all
contributions.

By signing off your commits, you certify that you have the right to
submit your contribution under the project's license and that you
agree to the terms of the DCO.

DCO text: <https://developercertificate.org/>

## Requirement

Every commit must include a `Signed-off-by` trailer.

Example:

```bash
git commit -s -m "fix: correct digest pinning in deploy workflow"
```

This adds a line like:

```text
Signed-off-by: Your Name <your.email@example.com>
```

## Why this project uses DCO

This repository is intended to be low-friction, transparent, and
friendly to individual contributors and engineers contributing from
companies. The DCO provides provenance and contribution attestation
without requiring a separate CLA workflow.

## Pull requests

All commits in a pull request must be signed off. If a commit is
missing sign-off, amend it:

```bash
git commit --amend -s --no-edit
```

Or, for multiple commits:

```bash
git rebase --signoff <base-branch>
```

## Web-based commits

If GitHub sign-off enforcement is enabled, web-based commits can be
signed automatically by GitHub.

## Maintainer policy

Maintainers will not merge commits that are missing DCO sign-off.
