"""Opt-in real-report retrieval check. Downloads publishers' PDFs to a gitignored cache.

Run: python bank_eval.py --download
No LLM calls. These manually selected smoke cases are not a held-out benchmark.
"""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from evidence_desk.core import Store
from evidence_desk.reports import REPORTS, download_pdf, extract_pages

CASES = [
    {'report': 'sg-2025', 'question': 'cost income ratio', 'expected_pages': [3]},
    {'report': 'sg-2025', 'question': 'CET1 liquidity coverage', 'expected_pages': [3]},
    {'report': 'bnp-2025', 'question': 'revenues operating expenses', 'expected_pages': [4]},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Allow downloading missing public PDFs')
    args = parser.parse_args()
    cache = Path('data/reports')
    cache.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / 'eval.sqlite3')
        for rid, report in REPORTS.items():
            path = cache / f'{rid}.pdf'
            if not path.exists():
                if not args.download:
                    parser.error(f'{path} missing; use --download to fetch it from the publisher.')
                path.write_bytes(download_pdf(report['url']))
            store.ingest_pages(pages=extract_pages(path.read_bytes()), **report)
        results = []
        for case in CASES:
            report = REPORTS[case['report']]
            hits = store.retrieve(case['question'], 5, report['bank'], report['year'])
            ranks = [i for i, hit in enumerate(hits, 1) if hit['page'] in case['expected_pages']]
            results.append(case | {'retrieved_pages': [h['page'] for h in hits],
                                   'hit_at_5': bool(ranks), 'reciprocal_rank': 1 / min(ranks) if ranks else 0})
        negative = store.retrieve('xylophone extraterrestrial recipe', 5, 'Société Générale', 2025)
        print(json.dumps({'scope': 'manually selected real-report smoke cases; not held-out',
                          'cases': results, 'hit_at_5': sum(r['hit_at_5'] for r in results) / len(results),
                          'mrr_at_5': sum(r['reciprocal_rank'] for r in results) / len(results),
                          'unanswerable_returns_no_passages': not negative}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
