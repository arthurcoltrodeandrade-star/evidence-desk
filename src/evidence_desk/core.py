"""Persistence, lexical retrieval and auditable briefs. No model download required."""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
import sqlite3


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold(), re.UNICODE)


STOPWORDS = set('the a an and or of to in on for with is are was be as by it this that what which how can do does should from about'.split())


def chunks(text: str, size: int = 180, overlap: int = 35) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size - overlap)]


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                  id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT UNIQUE NOT NULL,
                  fetched_at TEXT NOT NULL, digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks (
                  id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id),
                  ordinal INTEGER NOT NULL, body TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(body, tokenize='unicode61');
                CREATE TABLE IF NOT EXISTS runs (
                  id INTEGER PRIMARY KEY, created_at TEXT, question TEXT, mode TEXT,
                  citations INTEGER, latency_ms REAL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, title: str, url: str, text: str) -> dict:
        text = " ".join(text.split())
        if len(text) < 40:
            raise ValueError('Source must contain at least 40 characters of readable text.')
        digest = sha256(text.encode()).hexdigest()
        with self.connect() as db:
            existing = db.execute('SELECT * FROM sources WHERE url=?', (url,)).fetchone()
            if existing and existing['digest'] == digest:
                return {'id': existing['id'], 'changed': False, 'digest': digest}
            if existing:
                sid = existing['id']
                db.execute('DELETE FROM search WHERE rowid IN (SELECT id FROM chunks WHERE source_id=?)', (sid,))
                db.execute('DELETE FROM chunks WHERE source_id=?', (sid,))
                db.execute('UPDATE sources SET title=?, fetched_at=?, digest=? WHERE id=?',
                           (title, datetime.now(timezone.utc).isoformat(), digest, sid))
            else:
                sid = db.execute('INSERT INTO sources(title,url,fetched_at,digest) VALUES(?,?,?,?)',
                                 (title, url, datetime.now(timezone.utc).isoformat(), digest)).lastrowid
            for ordinal, body in enumerate(chunks(text)):
                cid = db.execute('INSERT INTO chunks(source_id,ordinal,body) VALUES(?,?,?)', (sid, ordinal, body)).lastrowid
                db.execute('INSERT INTO search(rowid,body) VALUES(?,?)', (cid, body))
        return {'id': sid, 'changed': True, 'digest': digest}

    def sources(self) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM sources ORDER BY id')]

    def retrieve(self, question: str, k: int = 5) -> list[dict]:
        # Tokens only: user input can never become FTS syntax or SQL.
        terms = list(dict.fromkeys(t for t in tokens(question) if len(t) > 2 and t not in STOPWORDS))[:24]
        if not terms:
            return []
        query = ' OR '.join('"' + t + '"' for t in terms)
        with self.connect() as db:
            rows = db.execute('''SELECT c.id, c.body, s.title, s.url, s.fetched_at,
                       s.digest, bm25(search) AS score FROM search
                       JOIN chunks c ON c.id=search.rowid JOIN sources s ON s.id=c.source_id
                       WHERE search MATCH ? ORDER BY score,c.id LIMIT ?''', (query, k * 3)).fetchall()
        minimum = 2 if len(terms) > 2 else 1
        rows = [r for r in rows if len(set(terms) & set(tokens(r['body']))) >= minimum][:k]
        return [dict(r) | {'citation': i + 1} for i, r in enumerate(rows)]

    def log(self, question: str, mode: str, count: int, latency: float):
        with self.connect() as db:
            db.execute('INSERT INTO runs(created_at,question,mode,citations,latency_ms) VALUES(?,?,?,?,?)',
                       (datetime.now(timezone.utc).isoformat(), question, mode, count, latency))

    def metrics(self):
        with self.connect() as db:
            row = db.execute('SELECT count(*) queries, avg(latency_ms) mean_latency_ms FROM runs').fetchone()
            modes = Counter(r[0] for r in db.execute('SELECT mode FROM runs'))
        return dict(row) | {'modes': dict(modes)}


def extractive_brief(question: str, evidence: list[dict]) -> str:
    if not evidence:
        return 'Insufficient evidence in the indexed sources. Add a relevant source and try again.'
    terms = set(tokens(question))
    result = []
    for item in evidence:
        sentences = re.split(r'(?<=[.!?])\s+', item['body'])
        best = sorted(enumerate(sentences), key=lambda pair: len(terms & set(tokens(pair[1]))), reverse=True)[:2]
        selection = ' '.join(sentence for _, sentence in sorted(best))
        result.append(f"{selection} [{item['citation']}]")
    return '\n\n'.join(result)


def validate_citations(answer: str, evidence: list[dict]) -> bool:
    """Validate IDs and paragraph coverage, not semantic entailment."""
    allowed = {str(x['citation']) for x in evidence}
    used = re.findall(r'\[(\d+)\]', answer)
    return bool(used) and set(used) <= allowed and all(
        re.search(r'\[\d+\]', p) for p in answer.split('\n\n') if p.strip())
