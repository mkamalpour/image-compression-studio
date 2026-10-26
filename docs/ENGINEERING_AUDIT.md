# Engineering audit — 2026-10-26

Purpose: Educational image compression and quality comparison.

Classification: **A** (single application/tool).
Final structure: media_studio/, tests/, docs/. Existing capabilities and source material were retained.

| Assessment | Result |
| --- | --- |
| Idea strength | 6/10 |
| Implementation strength | 8/10 |
| Core strength | Codec regressions, synthetic images and source-preserving workflows. |
| Main limitation | Large-image performance and human visual-quality judgements were not measured here. |
| Readiness | Local prototype/tool with the verified baseline below; no production certification |

Scores are subjective engineering estimates, not measured product or model quality.

## Delivered

Added a repo-local run.cmd that activates the assigned existing environment, checks actual startup imports and forwards application arguments. README setup now uses this local launcher.

Assigned environment: **base**. Run `.\run.cmd --check`, then `.\run.cmd`.
The launcher installs nothing and preserves its child exit status. On this workstation
it selects the assigned interpreter; standalone clones fall back to active Python.
VS Code's local interpreter settings were aligned with the same assignment.

## Verification

- **Automated tests:** 45 passed; 0 reported skips; 0 private-report cases deselected.
- **Startup check:** `run.cmd --check` passed from outside the repository;
  required startup modules were imported in the assigned environment.
- **Tested runtime:** Windows; Conda base; Python 3.13.5.
- **Data handling:** tests used temporary/synthetic fixtures. No live transactions,
  provider generation, deployment, new model downloads or package installs were performed.
- **Repository check:** origin/main fetched before publication; no pre-existing local
  changes were present. A tracked-file scan found no matches for the high-confidence
  credential patterns checked. That scan is not a guarantee that all personal data
  or arbitrary secret formats are absent. Ignored local data was not staged.
- **Limits:** optional external workflows, representative real-data quality and all
  possible platform/version combinations remain unverified.
- A first run encountered a Tcl file-read error; a complete rerun passed without a source or environment change.\n
Test command from the repository root:

```powershell
conda activate base
python -m pytest tests -q -p no:cacheprovider
```

## Next three upgrades

1. Export comparison contact sheets.
2. Bounded batch processing.
3. Representative image benchmark pack.

Expected benefit: clearer decisions, more reproducible workflows and stronger evidence
for quality. These are proposed upgrades, not implemented features or measured speedups.

External assets: No external model is needed; a shareable image corpus is useful for measured comparisons.

No root license file is set. No license was selected or changed.

## Additional implementation pass

GUI and CLI reports identify exact RGB working/result pixels with dimension-aware SHA-256 fingerprints. Desktop initialization failures now produce setup guidance; GUI tests reuse one interpreter with fresh widgets instead of repeatedly reinitializing Tcl.

Use: Export a JSON/text report in the desktop app, or inspect report.json from a headless command. Fingerprints identify decoded working pixels, not source-file bytes.

Verification: the complete offline suite passed in the assigned **base**
environment after this change (45 tests). Regression fixtures remain
temporary/synthetic. Optional real-model/data quality and external integrations
remain unverified. No packages, models or additional environments were installed.

The earlier numeric scores are subjective historical assessments; new features do
not automatically establish a higher score or production readiness.
