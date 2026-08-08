# CURRENT STATE

## Last updated

2026-07-27

## Current milestone

Knowledge Compiler V1.1 (Incremental Engine) implemented, unit-tested, and
successfully executed in production against the real `01-Ingestion`
repository. V1.1.1 (directory-level scan-error patch) completed and
unit-tested; not yet executed against the real `01-Ingestion`.

Knowledge Compiler V1.2.0 (Document Normalizer) is **formally closed**:
implemented, unit-tested (132 tests, all synthetic fixtures), and
successfully executed for the first time against the real repository on
branch `feature/document-normalizer-v1.2` (run_id
`20260720T030909.550868Z-bc40`, initial mode, exit code 0 / clean). Not
yet merged to `main`.

Knowledge Compiler V1.2.1A (Document Identity Metadata) is **formally
closed**: implemented, unit-tested (174 tests, all passing, all synthetic
fixtures), and successfully executed against the real repository on
branch `feature/document-normalizer-v1.2.1` (run_id
`20260727T194202.584265Z-9562`, incremental mode, exit code 0 / clean, all
179 text-native documents reclassified as `converted_stale_converter` and
reconverted with zero failures). See "Validation results (V1.2.1A
production run)" below. ADR-001 (Knowledge Representation) is **Accepted**.
Not yet merged to `main`.

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
- Knowledge Compiler V1.2.0 (Document Normalizer) implemented: normalizer
  state engine, converter router, deterministic canonical Markdown
  builder, curated manifest, normalizer run metadata and immutable run
  history, `normalize` CLI command (`knowledge-compiler normalize`,
  dispatched non-destructively alongside the original scan command).
  Text-native converters implemented for `.md .txt .json .yaml .sql .py
  .sh .java`; PDF/Office/HTML/OCR/image/email/notebook/diagram/
  legacy-office/multimodal/structured-data formats are recognized as
  `deferred` (roadmap, not implemented) rather than `unsupported`. `.csv`
  and `.xml` were moved from text-native to `deferred` on 2026-07-20 --
  both are structured-data formats, not free text, and are now reserved
  for a future Structured Data Compiler rather than being wrapped as
  opaque fenced text. Consumes the V1.1 document manifest as its source
  inventory and never rescans `01-Ingestion`.
  State classification (`converted_new`, `converted_stale`,
  `converted_stale_converter`, `unchanged`, `unsupported`, `deferred`,
  `failed`) is mutually exclusive; `orphaned` previous-curated entries
  (source deleted upstream) are tracked separately and their outputs are
  left untouched. Degraded runs (document-level failures) still publish
  all three curated artifacts and exit 2; only structural failures
  (missing/corrupt required manifests, metrics-invariant violation,
  publish failure) abort without advancing the curated manifest, exit 1.
  `--dry-run` invokes converters in-memory but writes nothing, including
  temporary artifacts. PyYAML added as the only new runtime dependency.
  62 new unit tests added (up from 57 to 119 total; 5 more added for the
  `.csv`/`.xml` scope revision and degraded-run diagnostics work brought
  the suite to 132), all against synthetic temporary fixtures -- no real
  corpus processing during implementation.
- Degraded-run diagnostics added to the normalizer: sanitized, path-free
  failure reasons, a "Failures" section printed by the CLI (relative
  path, converter, exception class, reason) whenever `failed > 0` in
  either dry-run or real-run mode, and identical per-document failure
  detail persisted in both `normalizer_run_metadata.json` and the
  immutable run-history file.
- First real V1.2.0 production run executed against the real repository
  (run_id `20260720T030909.550868Z-bc40`, initial mode, exit code 0 /
  clean). See "Validation results (V1.2.0 production run)" below.
