from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from time import perf_counter
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .core import Store
from .service import answer
from .web import ALLOWED_HOSTS, fetch_document
import httpx

ROOT = Path(__file__).parent


def create_app(db_path=None):
    store = Store(db_path or os.getenv('EVIDENCE_DB', 'data/evidence.sqlite3'))

    @asynccontextmanager
    async def lifespan(app):
        for source in json.loads((ROOT / 'data/demo.json').read_text(encoding='utf-8')):
            store.ingest(**source)
        yield

    app = FastAPI(title='EvidenceDesk', version='0.1.0', lifespan=lifespan)

    class ImportRequest(BaseModel):
        url: str = Field(min_length=10, max_length=1000)
        title: str = Field(min_length=3, max_length=180)

    class Question(BaseModel):
        question: str = Field(min_length=3, max_length=1000)
        k: int = Field(default=4, ge=1, le=8)

    @app.get('/')
    def home():
        return FileResponse(ROOT / 'static/index.html')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'retrieval': 'SQLite FTS5 / BM25'}

    @app.get('/api/sources')
    def sources():
        return {'sources': store.sources(), 'allowed_hosts': sorted(ALLOWED_HOSTS)}

    @app.post('/api/sources/web')
    def ingest(request: ImportRequest):
        try:
            return store.ingest(request.title, request.url, fetch_document(request.url))
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except httpx.HTTPError as error:
            raise HTTPException(502, 'The documentation host could not be fetched.') from error

    @app.post('/api/ask')
    def ask(request: Question):
        started = perf_counter()
        evidence = store.retrieve(request.question, request.k)
        text, mode = answer(request.question, evidence)
        elapsed = round((perf_counter() - started) * 1000, 2)
        store.log(request.question, mode, len(evidence), elapsed)
        return {'answer': text, 'mode': mode, 'evidence': evidence, 'latency_ms': elapsed}

    @app.get('/api/metrics')
    def metrics():
        return store.metrics()

    return app


app = create_app()
