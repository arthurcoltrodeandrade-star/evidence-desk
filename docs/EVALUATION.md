# Retrieval evaluation notes

## Corpus

- Société Générale: 75 physical PDF pages, 2025 full-year results presentation.
- BNP Paribas: 36 physical PDF pages, 2025 full-year results presentation.
- Sources are listed in `src/evidence_desk/reports.py`; PDFs and databases stay out of git.
- Relevant pages were checked against rendered originals. Metadata year means reporting-document year, not that every statement on every page concerns that year.

## Initial BM25 baseline

| Report | Query | Relevant physical page | Retrieved pages, top 5 | Reciprocal rank |
|---|---|---:|---|---:|
| SG 2025 | cost income ratio | 3 | 74, 26, 11, 23, 3 | 0.20 |
| SG 2025 | CET1 liquidity coverage | 3 | 3, 51 | 1.00 |
| BNP 2025 | revenues operating expenses | 4 | 18, 16, 22, 18, 16 | 0.00 |

Hit@5 = 2/3; MRR@5 = 0.40. Repeated page numbers mean different chunks from the same page. The negative query `xylophone extraterrestrial recipe` retrieves no passages.

The BNP failure is retained: the lexical baseline ranks division-specific tables above the desired group summary. Changing the expected page to hide this failure would make the result misleading. A representative future evaluation should include reporting periods, group/division distinctions, ambiguous terms, numeric units, multilingual paraphrases, deliberately unanswerable questions and source instructions attempting to manipulate generation.

## Reproduce

```sh
pip install -e '.[dev]'
python bank_eval.py --download
# Subsequently, use the cached PDFs without network:
python bank_eval.py
```

The runner creates a temporary database so pre-existing user imports cannot contaminate scores. It makes no LLM calls. The benchmark is a development smoke check, not a held-out test set; it cannot measure hallucination rate, financial correctness or general retrieval quality. Publisher revisions can change the result. Source hashes are available in the app's source library/API.
