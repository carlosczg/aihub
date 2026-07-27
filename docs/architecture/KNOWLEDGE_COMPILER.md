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

---

## V1.2.0 — Document Normalizer

### Purpose

The normalizer is the second deterministic stage of Knowledge Compiler. It
consumes the V1.1 document manifest as its source inventory (it never
rescans `01-Ingestion` itself) and converts text-native documents into
canonical, traceable Markdown under `02-Curated`.

### Command

```text
knowledge-compiler normalize [--root PATH] [--dry-run]
```

An optional leading `scan` on the original command is accepted for
symmetry (`knowledge-compiler scan ...`) but was never required; every
existing invocation shape continues to work unchanged.

### Text-native converters (V1.2.0 scope)

`.md` `.txt` `.json` `.yaml` `.sql` `.py` `.sh` `.java`

All eight share one converter identity, `converter_id = "text_native"`,
versioned independently of the package (`CONVERTER_VERSION` in
`converters.py`, bumped `1.0.0` -> `1.1.0` in **V1.2.1A** for the additive
front-matter identity fields below; no converter behavior changed).
`.md` sources are passed through with their own leading
YAML front matter (if any) parsed out and preserved under
`source_metadata`; the other seven are wrapped verbatim in a fenced code
block tagged with a language matching the extension. Fence length is
computed to exceed the longest backtick run already present in the
content, so fenced content can never break out of its block.

`.csv` and `.xml` are deliberately **not** registered as text-native:
both are structured-data formats rather than free text, and are deferred
to a future **Structured Data Compiler** instead of being wrapped as
opaque fenced text.

PDF, legacy and modern Office formats, images/OCR, HTML, email,
notebooks, diagram formats, and structured data (`.csv`, `.xml`) are
recognized but deliberately **deferred** — planned for a future
Knowledge Compiler version, not implemented here. Anything else is
**unsupported**. No PDF, Office, HTML, OCR, image, email, notebook,
diagram, legacy-office, multimodal, or structured-data conversion module
exists in V1.2.0.

### Canonical Markdown contract

Every converted document gets exactly one AI Hub YAML front matter block
(`schema_version`, `document_id`, `document_type`, `source_relative_path`,
`source_extension`, `source_sha256`, `knowledge_source`, `language`,
`converter_id`, `converter_version`, `source_metadata`, `derived_metadata`)
followed by the body. `document_id`, `document_type`, `language`, and
`derived_metadata` were added in **V1.2.1A**:

- `document_id` — a stable per-document UUID4, minted once on first
  conversion (or backfilled once for legacy curated-manifest entries) and
  carried forward unchanged on every subsequent run regardless of
  reconversion.
- `document_type` — derived 1:1 from `knowledge_source` via a fixed
  lookup table (`document_type.py`); recomputed on every reconversion,
  carried forward otherwise.
- `language` — computed from source content with a lightweight heuristic
  (`language.py`) on `converted_new` / `converted_stale` /
  `converted_stale_converter`; carried forward unchanged on `unchanged`,
  `failed`-with-previous-entry, and `orphaned` states; backfilled as
  `"und"` for legacy curated-manifest entries missing the field until
  their next reconversion.
- `derived_metadata` — always present, always `null` in V1.2.1A. Reserved
  for future AI/semantic enrichment; this version performs no AI
  interpretation or content analysis of any kind.

The front matter deliberately carries **no timestamp and no run
identifier** — output is byte-identical for the same source bytes and the
same converter version, regardless of when or in which run it was
produced. Body content and line endings after any detected source front
matter are preserved verbatim.

### State machine

Per-document classification against the previous curated manifest is
mutually exclusive:

- `converted_new` — no previous curated entry.
- `converted_stale_converter` — `registered_converter_version !=
  recorded_converter_version` (checked before source-hash staleness: a
  converter upgrade is a structural, repository-wide reason to reconvert).
- `converted_stale` — source `sha256` changed since the last conversion.
- `unchanged` — neither the source hash nor the converter identity
  changed; the previous curated entry is carried forward and the output
  file is never rewritten.
- `unsupported` / `deferred` — see above; no curated entry is produced.
- `failed` — the document could not be read, decoded as UTF-8, or
  converted.

`orphaned` is a separate dimension, not part of the mutually exclusive
set above: previous curated entries whose source document no longer
appears in the current V1.1 manifest. They remain recorded in the curated
manifest and their output files are left untouched (never rewritten,
never deleted).

### Degraded runs

A document-level failure does not stop the run: successful conversions
still get new curated entries, unchanged entries are still carried
forward, a failed document with a previous curated entry keeps that
entry, and a failed document without one simply gets no current entry.
Run history, the curated manifest, and run metadata are still published.
Exit code is `2` (degraded) whenever any document-level failure occurred.

Only structural failures abort the run without advancing the curated
manifest (exit `1`): a missing or invalid `aihub.json`, a missing or
corrupt V1.1 source manifest, a corrupt previous curated manifest, a
metrics-invariant violation, or a manifest-publication failure. There is
no `--full` recovery flag for the curated manifest in V1.2.0 — a corrupt
curated manifest always aborts.

### `--dry-run`

Converters may still be invoked (so conversion failures are visible in
the reported metrics) but nothing is written to disk — not the curated
manifest, not run metadata, not run history, and not a single Markdown
output file or temporary artifact.

### Output layout

```text
02-Curated/Markdown/<mirrored source path>/<original filename>.md
02-Curated/Metadata/document_normalizer_manifest.jsonl
02-Curated/Metadata/normalizer_run_metadata.json
02-Curated/Metadata/runs/run_<run_id>.json
```

`02-Curated/Documents`, `02-Curated/PDFs`, `02-Curated/Images`, and
`02-Curated/OCR` remain unused in V1.2.0.

### Metrics invariants

```
source_total = text_native + deferred + unsupported
text_native  = converted_new + converted_stale + converted_stale_converter
               + unchanged + failed
```

`orphaned` is reported alongside these but is not part of either
invariant, since it counts previous curated entries rather than documents
in the current V1.1 manifest.