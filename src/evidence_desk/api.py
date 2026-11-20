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
from .reports import REPORTS, import_report
import httpx

ROOT = Path(__file__).parent


def create_app(db_path=None):
    store = Store(db_path or os.getenv('EVIDENCE_DB', 'data/evidence.sqlite3'))

    @asynccontextmanager
    async def lifespan(app):
        for source in json.loads((ROOT / 'data/demo.json').read_text(encoding='utf-8')):
            store.ingest(**source)
        yield

    app = FastAPI(title='EvidenceDesk — Bank Report Research', version='0.2.0', lifespan=lifespan)

    class ImportRequest(BaseModel):
        url: str = Field(min_length=10, max_length=1000)
        title: str = Field(min_length=3, max_length=180)

    class Question(BaseModel):
        question: str = Field(min_length=3, max_length=1000)
        k: int = Field(default=4, ge=1, le=8)
        bank: str | None = Field(default=None, max_length=100)
        year: int | None = Field(default=None, ge=2000, le=2100)

    class Comparison(BaseModel):
        question: str = Field(min_length=3, max_length=1000)
        banks: list[str] = Field(min_length=2, max_length=3)
        year: int = Field(default=2025, ge=2000, le=2100)

    @app.get('/')
    def home():
        return FileResponse(ROOT / 'static/index.html')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'retrieval': 'SQLite FTS5 / BM25'}

    @app.get('/api/sources')
    def sources():
        return {'sources': store.sources(), 'allowed_hosts': sorted(ALLOWED_HOSTS)}

    @app.get('/api/reports')
    def reports():
        return {'reports': [{'id': key, **value} for key, value in REPORTS.items()]}

    @app.post('/api/reports/{report_id}/import')
    def ingest_report(report_id: str):
        try:
            return import_report(store, report_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except httpx.HTTPError as error:
            raise HTTPException(502, 'The report publisher could not be fetched.') from error

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
        evidence = store.retrieve(request.question, request.k, request.bank, request.year)
        text, mode = answer(request.question, evidence)
        elapsed = round((perf_counter() - started) * 1000, 2)
        store.log(request.question, mode, len(evidence), elapsed)
        return {'answer': text, 'mode': mode, 'evidence': evidence, 'latency_ms': elapsed}

    @app.post('/api/compare')
    def compare(request: Comparison):
        if len(set(request.banks)) != len(request.banks):
            raise HTTPException(400, 'Choose distinct banks.')
        started = perf_counter()
        evidence, coverage = [], []
        # Retrieve separately so one long report cannot crowd out the other bank.
        for bank in request.banks:
            passages = store.retrieve(request.question, 3, bank, request.year)
            coverage.append({'bank': bank, 'passages': len(passages)})
            for passage in passages:
                passage['citation'] = len(evidence) + 1
                evidence.append(passage)
        missing = [c['bank'] for c in coverage if not c['passages']]
        if missing:
            text, mode = ('Insufficient evidence for a comparison. Missing relevant passages for: '
                          + ', '.join(missing) + '. Import the reports or refine the question.'), 'abstained'
        else:
            text, mode = answer('Compare ' + ', '.join(request.banks) + f' in {request.year}: '
                                + request.question + '. Distinguish reporting periods, units and definitions; '
                                'do not treat unlike financial measures as equivalent.', evidence)
        elapsed = round((perf_counter() - started) * 1000, 2)
        store.log(request.question, mode, len(evidence), elapsed)
        return {'answer': text, 'mode': mode, 'evidence': evidence, 'coverage': coverage,
                'latency_ms': elapsed}

    @app.get('/api/metrics')
    def metrics():
        return store.metrics()

    return app


app = create_app()
