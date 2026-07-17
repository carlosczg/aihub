# CURRENT STATE

## Last updated

2026-07-17

## Current milestone

Knowledge Compiler V1.1 (Incremental Engine) implemented, unit-tested, and
successfully executed in production against the real `01-Ingestion`
repository. V1.1.1 (directory-level scan-error patch) completed and
unit-tested; not yet executed against the real `01-Ingestion`.

## Completed

- AI Hub base folder structure created.
- Omnigent installed and configured.
- Claude connected through the user's subscription.
- OneDrive established as the official source of truth.
- Incremental synchronization into `01-Ingestion` implemented.
- Approved file-extension filters configured.
- Initial synchronization completed with 345 documents.
- `aihub.json` created as the platform root configuration.
- Knowledge Compiler V1 implemented (scanner, metadata, manifest, run metadata).
- Knowledge Compiler V1.1 implemented: incremental diff engine, discovered/
  eligible/excluded/processed/failed metrics, atomic staged multi-artifact
  commit, corrupt-manifest detection with explicit `--full` recovery,
  per-run immutable history under `08-Indexes/Metadata/runs/`, `--dry-run`
  and `--full` CLI flags, exit codes 0/1/2.
- 54 unit tests executed successfully (up from 12 in V1), including atomic
  write failure, corrupt manifest, full-rehash classification, discovered
  vs eligible vs excluded, run-ID collision avoidance, and degraded-run
  exit-code coverage.
- First real V1.1 production run executed against `01-Ingestion`
  (run_id `20260717T030748.563951Z-dfb7`, incremental mode, exit code 0 /
  clean). The previous manifest on disk was a legacy V1 manifest
  (schema_version 1, 5,952 documents); this run detected it as
  `valid-legacy-v1`, backfilled `first_seen_at`/`last_verified_at` for
  every carried-over entry, and proceeded as a normal incremental
  comparison against the legacy hashes and paths.
- Document manifest upgraded to schema_version 2 (`first_seen_at`,
  `last_verified_at` added to every record).
- Per-run immutable history now populated: `08-Indexes/Metadata/runs/`
  contains one run-history file for the executed run.
- V1.1.1 completed: `scanner.py`'s directory walk now passes an `onerror`
  callback to `os.walk`. Directory-level scan errors (permission denied,
  removed mid-walk) are now reported explicitly as `ScanFailure` entries
  instead of being silently dropped — `os.walk` no longer silently skips
  an unreadable directory and its contents. The failure reuses the
  existing `ScanFailure`/`failed` pipeline, so it flows through the
  discovered/eligible/failed metrics with no changes to `diff.py`,
  `manifest.py`, or `cli.py`. 57 unit tests executed successfully (up
  from 54), including 3 new tests covering unreadable-directory
  detection, sibling-scan isolation, and deterministic repeat-run
  behavior.

## V1.1.1 status

Production V1.1 run already completed successfully (see below). V1.1.1
has not yet been executed against the real `01-Ingestion` — it has only
been validated by the unit test suite against synthetic directory
structures. The last real production run against `01-Ingestion` remains
the V1.1 run recorded below (`20260717T030748.563951Z-dfb7`).

## Validation results (production run 20260717T030748.563951Z-dfb7)

- Exit code: 0 (clean — zero failed files).
- Metrics invariants held: discovered = eligible + excluded
  (7,759 = 7,748 + 11); eligible = processed + failed (7,748 = 7,748 + 0);
  processed = new + modified + unchanged (7,748 = 4,864 + 6 + 2,878);
  hashes_recomputed + hashes_reused = processed (4,870 + 2,878 = 7,748).
- `document_manifest.jsonl` line count (7,748) matches `processed` exactly;
  every record passed required-field, `relative_path` uniqueness, and
  sort-order validation before publish.
- Atomic multi-artifact commit succeeded in the documented order: run
  history file first, document manifest second, run metadata (latest-run
  pointer) last.

## Current repository statistics (as of run 20260717T030748.563951Z-dfb7)

- Total cataloged documents: 7,748 (of 7,759 discovered; 11 excluded by
  policy; 0 failed).
- By knowledge source: OneDrive-Proposals 6,839 · OneDrive-Marketing 558 ·
  OneDrive-Portfolio 351.
- Top file types: .pdf 3,790 · .docx 2,154 · .xlsx 795 · .pptx 554 ·
  .xml 69 · .doc 65 · .csv 62 · .json 45 · .txt 36 · .md 34.
- This run's diff against the prior legacy manifest: 4,864 new · 6
  modified · 2,878 unchanged · 3,068 deleted.

## Next milestones

1. Initialize Git and create the first stable commit — the repository has
   no commit history yet; everything to date is untracked working state.
2. Create ADRs for: document identity and rename semantics (`relative_path`
   as path-stable, not rename-stable), the atomic multi-artifact publishing
   model, and the legacy schema (v1 → v2) migration policy.
3. Define the V1.2 scope for deterministic document-to-Markdown conversion.
4. Review the 3,068 `deleted` entries from the V1.1 production run to
   confirm they reflect legitimate OneDrive-side removals rather than a
   Knowledge Sync gap — V1.1 does not correlate renames, so a rename
   appears as one `deleted` entry plus one unrelated `new` entry.
5. Establish a recurring execution cadence for Knowledge Compiler (manual
   trigger for now; scheduling is out of scope until the platform owner
   approves an automation policy).
6. Define a run-history retention policy — no pruning is implemented yet,
   so `08-Indexes/Metadata/runs/` grows unbounded.
7. Design the `02-Curated` transformation stage that consumes the
   document manifest (normalization, enrichment) — the next layer in the
   architecture after Knowledge Compiler.
8. Design the `03-Knowledge` reusable-knowledge layer and its relationship
   to `02-Curated`.

## Current outputs (schema_version 2)

```text
08-Indexes/Metadata/document_manifest.jsonl
08-Indexes/Metadata/manifest_run_metadata.json
08-Indexes/Metadata/runs/run_20260717T030748.563951Z-dfb7.json
```
