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
| 2 | Summarize `Caso_Financiera.py.md` | | |
| 3 | Documents per `knowledge_source` / languages | | |
| 4 | Deployment/DevOps scripts | | |
| 5 | Codex/GitHub/VS Code guide, language | | |
| 6 | Font-licensing / brand-typeface guidance | | |
| 7 | Largest curated file | | |
| 8 | Analytics-related proposals | | |
| 9 | GDPR / parental-leave policy (negative control) | | |
| 10 | Documents with `language: und` | | |

Fill in this table as each question is run against the real corpus and an agent's
answer is reviewed against the criteria above. Raw CLI output for each run should
be saved under `results/` (gitignored).
