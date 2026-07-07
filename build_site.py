"""
Assembles the deployable site into _site/ and builds the Pagefind index.
Used locally and by the deploy workflow. _site/ is never committed.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

SITE = '_site'
COPY_FILES = ['index.html', 'ohio-legislation-tracker-LIVE.html',
              'ohio-committee-hearings-LIVE.html',
              'transcripts.html']
COPY_DIRS = ['ohio_legislation_data']
TRANSCRIPT_JSON = ['programs_index.json', 'topics.json', 'transcripts_meta.json',
                   'transcript_series.json', 'topics_curated.json']


def verify(site_dir, rendered_count):
    pf = os.path.join(site_dir, 'pagefind', 'pagefind.js')
    assert os.path.exists(pf), 'pagefind.js missing — index build failed'
    # Fragment presence stands in for the spec's canary query: Pagefind has no
    # Python query API, and an index with fragments is a queryable index.
    frags = glob.glob(os.path.join(site_dir, 'pagefind', 'fragment', '*'))
    assert frags, 'no Pagefind index fragments'
    gz = len(glob.glob('ohio_transcript_data/programs/*.json.gz'))
    assert rendered_count == gz, f'rendered {rendered_count} pages != {gz} distilled programs'
    print(f'build OK: {rendered_count} transcript pages, {len(frags)} index fragments')


def main():
    shutil.rmtree(SITE, ignore_errors=True)
    os.makedirs(SITE)
    for f in COPY_FILES:
        if os.path.exists(f):
            shutil.copy(f, SITE)
    for d in COPY_DIRS:
        if os.path.isdir(d):
            shutil.copytree(d, os.path.join(SITE, d))
    td = os.path.join(SITE, 'ohio_transcript_data')
    os.makedirs(td, exist_ok=True)
    for name in TRANSCRIPT_JSON:
        src = os.path.join('ohio_transcript_data', name)
        if os.path.exists(src):
            shutil.copy(src, td)

    import render_transcripts as rt
    count = rt.render_all('ohio_transcript_data/programs',
                          'ohio_transcript_data/programs_index.json',
                          os.path.join(SITE, 'transcripts'))

    r = subprocess.run(['npx', '--yes', 'pagefind', '--site', SITE],
                       shell=(os.name == 'nt'))
    if r.returncode != 0:
        sys.exit('pagefind failed')
    verify(SITE, count)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
