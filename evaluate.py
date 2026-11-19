"""Small deterministic retrieval smoke benchmark, not a production quality claim."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from evidence_desk.core import Store

CASES = [
    ('How do pipeline hashes prevent duplicate records?', 'demo://pipelines'),
    ('What are BM25 lexical retrieval limitations?', 'demo://retrieval'),
    ('What does public deployment need beyond Docker?', 'demo://deployment'),
]
with TemporaryDirectory() as tmp:
    store = Store(Path(tmp) / 'eval.sqlite3')
    for s in json.loads(Path('src/evidence_desk/data/demo.json').read_text()):
        store.ingest(**s)
    hits = [store.retrieve(q, 1)[0]['url'] == expected for q, expected in CASES]
    result = {'cases': len(CASES), 'top1_accuracy': sum(hits) / len(hits), 'hits': hits,
              'scope': 'handwritten synthetic smoke cases; not a held-out benchmark'}
    print(json.dumps(result, indent=2))
