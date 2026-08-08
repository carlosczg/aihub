# Agent Validation (V1.3)

## What this is

An **experimental validation harness** for asking real questions against the
existing curated corpus produced by the Knowledge Compiler, and getting back a
ready-to-paste context bundle an AI agent can answer from — with citations.

It exists to validate, with real questions against the real 179-file curated
corpus, whether the Knowledge Compiler's output (`02-Curated/Metadata/
document_normalizer_manifest.jsonl` + `02-Curated/Markdown/`) is actually
usable as grounding material for an agent, before any semantic/embedding
layer is built on top of it.

## What this does NOT do

- No embeddings, no vector database, no similarity math of any kind.
- No LLM API calls inside the tool itself. The CLI only selects candidates and
  formats a context bundle; answering the question is left to whatever agent
  the bundle is pasted into.
- No summaries, no entity extraction, and no Knowledge Graph construction or
  traversal of any kind. V1.3 only selects and returns raw candidate metadata
  plus Markdown content -- it does not derive, summarize, or link anything.
- No aggregation or counting. V1.3 has no concept of "how many" or "per
  knowledge_source/language" -- see "Scope (V1.3)" below.
- No writes to `02-Curated/` or to the Knowledge Compiler's manifests. This
  tool is a strictly read-only consumer of Knowledge Compiler output.
- No dependency on the `knowledge_compiler` package. The repo-root discovery
  pattern (`aihub.json` walk-up) is intentionally duplicated locally in
  `src/agent_validation/cli.py` rather than imported, so this tool stays fully
  decoupled and can be deleted without touching Knowledge Compiler.

Candidate selection is entirely deterministic and explainable: metadata
filtering on known field values mentioned in the question, then keyword/token
overlap scoring against file paths and Markdown body text, with a documented
tie-break rule. See "How selection works" below.

## Layout

```text
00-System/AgentValidation/
  README.md
  questions.md          -- the 10 approved V1.3 validation questions + results table
  src/agent_validation/
    manifest_loader.py   -- loads the curated manifest JSONL (the catalog; never rescans disk)
    candidate_selector.py -- deterministic filtering + keyword ranking
    cli.py                -- argparse CLI, context-bundle formatting
  tests/
    test_manifest_loader.py
    test_candidate_selector.py
  results/               -- gitignored; run logs land here (see below)
```

## How selection works

1. **Metadata filters** — if the question text literally mentions a value
   that matches a known `document_type`, `knowledge_source`, `language`, or
   `source_extension` from the loaded manifest (case-insensitive, word-bounded
   match — e.g. `.py` or `proposal`), the candidate pool is narrowed to
   entries matching every field that had a mention. If no known value is
   mentioned, the full manifest is the candidate pool.
2. **Keyword/token overlap** — the question and each entry's `relative_path`
   / `output_relative_path` / curated Markdown body are tokenized (lowercased,
   punctuation stripped, stopwords dropped) and scored by the size of the
   token intersection.
3. **Deterministic ranking** — sorted by score descending; ties are broken by
   `relative_path` ascending, so identical input always produces identical
   output order.
4. **Cap** — results are capped to `MAX_CANDIDATES` (8).
5. **No candidates** — if every entry scores zero, the selector returns the
   explicit `NoCandidatesFound` sentinel (not an empty list), and the CLI
   prints that fact instead of an instruction block implying sources exist.

## Scope (V1.3): what kinds of questions this answers

V1.3 is a **deterministic retrieval harness**, not a general question-answering
system. It is good at *retrieval-style* questions -- "find / summarize /
describe X" -- where keyword/token overlap against paths and Markdown bodies
can locate the right document(s). Real-corpus smoke testing (see
`questions.md`) confirms this works well: e.g. `Caso_Financiera.py` correctly
ranks #1 for "Summarize what Caso_Financiera.py does."

**Aggregation/counting questions are out of scope for V1.3.** Questions like
"How many curated documents exist per knowledge_source and language?" cannot
be answered correctly by keyword-overlap candidate selection -- there is no
aggregation/counting capability in the selector, so it returns a small,
arbitrary-looking sample of the manifest rather than true totals. For these
questions, either answer manually from the manifest
(`02-Curated/Metadata/document_normalizer_manifest.jsonl`, e.g. with `jq` /
`wc -l` / a one-off script) or treat proper aggregation support as a candidate
V1.3.1/V1.4 feature. Do not present V1.3's candidate bundle as a valid answer
to an aggregation question.

**Low-score candidates are an abstention signal.** When every returned
candidate scores at or near the minimum (1, matched only on a generic token),
that is a strong hint the corpus does not actually contain material on the
topic -- treat it as grounds to abstain ("the corpus does not appear to
address this") rather than answer from weak/incidental matches. This behavior
was validated against a negative-control question (GDPR / parental-leave
policy, see `questions.md` #9): all returned candidates scored 1 on the
generic token "policy" only, and the correct response is "not found in the
corpus," not a guess.

## Running the CLI

The tool is a plain package under `src/`, run via `python -m agent_validation`
with `PYTHONPATH` pointed at that `src/` directory. From the AI Hub repo root:

```bash
PYTHONPATH=00-System/AgentValidation/src python3 -m agent_validation ask \
  "What proposals relate to financial analytics?"
```

By default `--manifest` and `--markdown-root` resolve relative to `--root`
(which itself defaults to the current working directory, walking up to find
`aihub.json` — mirroring the pattern in
`00-System/KnowledgeCompiler/src/knowledge_compiler/config.py`'s
`find_repo_root`, duplicated locally rather than imported):

- `--manifest` defaults to `<root>/02-Curated/Metadata/document_normalizer_manifest.jsonl`
- `--markdown-root` defaults to `<root>/02-Curated/Markdown`

Both can be overridden explicitly, which also skips the `aihub.json` lookup
entirely:

```bash
PYTHONPATH=00-System/AgentValidation/src python3 -m agent_validation ask \
  "What proposals relate to financial analytics?" \
  --manifest /path/to/document_normalizer_manifest.jsonl \
  --markdown-root /path/to/02-Curated/Markdown
```

`--root`, `--manifest`, and `--markdown-root` must come after `ask` (they are
registered on the `ask` subcommand, not the top-level parser).

Output is a context bundle: the question, each ranked candidate's metadata
(`document_id`, `source_relative_path`, `knowledge_source`, `document_type`,
`language`, `source_sha256` short form, `converter_version`,
`output_relative_path`) plus its full Markdown content, and an instruction
block telling the consuming agent to answer only from the provided sources
and cite claims inline as `[1]`, `[2]`, etc.

## Where results get recorded

Run logs (raw CLI output, agent answers, pass/fail notes) go under
`results/`, which is gitignored (an empty `.gitkeep` keeps the directory
itself tracked). `questions.md` holds the canonical results table.

## Running the tests

```bash
PYTHONPATH=00-System/AgentValidation/src python3 -m unittest discover \
  -s 00-System/AgentValidation/tests -v
```

Tests use only small synthetic fixture manifests and fixture Markdown files
built in-memory/tempdir — zero dependency on the real `02-Curated` corpus.
