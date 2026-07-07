"""
One-off generator for ohio_transcript_data/transcript_series.json.

Selects legislative series: the two floor series (House=26, Senate=25) plus
every series the Ohio Channel tags with a chamber (committee series). Old-GA
duplicate series (e.g. "- 134th GA") have chamber=None and are excluded;
the release-date window filters any stragglers at fetch time anyway.

Rerun at GA rollover (Jan 2027): update GENERAL_ASSEMBLY/GA_START below,
rerun, review the diff, commit.
"""
import json
import os

import ohiochannel_api as api

GENERAL_ASSEMBLY = 136
GA_START = "2025-01-01"
FLOOR_SERIES = {26: 'HOUSE', 25: 'SENATE'}


def main():
    series = api.get_series()
    keep = []
    for s in series:
        chamber = s.get('chamber')
        if s['id'] in FLOOR_SERIES:
            chamber = FLOOR_SERIES[s['id']]
        elif chamber not in ('HOUSE', 'SENATE', 'JOINT'):
            continue
        keep.append({
            'id': s['id'],
            'name': s.get('name', ''),
            'chamber': chamber,
            'is_floor': s['id'] in FLOOR_SERIES,
        })
    keep.sort(key=lambda x: x['id'])
    os.makedirs('ohio_transcript_data', exist_ok=True)
    out = 'ohio_transcript_data/transcript_series.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'general_assembly': GENERAL_ASSEMBLY,
                   'ga_start_date': GA_START,
                   'series': keep}, f, indent=2)
    print(f"wrote {len(keep)} series to {out}")


if __name__ == '__main__':
    main()
