"""
fetch_lda_full_1.py -- full pull of Lobbying Disclosure Act filings naming the Federal Reserve System, 1999-2025.

Runs with or without a Senate LDA API key (https://lda.senate.gov/api/register/ ; --key or LDA_API_KEY). With a key the API
allows about 120 requests a minute; without one 15 a minute and 25 rows a page, so a year takes about 4-6 hours: run one
year per job in parallel (fetch-lda-full.yml, matrix over years) from a public repository, where runner minutes are free.
The API does not filter on the government-entity field, so every filing of every year is paged through and the activities
whose government_entities include the Federal Reserve System are kept, with the FULL issue text (the 2026-10 pull cut it at
2,000 characters) and the client's state of principal place of business as well as its mailing state.
Resumable: one CSV per year in Data/raw/lda_full/; a year with a finished file is skipped. Run on the GitHub runner
(see fetch-lda-full.yml) or on any machine that reaches lda.senate.gov:
    python fetch_lda_full_1.py --key XXXX --years 1999-2025
Afterwards:  python fetch_lda_full_1.py --merge   writes Data/raw/lda_fed_filings_full.csv; point code_2.py / code_3.py at it.
UNTESTED against the live API from the writing session (no network); the request pattern follows fetch_data.py, which ran.
"""
import os, sys, csv, json, time, argparse, urllib.request, urllib.parse, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(os.path.dirname(HERE), 'Data', 'raw'); OUT = os.path.join(RAW, 'lda_full')
ap = argparse.ArgumentParser(); ap.add_argument('--key', default=os.environ.get('LDA_API_KEY', '')); ap.add_argument('--years', default='1999-2025')
ap.add_argument('--page-size', type=int, default=25); ap.add_argument('--merge', action='store_true'); ap.add_argument('--budget-hours', type=float, default=5.5)
ap.add_argument('--out', default=OUT, help='directory for the per-year files (default Data/raw/lda_full next to this script)')
args = ap.parse_args(); OUT = os.path.abspath(args.out); RAW = os.path.dirname(OUT); os.makedirs(OUT, exist_ok=True)
HDR = ['filing_uuid', 'filing_year', 'filing_period', 'filing_type', 'dt_posted', 'registrant_name', 'registrant_state', 'client_name', 'client_state',
       'client_ppb_state', 'client_country', 'client_general_description', 'income', 'expenses', 'general_issue_code', 'specific_issues',
       'n_lobbyists', 'n_entities', 'entities', 'n_activities_in_filing']
LOG = open(os.path.join(OUT, 'fetch_log.txt'), 'a')
def log(m): print(m, flush=True); LOG.write(time.strftime('%H:%M:%S ') + m + '\n'); LOG.flush()

UA = 'Mozilla/5.0 (research data fetch; contact ozaneksi@gmail.com)'   # the header fetch_data.py used in the pull that ran
def get(url, headers, tries=6):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=dict(headers, **{'User-Agent': UA}))
            with urllib.request.urlopen(req, timeout=180) as r: return r.read()
        except urllib.error.HTTPError as e:
            body = ''
            try: body = e.read()[:200].decode('utf-8', 'ignore')
            except Exception: pass
            last = e
            if e.code == 429: log(f'429 at {url[-60:]}: sleeping 60s'); time.sleep(60); continue
            if e.code >= 500: log(f'HTTP {e.code} at {url[-60:]} (try {k + 1}/{tries}): {body!r}'); time.sleep(15 * (k + 1)); continue
            raise
        except Exception as e:
            last = e; log(f'{e!r} at {url[-60:]} (try {k + 1}/{tries})'); time.sleep(15 * (k + 1))
    raise RuntimeError(f'gave up after {tries} tries: {last!r}')

def rows_from_filing(f):
    cl = f.get('client') or {}; rg = f.get('registrant') or {}; acts = f.get('lobbying_activities', []) or []; out = []
    for a in acts:
        ents = [e.get('name', '') for e in a.get('government_entities', []) or []]
        if not any('federal reserve' in e.lower() for e in ents): continue
