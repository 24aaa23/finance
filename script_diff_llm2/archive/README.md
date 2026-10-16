# Archived experiment metadata

This directory contains logs, input snapshots and metadata for experiment runs not selected for retention, plus older launcher logs. The corresponding raw/graded CSVs had already been removed at the user's explicit request.

- `experiments/<experiment>/runs/...` preserves the previous run hierarchy.
- `launcher_logs/<experiment>/` holds historical launcher output.
- Original paths and destinations are recorded in `analysis/organization_20261016/organization_manifest.json`.

These folders are provenance archives, not complete resumable runs. Use `results/README.md` to find the seven retained graded reports and six raw reports. Experiment launcher code and native baseline source snapshots remain in `ablations/`.
