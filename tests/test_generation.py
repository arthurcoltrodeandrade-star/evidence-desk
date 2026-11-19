import httpx
from evidence_desk.service import answer

EVIDENCE = [{'citation': 1, 'title': 'Fixture', 'body': 'SQLite stores source hashes for reproducibility.'}]


def enable(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-key-not-a-real-secret')
    monkeypatch.setenv('LLM_MODEL', 'mock-model')


def test_valid_llm_response(monkeypatch):
    enable(monkeypatch)
    def post(url, **kwargs):
        assert kwargs['json']['messages'][0]['role'] == 'system'
        assert 'untrusted' in kwargs['json']['messages'][0]['content']
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'choices': [{'message': {'content': 'Store content hashes. [1]'}}]})
    monkeypatch.setattr(httpx, 'post', post)
    assert answer('How are hashes stored?', EVIDENCE) == ('Store content hashes. [1]', 'llm')


def test_invalid_citation_falls_back(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(httpx, 'post', lambda url, **kwargs: httpx.Response(200,
        request=httpx.Request('POST', url), json={'choices': [{'message': {'content': 'Invented claim [99]'}}]}))
    text, mode = answer('hashes', EVIDENCE)
    assert mode == 'extractive_fallback' and '[99]' not in text and '[1]' in text


def test_provider_timeout_falls_back(monkeypatch):
    enable(monkeypatch)
    def fail(*args, **kwargs):
        raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(httpx, 'post', fail)
    assert answer('hashes', EVIDENCE)[1] == 'extractive_fallback'


def test_no_evidence_never_calls_provider(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('must not call')))
    assert 'Insufficient' in answer('unanswerable', [])[0]
