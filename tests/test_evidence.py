import pytest
from fastapi.testclient import TestClient
from evidence_desk.core import Store, validate_citations
from evidence_desk.api import create_app
from evidence_desk.web import validate_url, TextParser


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'test.sqlite3')


def test_idempotent_update_removes_stale_index(store):
    assert store.ingest('Old', 'demo://x', 'Orchids are flowers grown in warm rooms with filtered light.')['changed']
    assert not store.ingest('Old', 'demo://x', 'Orchids are flowers grown in warm rooms with filtered light.')['changed']
    store.ingest('New', 'demo://x', 'Penguins are birds found around cold ocean environments.')
    assert not store.retrieve('orchids')
    assert store.retrieve('penguins')[0]['title'] == 'New'
    assert len(store.sources()) == 1


@pytest.mark.parametrize('query', ['', '" OR * NEAR(', "'; DROP TABLE sources; --", '💫'])
def test_queries_are_safe(store, query):
    assert store.retrieve(query) == []
    assert store.sources() == []


@pytest.mark.parametrize('url', ['http://docs.python.org/', 'https://127.0.0.1/',
    'https://docs.python.org.evil.test/', 'https://u:p@docs.python.org/', 'https://docs.python.org:444/'])
def test_ssrf_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_parser_removes_executable_content():
    p = TextParser()
    p.feed('<p>Useful text</p><script>steal()</script><style>x{}</style>')
    assert p.parts == ['Useful text']


def test_citation_validation():
    e = [{'citation': 1}]
    assert validate_citations('A claim [1]', e)
    assert not validate_citations('A claim [9]', e)
    assert not validate_citations('A claim [1]\n\nUncited claim', e)


def test_api_workflow_and_abstention(tmp_path, monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    with TestClient(create_app(tmp_path / 'api.sqlite3')) as client:
        assert client.get('/health').status_code == 200
        assert len(client.get('/api/sources').json()['sources']) == 3
        r = client.post('/api/ask', json={'question': 'How do citations and BM25 retrieval work?'}).json()
        assert r['mode'] == 'extractive' and r['evidence']
        assert '[' in r['answer']
        assert not client.post('/api/ask', json={'question': 'zyxwvutsrqponmlk'}).json()['evidence']
        assert client.get('/api/metrics').json()['queries'] == 2
        assert client.post('/api/ask', json={'question': 'ok', 'k': 900}).status_code == 422
