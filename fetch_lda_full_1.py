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
 
UA = 'Mozilla/5.0 (academic research data fetch)'   # a browser-style header, as in the pull that ran in 2026-10
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
        out.append([f.get('filing_uuid'), f.get('filing_year'), f.get('filing_period_display', f.get('filing_period')), f.get('filing_type'), f.get('dt_posted'),
                    rg.get('name'), rg.get('state'), cl.get('name'), cl.get('state'), cl.get('ppb_state'), cl.get('country') or cl.get('ppb_country'),
                    cl.get('general_description'), f.get('income'), f.get('expenses'), a.get('general_issue_code'), a.get('description') or '',
                    len(a.get('lobbyists', []) or []), len(ents), ';'.join(ents), len(acts)])
    return out
 
if args.merge:
    rows = []
    for fn in sorted(os.listdir(OUT)):
        if fn.startswith('lda_fed_') and fn.endswith('.csv'):
            with open(os.path.join(OUT, fn), newline='', encoding='utf-8') as fh: r = csv.reader(fh); next(r); rows += list(r)
    with open(os.path.join(RAW, 'lda_fed_filings_full.csv'), 'w', newline='', encoding='utf-8') as fh: w = csv.writer(fh); w.writerow(HDR); w.writerows(rows)
    log(f'merged {len(rows)} activity rows into lda_fed_filings_full.csv'); sys.exit(0)
 
if args.key: H = {'Authorization': f'Token {args.key}'}; sleep = 0.55
else: H = {}; sleep = 4.2; args.page_size = min(args.page_size, 25); log('no API key: anonymous access, 25 rows a page, one request every 4.2 s')
base = 'https://lda.senate.gov/api/v1/filings/'
ys = [int(x) for x in args.years.split('-')]; y0, y1 = ys[0], ys[-1]; T0 = time.time()
for y in range(y0, y1 + 1):
    done = os.path.join(OUT, f'lda_fed_{y}.csv'); part = os.path.join(OUT, f'lda_fed_{y}.partial.csv'); state = os.path.join(OUT, f'lda_fed_{y}.page')
    if os.path.exists(done): log(f'{y}: finished earlier, skipped'); continue
    page = int(open(state).read()) if os.path.exists(state) else 1
    mode = 'a' if page > 1 and os.path.exists(part) else 'w'
    fh = open(part, mode, newline='', encoding='utf-8'); w = csv.writer(fh)
    if mode == 'w': w.writerow(HDR)
    n_rows = n_scanned = 0; total = None
    while True:
        if time.time() - T0 > 3600 * args.budget_hours: log(f'{y}: time budget reached at page {page}; rerun to resume'); fh.close(); sys.exit(0)
        q = urllib.parse.urlencode({'filing_year': y, 'page_size': args.page_size, 'page': page})   # no 'ordering': it made the server time out
        try: d = json.loads(get(base + '?' + q, H))
        except urllib.error.HTTPError as e:
            if e.code == 404: break          # past the last page
            log(f'{y} p{page}: {e!r}'); fh.close(); sys.exit(1)
        total = d.get('count', total)
        for f in d.get('results', []):
            n_scanned += 1; r = rows_from_filing(f); w.writerows(r); n_rows += len(r)
        if page % 50 == 0: fh.flush(); open(state, 'w').write(str(page + 1)); log(f'{y} p{page}: {n_scanned} filings scanned of {total}, {n_rows} Fed activity rows')
        if not d.get('next'): break
        page += 1; time.sleep(sleep)
    fh.close(); os.replace(part, done)
    if os.path.exists(state): os.remove(state)
    log(f'{y}: done, {n_scanned} filings scanned, {n_rows} activity rows naming the Federal Reserve System')
log('all years done; run with --merge')