- Knowledge Compiler V1.2.1A (Document Identity Metadata) implemented:
  `document_id` (stable per-document UUID4, minted once and carried
  forward across reconversions), `document_type` (derived 1:1 from
  `knowledge_source` via `document_type.py`), and `language` (computed
  from source content via a lightweight heuristic in `language.py`,
  backfilled as `"und"` for legacy manifest entries, carried forward
  unchanged on `unchanged` / `failed`-with-previous-entry / `orphaned`
  states, and recomputed on `converted_new` / `converted_stale` /
  `converted_stale_converter`) are now wired into `CuratedDocumentMetadata`
  and into the canonical Markdown front matter, alongside a new
  `derived_metadata` field (always present, always `null` -- reserved for
  future AI/semantic enrichment, no AI interpretation performed in this
  version). `CONVERTER_VERSION` bumped `1.0.0` -> `1.1.0` (additive fields
  only; no converter behavior changed). 42 new/updated unit tests added
  (132 -> 174 total), all against synthetic fixtures. Explicitly out of
  scope for this batch: PDF, DOCX, rename correlation, summaries,
  embeddings, Knowledge Graph, entity extraction, relationship extraction.
  `01-Ingestion` was not modified.
- First real V1.2.1A production run executed against the real repository
  (run_id `20260727T194202.584265Z-9562`, incremental mode, exit code 0 /
  clean). See "Validation results (V1.2.1A production run)" below.

## Validation results (V1.2.1A production run 20260727T194202.584265Z-9562)

- Exit code: 0 (clean — zero failed files).
- Ran against the same real repository inventory as the V1.2.0 run:
  `source_total=7748 text_native=179 deferred=7544 unsupported=25`.
- All 179 previously curated documents reclassified as
  `converted_stale_converter` (0 `converted_new`, 0 `converted_stale`, 0
  `unchanged`) because `CONVERTER_VERSION` changed `1.0.0` -> `1.1.0`
  while every source `sha256` was unchanged — the documented
  converter-version-precedence path in the state machine. `failed=0`,
  `orphaned=0`.
- All 179 canonical Markdown files under `02-Curated/Markdown/` were
  rewritten with the new front matter, each now including `document_id`,
  `document_type`, `language`, and `derived_metadata` (null) alongside
  the preserved `schema_version`, `source_relative_path`,
  `source_extension`, `source_sha256`, `knowledge_source`,
  `converter_id`, `converter_version: 1.1.0`, and `source_metadata`
  fields.
- `document_normalizer_manifest.jsonl` (179 entries), updated
  `normalizer_run_metadata.json`, and a new immutable run-history file
  (`02-Curated/Metadata/runs/run_20260727T194202.584265Z-9562.json`) were
  all written and are mutually consistent (same run_id and metrics in
  both the run-metadata pointer and the run-history record); the prior
  V1.2.0 run-history file was preserved, not overwritten.
- `01-Ingestion` was not modified by this run (confirmed via `git status`/
  `git diff --stat` scoped to that path: empty).
- Full unit test suite: `Ran 174 tests ... OK` (`.venv/bin/python -m
  unittest discover -s tests`), run immediately before formal closure.

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

## Validation results (V1.2.0 production run 20260720T030909.550868Z-bc40)

- Exit code: 0 (clean — zero failed files).
- Metrics invariants held: source_total = text_native + deferred +
  unsupported (7,748 = 179 + 7,544 + 25); text_native = converted_new +
  converted_stale + converted_stale_converter + unchanged + failed
  (179 = 179 + 0 + 0 + 0 + 0).
- 179 text-native documents converted (`converted_new`), 0 failed,
  0 unchanged/stale (first run, no previous curated manifest), 0
  orphaned; 7,544 deferred (PDF/Office/HTML/OCR/image/email/notebook/
  diagram/legacy-office/structured-data families); 25 unsupported.
- `document_normalizer_manifest.jsonl` line count (179) matches
  `converted_new` exactly.
- Curated manifest, `normalizer_run_metadata.json`, and the immutable
  run-history file (`02-Curated/Metadata/runs/
  run_20260720T030909.550868Z-bc40.json`) were all created and are
  mutually consistent (same run_id and metrics in both the run-metadata
  pointer and the run-history record).
- 179 canonical Markdown files written under `02-Curated/Markdown/`,
  matching the curated manifest count exactly.
- `01-Ingestion` was not modified by this run (the normalizer only reads
  it and only writes under `02-Curated`).

## Next milestones

1. Merge `feature/document-normalizer-v1.2` to `main` and tag the release
   now that V1.2.0 is implemented, tested, and has a clean real-corpus
   run on record.
