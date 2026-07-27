# ADR-001 — Knowledge Representation for Curated Markdown

## Status

Accepted

## Date

2026-07-20 (revised 2026-07-20, accepted 2026-07-20, clarified 2026-07-20)

---

## Context

Knowledge Compiler V1.2.0 (Document Normalizer) is implemented, tested, and has
completed its first real production run: 179 text-native documents converted,
0 failed, 7,544 deferred, 25 unsupported, out of 7,748 total source documents
(run_id `20260720T030909.550868Z-bc40`).

Before V1.2.1 introduces PDF and DOCX converters — which will multiply the
volume of curated Markdown by orders of magnitude and copy whatever patterns
V1.2.0 established — a design review was performed against the actual V1.2.0
implementation (`converters.py`, `markdown_builder.py`, `curated_manifest.py`,
`normalizer_diff.py`) and one real converted file from the production run.

### Revision note

The design review's first pass proposed a broad set of forward-looking
schema and infrastructure decisions (a controlled document-type ontology, a
reserved embedding-manifest shape, per-converter structural/heading markers,
and groundwork explicitly framed around future chunking, embedding, and
Knowledge Graph construction). The platform owner corrected this: **V1.2.1A
must prioritize agent validation and practical retrieval quality over early
deep structuring.** This revision narrows the decision accordingly. The
review's factual findings below are unchanged; what changed is which of
them V1.2.1A actually acts on now versus defers.

### Current representation (as implemented and verified against the real run)

- **Identity**: `relative_path` (relative to `01-Ingestion`) is the sole
  identifier at every layer, including the curated manifest. It is
  path-stable, not rename-stable — a deliberate, documented, scoped trade-off
  in V1.1 for the scanning/hashing layer, but silently inherited by V1.2.0 as
  the *permanent* identity for curated Markdown.
- **Canonical Markdown**: one YAML front matter block
  (`schema_version`, `source_relative_path`, `source_extension`,
  `source_sha256`, `knowledge_source`, `converter_id`, `converter_version`,
  `source_metadata`) followed by a body.
  - `.md` sources: their own front matter is parsed into `source_metadata`;
    the body is passed through live, unfenced.
  - All seven other text-native types (`.txt`, `.json`, `.yaml`, `.sql`,
    `.py`, `.sh`, `.java`): the **entire file content is wrapped in a single
    fenced code block**, verbatim, regardless of length. Confirmed on the
    real sample (`Caso_Financiera.py.md`): a multi-hundred-line Python file
    is one opaque fence with no internal structure exposed to Markdown
    tooling.
- **Facets available today**: `knowledge_source` (three values —
  OneDrive-Proposals / OneDrive-Marketing / OneDrive-Portfolio) and
  `source_extension`. Nothing else.
- **Staleness/versioning contract**: `source_sha256` +
  `converter_id`/`converter_version` on the curated entry, `output_sha256` on
  the canonical Markdown — a clean, already field-tested invalidation signal
  (`converted_new` / `converted_stale` / `converted_stale_converter` /
  `unchanged`).
- **Cardinality**: exactly one source document produces exactly one curated
  Markdown file, always.

### Gaps identified

1. **No document title or heading anchor** in the rendered output. Noted as
   a retrieval-quality observation; V1.2.1A does not act on it (see
   Decision) — it is not a metadata field and introducing per-converter
   structural markers now would be exactly the kind of early deep
   structuring this revision avoids.
2. **Whole-file fenced wrapping erases all internal structure** for seven of
   eight text-native converters. Confirmed, unresolved, explicitly deferred
   by this revision until a concrete need is demonstrated through agent
   validation or summary work, rather than solved speculatively now.
3. **`source_metadata` conflates two different kinds of metadata**: raw,
   uncontrolled passthrough from whatever the source `.md` file's own front
   matter happened to contain, with no reserved place for anything AI Hub
   itself later derives about the document. Addressed narrowly in this
   revision (see `derived_metadata` below) — reserved, but constrained to
   stay empty or deterministic-only for now.
4. **No stable `document_id` independent of `relative_path`.** A rename
   today produces one `orphaned` curated entry plus one unrelated
   `converted_new` entry, even though `source_sha256` would prove it is the
   same content. Nothing correlates them. Addressed by this revision —
   this is the one identity-layer gap still judged cheap enough, and
   costly enough to defer, to act on now.
