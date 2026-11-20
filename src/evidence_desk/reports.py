"""A reproducible catalog of public bank reports, with physical PDF-page provenance."""
from io import BytesIO
import httpx
from pypdf import PdfReader

REPORTS = {
    'sg-2025': {
        'title': 'Société Générale — full-year 2025 results',
        'bank': 'Société Générale', 'year': 2025,
        'url': 'https://www.societegenerale.com/sites/default/files/resultats-publication/en/2026-02/q4-2025-financial-results-presentation.pdf',
    },
    'bnp-2025': {
        'title': 'BNP Paribas — full-year 2025 results',
        'bank': 'BNP Paribas', 'year': 2025,
        'url': 'https://cdn-group.bnpparibas.com/uploads/file/Slides_BNPP_4Q25_Results_EN.pdf',
    },
}
MAX_BYTES = 20_000_000
MAX_PAGES = 200


def download_pdf(url: str) -> bytes:
    # Exact catalog URLs, not arbitrary hosts or user-controlled redirects.
    if url not in {r['url'] for r in REPORTS.values()}:
        raise ValueError('Choose a report from the public catalog.')
    data = bytearray()
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        with client.stream('GET', url, headers={'User-Agent': 'EvidenceDesk/0.2 educational research'}) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('Report must return a direct 200 response; redirects are disabled.')
            for block in response.iter_bytes():
                data.extend(block)
                if len(data) > MAX_BYTES:
                    raise ValueError('Report exceeds the 20 MB limit.')
    return bytes(data)


def extract_pages(data: bytes) -> list[tuple[int, str]]:
    if len(data) > MAX_BYTES or not data.startswith(b'%PDF-'):
        raise ValueError('Expected a PDF smaller than 20 MB.')
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('Encrypted reports are not supported.')
        if len(reader.pages) > MAX_PAGES:
            raise ValueError('Report exceeds the 200-page limit.')
        pages = []
        for number, page in enumerate(reader.pages, 1):
            content = page.get_contents()
            if content is not None and len(content.get_data()) > 5_000_000:
                raise ValueError('A PDF page exceeds the extraction limit.')
            text = page.extract_text(extraction_mode='layout') or ''
            if text.strip():
                pages.append((number, text))
        if sum(len(text) for _, text in pages) < 40:
            raise ValueError('No readable text found. Scanned PDFs require OCR, which is not implemented.')
        return pages
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('PDF could not be parsed.') from error


def import_report(store, report_id: str) -> dict:
    if report_id not in REPORTS:
        raise ValueError('Unknown report ID.')
    report = REPORTS[report_id]
    pages = extract_pages(download_pdf(report['url']))
    return store.ingest_pages(pages=pages, **report) | {'pages': len(pages), 'report_id': report_id}
