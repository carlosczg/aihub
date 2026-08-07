# V1.3 Validation Questions

These are the 10 validation questions approved for the AgentValidation experimental
validation harness. Each is run through `python -m agent_validation ask "<question>"`
against the real curated corpus, and the resulting context bundle is handed to an
agent that must answer using only the provided sources.

## Criteria

- **Groundedness** — every factual claim in the agent's answer is directly
  supported by content present in the cited source(s), not by the model's prior
  knowledge.
- **Citation completeness** — every claim is attributed inline to a candidate
  number (`[1]`, `[2]`, ...) that actually contains the supporting content.
- **Candidate relevance** — the ranked candidates returned by the selector are
  plausibly on-topic for the question, given only metadata filters and keyword
  overlap (no embeddings, no semantic search).
- **Correct abstention** — when the corpus genuinely does not contain an answer,
  the agent says so explicitly instead of guessing or falling back to general
  knowledge. This is what question 9 (a negative control) is designed to test.
- **Determinism** — running the same question against the same manifest and
  markdown root twice produces the same candidates, in the same order.

## Questions

1. What proposals or portfolio items relate to financial/analytics engagements
   (e.g. `Caso_Financiera`)?
2. Summarize what `Caso_Financiera.py.md` does, citing its exact
   `source_relative_path` and `document_id`.
3. How many curated documents exist per `knowledge_source`, and what languages
   do they use?
4. Find any deployment/DevOps scripts in the corpus and describe what they do.
5. What does the Codex/GitHub/VS Code guide recommend, and is it written in
   Spanish or English?
6. Is there any font-licensing or brand-typeface guidance in the corpus?
7. What's in the largest curated file, and what kind of data does it represent?
8. Summarize the analytics-related proposals and list their `document_id`
   values.
9. What does the corpus say about GDPR compliance / parental-leave policy?
   (expected: "not found" — negative control)
10. Which curated documents are still `language: und`, and what do they have
    in common?

## Results

| Question # | Question | PASS/PARTIAL/FAIL | Notes |
|---|---|---|---|
| 1 | Financial/analytics engagements | PARTIAL | Real-corpus run (see README/report) returns 8 `OneDrive-Proposals` Python scripts under "Speech Analytics" (score 3: `analytics`/`items`/`proposals`), all plausibly on-topic. It does NOT surface `Caso_Financiera.py` specifically -- that file only scores 1 (`proposals`) since its path uses Spanish "Propuestas Analitica" rather than the literal token "analytics", so naive keyword overlap outranks it. Documented limitation of no-stemming/no-translation matching, not a bug. |
| 2 | Summarize `Caso_Financiera.py.md` | PASS | Question text contains the exact filename, so the selector's naive token overlap puts the correct file at rank 1 with 9 matched tokens (unlike Q1's natural-language phrasing). Agent answer fully grounded and cited to [1]; determinism confirmed identical across two runs. |
| 3 | Documents per `knowledge_source` / languages | PARTIAL | Aggregation-style question the selector isn't built for: only 8 of 179 docs surface (keyword overlap with the question's own metadata-field wording), covering all 3 `knowledge_source` values but drastically undercounting and missing the `und` language entirely (ground truth: Proposals 170 (es108/und47/en15), Portfolio 6, Marketing 3). Agent correctly abstained from stating totals rather than guessing -- correct abstention, but candidate relevance fails for this question class. Likely needs a separate manifest-aggregation subcommand in V1.4, not a ranking fix. |
| 4 | Deployment/DevOps scripts | PASS | 5 of 8 candidates genuinely on-topic (GCP deployment README + 4 shell scripts for Cloud Run/Scheduler deploy); 3 of 8 are keyword-overlap false positives (font license files matched on "scripts", a dev-tools guide matched on "describe"). True positives still correctly identified and described; agent answer fully grounded and cited, excluded the false positives. Noise ratio (~38%) worth tracking. |
| 5 | Codex/GitHub/VS Code guide, language | PASS | Question contains distinctive title tokens (`codex`/`github`/`vs`/`code`/`guide`), so the target `GUIA_CODEX_GITHUB_VSCODE_ZAT.md` ranks first with 5 matched tokens despite noise (font-license false positives) filling out the rest of the pool. Agent answer fully grounded, correctly identifies `language: es`, cites recommendations to [1]. |
| 6 | Font-licensing / brand-typeface guidance | PASS | Selector found exactly 5 candidates (below the 8 cap): 3 genuinely on-topic (Hijrnotes font license notice, 2 copies of SIL Open Font License for Montserrat), 2 false positives from incidental "font" substring match in Tealium diagram JSON files. Agent answered "yes, licensing material exists" grounded in [1][2][5], correctly noted no dedicated brand-typeface style guide was found (partial, appropriate abstention) and excluded the JSON false positives. |
| 7 | Largest curated file | FAIL | Selector has no size concept: all 8 candidates are generic `.py`/`.sh` scripts tied on the tokens "data"/"file", tie-broken alphabetically. The actual largest file (`PowerBIPerformanceData 1.json.md`, ~1.45MB, ~10x the next-largest) never appears. Agent correctly abstained rather than guessing (correct abstention holds), but candidate relevance is a clean miss -- "largest/smallest/most-recent" queries need a manifest-attribute sort the tool doesn't have. |
| 8 | Analytics-related proposals | PASS | All 8 candidates genuinely on-topic (Genesys audio pipeline, OneMarketer processing, financial classification, sales forecasting) -- no noise, unlike Q4/Q6. Same English/Spanish skew as Q1: "Speech Analytics" (English) folder paths outrank "Propuestas Analitica" (Spanish) ones, so completeness (not relevance) is the open question -- agent correctly caveated the list may not be exhaustive. All 8 document_ids correctly cited. |
| 9 | GDPR / parental-leave policy (negative control) | PASS | Negative control works as designed: 7 weak candidates (all scoring only 1 matched token, "policy", against unrelated GCP IAM-policy-binding commands), zero occurrences of GDPR/parental/leave anywhere in returned content. Agent correctly recognized the "policy" match as a false positive and abstained rather than fabricating an answer. Low match scores (1 vs typical 5-6) are themselves a useful abstention signal. |
| 10 | Documents with `language: und` | PASS | Positive counterexample to Q3/Q7: "und" is a literal known `language` value, so the metadata filter correctly narrowed the pool to true `language: und` entries before ranking -- all 8 candidates are genuine (credentials list, 2 Plotly JSON chart configs, a Python dict of date ranges, an RFM Python script, 3 Java files). Agent correctly identified the common thread (non-prose/structured/code content, hence undetected language) and flagged the 8-item cap as a sample, not exhaustive. |

Fill in this table as each question is run against the real corpus and an agent's
answer is reviewed against the criteria above. Raw CLI output for each run should
be saved under `results/` (gitignored).