5. **No language tag**, despite the corpus being visibly multilingual
   (Spanish content confirmed in the real sample). Addressed by this
   revision, deterministic-only.
6. **No chunk-, embedding-, or graph-addressability hooks reserved
   anywhere.** Confirmed, and **explicitly out of scope for V1.2.1A** under
   this revision — reserving infrastructure for stages (chunking,
   embedding, Knowledge Graph) that are no longer the next milestone is the
   over-engineering this correction is meant to prevent.

---

## Decision

**V1.2.1A adopts a deliberately small, closed set of document-level fields
and explicitly excludes semantic enrichment work.** This replaces the
broader seven-point decision from the original review.

### Scope of the closed field list

The closed field list below constrains **canonical Markdown front matter —
semantic, document-level metadata only.** It does **not** constrain
operational manifest bookkeeping. Fields such as `output_relative_path`,
`output_sha256`, `first_seen_at`, `last_converted_at`, `run_id`, and other
run/status fields already used by the curated manifest and run metadata
(`curated_manifest.py`) may remain there freely — they describe the
pipeline's own state (what was written, when, by which run), not the
document's knowledge content, and are not subject to this ADR's field
closure.

### Closed field list

The only document-level fields permitted in the curated schema and canonical
Markdown front matter for V1.2.1A are:

- `document_id`
- `source_relative_path`
- `source_extension`
- `source_sha256`
- `knowledge_source`
- `document_type`
- `language`
- `converter_id`
- `converter_version`
- `source_metadata`
- `derived_metadata`

No other document-level field may be added under this ADR. Any additional
field (entities, relationships, summaries, embeddings references, chunk
references, structural/heading metadata, etc.) requires its own future
decision once a concrete, validated need exists.

### Field-specific decisions

1. **`document_id`** — a persistent identifier, independent of
   `relative_path`. Minted once at first-seen; carried forward across
   renames by matching `source_sha256` against orphaned curated entries
   during classification, rather than treating every rename as a brand-new
   document. This remains in scope because it is cheap now (179 documents)
   and the one gap that is categorically expensive to retrofit later,
   regardless of which downstream consumer eventually needs it.

   **Rename correlation tie-breaking**: if multiple orphaned previous
   entries share the same `source_sha256` (duplicate content under
   different historical paths), the `document_id` is reused from the
   orphaned entry whose `source_relative_path` is **lexicographically
   smallest**. This rule is chosen because it is deterministic, simple,
   and testable — no recency heuristic, no path-depth heuristic, no
   content inspection beyond the hash match already required.
2. **`source_extension`** — kept from the current V1.2.0 implementation.
   Although it is technically derivable from `source_relative_path`, it is
   retained as an explicit operational/search facet already in production
   use — removing an existing, working field is not part of this ADR's
   intent, which is to bound *new* additions, not to strip proven ones.
