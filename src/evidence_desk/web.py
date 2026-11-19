"""Constrained public documentation import. No arbitrary-URL crawler."""
from html.parser import HTMLParser
from urllib.parse import urlsplit
import httpx

ALLOWED_HOSTS = {'fastapi.tiangolo.com', 'docs.python.org', 'www.sqlite.org', 'sqlite.org'}
MAX_BYTES = 1_000_000


def validate_url(url: str) -> str:
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in ALLOWED_HOSTS or p.username or p.password
            or p.port not in (None, 443) or p.fragment):
        raise ValueError('Use an HTTPS documentation URL from an allowed host, without credentials or fragments.')
    return url


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer', 'header'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer', 'header') and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def fetch_document(url: str) -> str:
    validate_url(url)
    # Do not follow redirects to unvalidated hosts; bound both time and bytes.
    with httpx.Client(timeout=12, follow_redirects=False, trust_env=False) as client:
        with client.stream('GET', url, headers={'User-Agent': 'EvidenceDesk/0.1 (educational local research)'}) as r:
            r.raise_for_status()
            if r.status_code != 200 or 'text/html' not in r.headers.get('content-type', ''):
                raise ValueError('Expected a direct HTML response (redirects are not followed).')
            body = bytearray()
            for block in r.iter_bytes():
                body.extend(block)
                if len(body) > MAX_BYTES:
                    raise ValueError('Document exceeds the 1 MB import limit.')
    parser = TextParser()
    parser.feed(body.decode('utf-8', errors='replace'))
    return ' '.join(parser.parts)