2. Create ADRs for: document identity and rename semantics (`relative_path`
   as path-stable, not rename-stable), the atomic multi-artifact publishing
   model, the legacy schema (v1 → v2) migration policy, and the
   normalizer's deferred-vs-unsupported extension classification.
3. Review the 3,068 `deleted` entries from the V1.1 production run to
   confirm they reflect legitimate OneDrive-side removals rather than a
   Knowledge Sync gap — V1.1 does not correlate renames, so a rename
   appears as one `deleted` entry plus one unrelated `new` entry.
4. Review the 25 `unsupported` documents from the V1.2.0 production run
   to confirm none of them should instead be added to `DEFERRED_EXTENSIONS`
   as a recognized future-roadmap format.
5. Establish a recurring execution cadence for Knowledge Compiler (manual
   trigger for now; scheduling is out of scope until the platform owner
   approves an automation policy).
6. Define a run-history retention policy — no pruning is implemented yet,
   so `08-Indexes/Metadata/runs/` and `02-Curated/Metadata/runs/` both
   grow unbounded.
7. Design PDF, Office, and other deferred-format converters (including a
   Structured Data Compiler for `.csv`/`.xml`) as their own Knowledge
   Compiler versions -- V1.2.0 only covers text-native formats.
8. Design the `03-Knowledge` reusable-knowledge layer and its relationship
   to `02-Curated`.

## Current outputs (schema_version 2)

```text
08-Indexes/Metadata/document_manifest.jsonl
08-Indexes/Metadata/manifest_run_metadata.json
08-Indexes/Metadata/runs/run_20260717T030748.563951Z-dfb7.json
```

## V1.2.0 / V1.2.1A outputs (curated_manifest schema_version 1, real runs on record)

```text
02-Curated/Markdown/<mirrored source path>/<original filename>.md  (179 files, front matter upgraded by V1.2.1A)
02-Curated/Metadata/document_normalizer_manifest.jsonl
02-Curated/Metadata/normalizer_run_metadata.json
02-Curated/Metadata/runs/run_20260720T030909.550868Z-bc40.json  (V1.2.0, initial)
02-Curated/Metadata/runs/run_20260727T194202.584265Z-9562.json  (V1.2.1A, converted_stale_converter)
```

## Development environment (Python) — added 2026-08-08

OneDrive sync errors were observed on Python virtual-environment artifacts
(`.venv/.lock`, `*.dist-info/REQUESTED`) inside the OneDrive-synced repo.
Root cause: a `.venv/` had been created directly under
`00-System/KnowledgeCompiler/` inside OneDrive. It has been removed; the
environment now lives outside OneDrive.

**Rule: `.venv` must never live inside this OneDrive-synced repo.**

- Recommended external venv path:
  `/Users/carlosczg/LocalDev/venvs/knowledge-compiler`
- Create/install (uv preferred):
  ```bash
  uv venv /Users/carlosczg/LocalDev/venvs/knowledge-compiler
  cd 00-System/KnowledgeCompiler
  uv pip install --python /Users/carlosczg/LocalDev/venvs/knowledge-compiler/bin/python -e .
  ```
- Run KnowledgeCompiler tests using the external venv:
  ```bash
  cd 00-System/KnowledgeCompiler
  /Users/carlosczg/LocalDev/venvs/knowledge-compiler/bin/python -B -m unittest discover -s tests -v
  ```
- Run AgentValidation tests (plain Python is sufficient; no extra deps):
  ```bash
  PYTHONPATH=00-System/AgentValidation/src \
    /Users/carlosczg/LocalDev/venvs/knowledge-compiler/bin/python -B -m unittest discover -s 00-System/AgentValidation/tests -v
  ```
  (`-B` skips writing `__pycache__/*.pyc` bytecode files, since even a
  correctly-external venv's interpreter still writes bytecode caches next to
  the source files it imports — which live inside the OneDrive-synced repo.)
- `.gitignore` already covers `**/.venv/`, `__pycache__/`, `.pytest_cache/`,
  `.ruff_cache/`, `.mypy_cache/`, `dist/`, `build/`, `*.egg-info/`,
  `*.dist-info/` — but gitignore does not stop OneDrive from syncing stray
  files that exist on disk, so the real fix is: never create the venv inside
  the repo in the first place.