3. **`document_type`** — a **minimal, 1:1 mapping** from the existing
   `knowledge_source` value. No deeper taxonomy, no customer inference, no
   industry inference, no service inference, and no entity extraction of
   any kind. The complete mapping for V1.2.1A is:

   | `knowledge_source`   | `document_type` |
   |----------------------|------------------|
   | `OneDrive-Proposals`  | `proposal`       |
   | `OneDrive-Marketing`  | `marketing`      |
   | `OneDrive-Portfolio`  | `portfolio`      |
   | anything else         | `unknown`        |

   This is a lookup table, not a classifier — it must not grow branches,
   heuristics, or exceptions without a separate future decision. Invented
   categories such as "contract," "code_artifact," or "dataset" (part of
   the original review's over-engineered proposal) remain explicitly
   rejected.

   **Future `knowledge_source` values**: reaffirmed unchanged. Any
   `knowledge_source` value outside the three listed rows — including any
   new OneDrive sync category introduced later — falls to `unknown` under
   the table's existing "anything else" rule. This requires no new
   decision when it happens; it is already the defined behavior.
4. **`language`** — a simple, deterministic tag (e.g. ISO 639-1 code, or
   `und` when undetermined). Deterministic heuristic only; no new
   ML/AI dependency for language detection in V1.2.1A.

   **Migration/backfill**: existing curated manifest entries that predate
   this field (the 179 documents from the first production run) are
   backfilled with `language: und` during legacy manifest loading — no
   source content is re-read solely to backfill this field. For `new`,
   `stale`, or `stale_converter` conversions, `language` is computed
   deterministically from the source content at the time it is read.
   Concretely, this means the `CONVERTER_VERSION` bump that lands the
   fields in this ADR (see the closed field list) triggers
   `converted_stale_converter` for all 179 existing documents, and their
   `language` is recomputed from source content as part of that
   reconversion — so `und` backfill only ever applies transiently, between
   the schema-migration load and the next reconversion, never as a
   long-lived stored value for documents that have since been reconverted.
5. **`derived_metadata`** — a reserved field, distinct from `source_metadata`
   (which remains pure, uncontrolled passthrough of whatever the source
   document's own front matter contained). `derived_metadata` **must stay
   empty, or contain only deterministic, rule-based derivations, for now.**
   It must not contain AI-generated or agent-generated content of any kind
   at this stage. This keeps the passthrough/derived distinction available
   for later without pre-committing to what "derived" will eventually mean.

### Explicit exclusions for V1.2.1A

V1.2.1A **must not** implement:

- entity extraction
- relationship extraction
- semantic entity typing
- Knowledge Graph construction
- rich metadata enrichment of any kind

Summaries, abstracts, entities, relationships, semantic enrichment, and any
agent- or model-generated interpretation of a document belong to a later,
distinct enrichment layer — not to Knowledge Compiler, and not to V1.2.1A.
This keeps Knowledge Compiler inside Principle 4 (deterministic before AI):
everything it produces remains reproducible from source bytes plus a
versioned, rule-based converter, with nothing depending on a model's
judgment.

### Next milestone

**The next practical milestone after PDF/DOCX converters is document
summaries and agent validation — not Knowledge Graph construction.** Any
future work on chunking, embedding, or a Knowledge Graph is deferred until
agent validation and summary work demonstrate a concrete, specific need,
rather than being built speculatively ahead of that evidence.

---

## Alternatives considered

### Alternative A — Keep `relative_path` as the sole identity; reconcile renames later, whenever a downstream consumer needs it

Defer the identity problem entirely; reconcile renamed/moved documents
later using `source_sha256` matching, whenever something downstream first
needs stable identity.

Rejected: by the time any downstream consumer exists, it will already be
keyed off `relative_path`. Reconciliation becomes a migration across
whatever was built in the meantime, instead of a single field addition made
once, now, while only 179 curated documents exist. This is the one
exception this revision still makes to "avoid early investment" — identity
is judged different in kind from structuring/enrichment work because
every future consumer inherits it silently, without the chance to opt in.

### Alternative B — Continue whole-file fenced wrapping; defer all structural investment indefinitely

Make no changes to how converters render content; treat internal document
structure as entirely out of scope until a concrete consumer (chunker,
search UI) demands it.

**Adopted for V1.2.1A** (reversing the original review's rejection of this
alternative). The original review argued that deferring structure would be
expensive to retrofit at scale. That argument remains true in principle,
but the platform owner's correction takes priority: practical retrieval
quality and agent validation should drive when and how structure gets
added, not a speculative worst case. This is revisited if agent validation
or the summary milestone surfaces a concrete retrieval problem traceable to
missing structure.

### Alternative C — Keep a single `source_metadata` field for all metadata, source and derived alike

Simplest schema; avoids adding `derived_metadata` before it has a concrete
consumer.

Rejected: mixing user-authored, uncontrolled metadata with anything AI Hub
itself later derives makes it impossible to distinguish "what the source
claimed" from "what AI Hub concluded" without an ambiguous migration once
both exist in volume. Unlike the structural/enrichment work deferred above,
this is a single empty field reservation with no speculative design
attached to it — low cost, and it directly enables the "deterministic-only
for now" constraint to be enforced and audited later (anything found in
`derived_metadata` that isn't deterministic is a violation, by
construction).

### Alternative D — Defer all field additions, including `document_id`, until a concrete consumer exists

Add no fields at all in V1.2.1A; revisit everything, including identity,
once chunking, embedding, or graph work actually begins.

Rejected, narrowly: identity is treated as a special case (see Alternative
A) because it is inherited silently by everything built afterward, with no
opportunity for a later consumer to "opt out" of the path-based identity
mistake. Every other field this revision adds (`document_type`, `language`,
`derived_metadata`) is judged cheap enough, and clearly bounded enough by
the closed field list, not to constitute the kind of speculative
over-engineering this alternative is right to guard against.

### Alternative E (superseded) — The original review's broader decision: controlled document-type ontology, reserved embedding-manifest shape, per-converter structural markers, explicit Knowledge Graph groundwork

This was the original Decision in this ADR before revision.

Superseded by the platform owner's correction: prioritize agent validation
and practical retrieval quality over early deep structuring. Reserving
infrastructure (an embedding manifest, a detailed document-type ontology,
structural parsing per converter) for stages that are no longer the next
milestone is over-engineering relative to the corpus's actual current
needs. These may be revisited, individually, once summaries and agent
validation work make a concrete need visible — but they are not part of
V1.2.1A.

---

## Consequences

### Positive

- V1.2.1A stays small and shippable: eleven fields total (one of which,
  `source_extension`, already exists in production), with a hard boundary
  against speculative infrastructure for stages not yet prioritized.
- `document_id` still prevents silent duplication and orphaning of any
  future downstream consumer across the OneDrive renames/reorgs that are
  routine in this corpus, without requiring that consumer to exist yet.
- `document_type` is a fixed, four-branch lookup table keyed directly off
  `knowledge_source` — no ontology to design, review, or maintain, and no
  classification logic that could drift or need retraining.
- `derived_metadata`, reserved but empty/deterministic-only, avoids both
  premature ontology lock-in and the risk of AI-generated content leaking
  into what is supposed to be Knowledge Compiler's deterministic output.
- A clear, explicit boundary — summaries, entities, relationships, and
  semantic enrichment belong to a later layer — keeps Knowledge Compiler
  inside Principle 4 and gives the next milestone (summaries + agent
  validation) an unambiguous starting point instead of an implicit one.

### Negative

- The four schema-additive fields (`document_id`, `document_type`,
  `language`, `derived_metadata`) still force a `converter_version` bump
  and full reconversion of the 179 already-curated documents — this
  revision reduces *what* gets added, not the mechanical reconversion cost
  of adding it.
- Retrieval quality for large, opaque, fenced-code documents remains
  unaddressed and is now explicitly deferred rather than solved — accepted
  as a known, named gap rather than a silent one.
- If agent validation surfaces a concrete need for chunk-level structure or
  embeddings sooner than expected, that work starts from zero rather than
  from infrastructure reserved in advance — a deliberate trade against the
  original review's more defensive posture.

---

## Future implications

- **Chunking, embedding, Knowledge Graph**: explicitly deferred. No
  `chunker_id`/`chunker_version` pair, no embedding manifest, and no graph
  node/edge model are decided by this ADR. If and when any of these become
  the actual next milestone (which this ADR states is *not* the case —
  document summaries and agent validation come first), a separate decision
  should be made at that time, informed by what agent validation actually
  found, rather than by this review's earlier speculation.
- **Document summaries + agent validation (the actual next milestone)**:
  this ADR does not design that work, but notes that `document_id`,
  `document_type`, `language`, and the `source_metadata`/`derived_metadata`
  split are the minimum identity and provenance surface it will need —
  summaries themselves are explicitly excluded from Knowledge Compiler's
  own output (per the exclusions above) and belong to whatever component
  performs that later enrichment.
- **Semantic search**: remains limited to the three `knowledge_source`
  values plus whatever `document_type` derives from the existing catalog.
  Richer facets are not pursued speculatively; they wait for evidence from
  agent validation that they are actually needed.
- **Omnigent integration**: the file-based, path-addressable curated output
  remains a good fit for Omnigent's OS-level tools. Any future retrieval
  surface should still return the lineage fields already adopted here
  (`document_id`, `source_relative_path`, `source_sha256`,
  `converter_version`) as a matter of course, matching the traceability
  already required by Principle 3 — this expectation is unchanged by the
  narrower scope.
