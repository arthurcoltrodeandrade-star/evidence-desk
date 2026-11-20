from io import BytesIO
import sqlite3
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from fastapi.testclient import TestClient
from evidence_desk.api import create_app
from evidence_desk.core import Store
from evidence_desk.reports import extract_pages, download_pdf


def pdf_fixture(texts):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                NameObject('/Subtype'): NameObject('/Type1'),
                                NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 40 740 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_physical_pages_and_empty_page_preserved():
    data = pdf_fixture(['Orchid Bank revenues increased during the reporting year.', '',
                        'Orchid Bank cost of risk remained stable during the year.'])
    pages = extract_pages(data)
    assert [p for p, _ in pages] == [1, 3]
    assert 'cost of risk' in pages[1][1]


@pytest.mark.parametrize('data', [b'not a pdf', b'%PDF-broken'])
def test_malformed_pdf_rejected(data):
    with pytest.raises(ValueError):
        extract_pages(data)


def test_empty_and_encrypted_pdf_rejected():
    with pytest.raises(ValueError, match='No readable text'):
        extract_pages(pdf_fixture(['']))
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    writer.encrypt('test-only')
    out = BytesIO()
    writer.write(out)
    with pytest.raises(ValueError, match='Encrypted'):
        extract_pages(out.getvalue())


def test_arbitrary_pdf_url_rejected():
    with pytest.raises(ValueError):
        download_pdf('https://127.0.0.1/private.pdf')


def test_page_citations_filters_and_atomic_replacement(tmp_path):
    store = Store(tmp_path / 'pages.sqlite3')
    pages = [(2, 'Orchid Bank revenues increased to ten million euros during the year.'),
             (7, 'Orchid Bank liquidity coverage reached a comfortable level this year.')]
    store.ingest_pages('Orchid', 'https://example.test/report.pdf', pages, 'Orchid', 2025)
    store.ingest_pages('Other', 'https://example.test/other.pdf', pages, 'Other', 2024)
    assert not store.ingest_pages('Orchid', 'https://example.test/report.pdf', pages, 'Orchid', 2025)['changed']
    hit = store.retrieve('liquidity coverage', bank='Orchid', year=2025)[0]
    assert hit['page'] == 7 and hit['citation_url'].endswith('#page=7')
    assert not store.retrieve('liquidity coverage', bank='Orchid', year=2024)
    store.ingest_pages('Orchid', 'https://example.test/report.pdf',
                       [(9, 'Orchid Bank operating expenses decreased in the reporting year.')], 'Orchid', 2025)
    assert not store.retrieve('liquidity coverage', bank='Orchid')
    assert store.retrieve('operating expenses', bank='Orchid')[0]['page'] == 9


def test_old_database_migrates_without_losing_content(tmp_path):
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE sources(id INTEGER PRIMARY KEY,title TEXT,url TEXT UNIQUE,
                          fetched_at TEXT,digest TEXT);
                          CREATE TABLE chunks(id INTEGER PRIMARY KEY,source_id INTEGER,ordinal INTEGER,body TEXT);
                          INSERT INTO sources VALUES(1,'Existing','demo://old','yesterday','abc');''')
    assert Store(path).sources()[0]['title'] == 'Existing'
    assert Store(path).sources()[0]['bank'] is None


def test_comparison_requires_both_banks_and_unique_citations(tmp_path, monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    path = tmp_path / 'api.sqlite3'
    store = Store(path)
    store.ingest_pages('Orchid', 'https://example.test/a.pdf',
                       [(2, 'Orchid revenues increased over the year with stable operating expenses.')], 'Orchid', 2025)
    with TestClient(create_app(path)) as client:
        body = {'question': 'revenues operating expenses', 'banks': ['Orchid', 'Lily'], 'year': 2025}
        assert client.post('/api/compare', json=body).json()['mode'] == 'abstained'
        store.ingest_pages('Lily', 'https://example.test/b.pdf',
                           [(4, 'Lily revenues increased over the year with higher operating expenses.')], 'Lily', 2025)
        result = client.post('/api/compare', json=body).json()
        assert result['mode'] == 'extractive'
        assert [e['citation'] for e in result['evidence']] == [1, 2]
        assert {e['bank'] for e in result['evidence']} == {'Orchid', 'Lily'}
        assert client.post('/api/compare', json=body | {'banks': ['Lily', 'Lily']}).status_code == 400
        assert client.post('/api/reports/not-real/import', json={}).status_code == 400
        assert len(client.get('/api/reports').json()['reports']) == 2
