# Portfolio explanation

## Suggested CV bullet

**EvidenceDesk — Bank Report RAG:** Built a Python/FastAPI research app that indexes public bank-results PDFs in SQLite FTS5, preserves page-level provenance and supports filtered retrieval, cross-bank evidence comparison and optional LLM answers with citation validation; packaged with Docker, CI and 25 automated tests.

## Interview walkthrough

1. Import a publisher PDF from the exact catalog. Explain size/page limits, text extraction and the absence of OCR.
2. Show the SQLite schema, idempotent import and atomic stale-chunk replacement.
3. Search with bank and reporting-year filters, then open an original PDF page.
4. Compare banks: retrieval runs independently per bank; missing relevant passages prevent a comparison answer.
5. Explain the difference between extractive mode and configured LLM generation. Show mocked provider tests and invalid-citation fallback.
6. Discuss the real-report retrieval failure in EVALUATION.md. Propose a larger labeled benchmark before choosing embeddings/reranking.

This is personal project experience, not employment or a production banking system. No live paid LLM call or cloud deployment was performed. The 2/3 smoke result is too small to claim an accuracy rate on a CV.
