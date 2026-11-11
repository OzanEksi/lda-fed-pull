# Full pull of LDA filings naming the Federal Reserve System, one job per year, anonymous API access (no key needed).
# Lives at .github/workflows/fetch-lda-full.yml with fetch_lda_full_1.py at the root of a PUBLIC repository.
# Actions -> fetch-lda-full -> Run workflow. A year that does not finish inside the 5.6-hour budget is resumed by the
# next run from the cache; rerun until the job "merge" prints "all years finished".
name: fetch-lda-full
on:
  workflow_dispatch:
jobs:
  pull:
    runs-on: ubuntu-latest
    timeout-minutes: 355
    strategy:
      fail-fast: false
      max-parallel: 20
      matrix:
        year: [1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013,
               2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: restore this year's partial pull from the previous run
        uses: actions/cache/restore@v4
        with:
          path: lda_full
          key: "lda-${{ matrix.year }}-${{ github.run_id }}"
          restore-keys: "lda-${{ matrix.year }}-"
      - name: pull
        run: python fetch_lda_full_1.py --years ${{ matrix.year }} --budget-hours 5.6 --out lda_full
      - name: save the year's files for the next run
        if: always()
        uses: actions/cache/save@v4
        with:
          path: lda_full
          key: "lda-${{ matrix.year }}-${{ github.run_id }}"
      - name: upload the year's files
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: "lda_full_${{ matrix.year }}"
          path: lda_full
          retention-days: 30
  merge:
    needs: pull
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: actions/download-artifact@v4
        with:
          pattern: lda_full_*
          path: lda_full
          merge-multiple: true
      - name: summary
        run: |
          ls lda_full
          n=$(ls lda_full/lda_fed_????.csv 2>/dev/null | wc -l); echo "finished years: $n of 27"
          if [ "$n" -eq 27 ]; then echo "all years finished"; else echo "NOT finished: run the workflow again"; fi
      - name: merge (complete only when all years are finished)
        run: python fetch_lda_full_1.py --merge --out lda_full || true
      - name: upload everything
        uses: actions/upload-artifact@v4
        with:
          name: lda_fed_filings_full
          path: lda_full
          retention-days: 90
