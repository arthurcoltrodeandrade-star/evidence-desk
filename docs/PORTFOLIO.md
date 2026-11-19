# Discussing EvidenceDesk in an interview

## CV description

**EvidenceDesk — source-grounded research assistant.** Built a Python/FastAPI application that imports public web documentation, persists provenance and overlapping chunks in SQLite, ranks evidence with FTS5/BM25, and returns cited briefs. Added an optional LLM generation adapter, citation validation and fallback behavior, a browser interface, Docker packaging and automated tests.

## Decisions worth explaining

1. Start with a lexical baseline that can be inspected and evaluated before adding embeddings.
2. Make the no-key path useful, while clearly distinguishing extractive retrieval from generative RAG.
3. Keep source hashes, URLs and timestamps alongside chunks so answers can be traced and imports can be repeated safely.
4. Treat remote text as untrusted data and narrow the importer to selected public hosts.
5. Test provider failures and invalid citations rather than assuming every LLM response succeeds.

## What was verified

17 local pytest cases cover persistence, index replacement, malformed queries, URL rejection, HTML extraction, end-to-end API behavior and mocked LLM generation/failure paths. Three synthetic retrieval smoke cases pass. A live FastAPI documentation import and browser query were checked. GitHub Actions runs pytest, the retrieval smoke evaluation and a Docker build.

The live LLM path was tested with mocked HTTP responses, not a paid model call. Do not describe this as a deployed client system, a semantic retrieval model, or a production-quality RAG benchmark.
