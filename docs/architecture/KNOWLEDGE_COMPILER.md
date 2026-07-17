# Knowledge Compiler

## Purpose

Knowledge Compiler is the deterministic processing component of AI Hub.

Its purpose is to transform the document inventory stored in `01-Ingestion` into traceable, reproducible technical artifacts prepared for future curation, search, and semantic enrichment stages.

Knowledge Compiler is independent from Omnigent and from any AI model.

---

## Location

The component is located at:

```text
00-System/KnowledgeCompiler/
```

---

## V1.1 — Incremental Engine

### Identifier

`relative_path` (relative to `01-Ingestion`) is the document identifier. It is
**path-stable, not rename-stable**: moving or renaming a file produces one
`deleted` entry at the old path and one unrelated `new` entry at the new
path. Rename correlation is deliberately out of scope for V1.1.

### Manifest schema (schema_version 2)

`document_manifest.jsonl` adds two fields to the V1 record, both additive:

- `first_seen_at` — run in which this path was first observed.
- `last_verified_at` — run in which the SHA-256 was last actually (re)computed,
  as opposed to reused from a previous run.

A legacy schema_version 1 manifest still loads: both fields are backfilled to
the current run's timestamp, and the migration run proceeds as a normal
incremental comparison against the legacy hashes/paths. True historical
first-seen dates for pre-existing documents are unrecoverable.

### Run metrics

Every run reports, and validates before publishing, these counts and their
invariants:

```
discovered = eligible + excluded
eligible   = processed + failed
processed  = new + modified + unchanged   (excludes failed by definition)
hashes_recomputed + hashes_reused = processed
```

- `excluded` — files skipped by policy (dotfiles, ignored filenames). Never
  mixed with `failed`.
- `failed` — files that could not be stat'd or hashed this run (broken
  symlink, permission error, race-condition deletion). The previous manifest
  entry, if any, is carried forward unchanged, and the run history record
  notes whether it was preserved.
- `deleted` — previous-manifest paths not seen this run. A `failed` path is
  never counted as `deleted`.

### Exit codes

`0` clean · `1` hard stop, nothing written (corrupt manifest without
`--full`, config/ingestion-root errors, staging validation failure) · `2`
completed but degraded (`failed > 0`).

### `--full`

Forces every eligible file's hash to be recomputed. Classification
(new/modified/unchanged) is still derived by comparing against the previous
manifest — `--full` never treats an existing path as unconditionally new.
It is also the required flag to recover from a corrupt previous manifest.

### `--dry-run`

Reports the full metrics summary and writes **no files at all** — no
manifest, no run metadata, and no run-history entry under `runs/`.

### Corrupt previous manifest

A missing manifest is a valid first-run state. A present-but-unparseable
manifest stops the run (exit 1) with an actionable message unless `--full`
is passed, in which case the invalid file is copied aside to
`document_manifest.jsonl.corrupt-<run_id>` before the run proceeds as a full
recovery run.

### Atomic multi-artifact commit

Each run stages all three artifacts (document manifest, run metadata,
`runs/run_<run_id>.json`) as temp files in their target directories,
validates every one of them, and only then publishes via `os.replace()` — in
the order: run-history file first, document manifest second, run metadata
last (the "latest committed run" pointer). If staging or validation of any
artifact fails, none of the three final targets are changed. Filesystem
operations across multiple files are not fully transactional — a crash
between two `os.replace()` calls can still leave the three artifacts
momentarily inconsistent with each other — but this staging and ordering
minimizes the window and severity: the history file is self-contained and
safe to appear alone; the document manifest (what future runs diff against)
is only replaced once fully valid; and the pointer is only updated after the
state it points to already exists.

### Run history

Every non-dry-run execution writes exactly one new, immutable file under
`08-Indexes/Metadata/runs/`. Run IDs use microsecond UTC timestamps plus a
random suffix and are checked for collisions before use. No retention or
pruning is implemented yet — all run-history files are kept indefinitely.