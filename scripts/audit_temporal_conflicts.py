"""Offline private evidence audit. Never edits observations or frozen evaluations."""
import json
from collections import defaultdict
from pathlib import Path

from betdoctore.archived_exports import load_export, load_feed_inventory
from betdoctore.capture_inventory import save

ROOT = Path('data/evaluation')
KEYS = {'nba:2023-10-25:LAC:POR', 'nba:2024-01-23:NOP:UTA',
        'nba:2025-01-25:MEM:UTA', 'nba:2024-11-02:MEM:PHI'}


def main():
    directory = ROOT/'embedded-exports'
    snapshots = [load_export(directory, p) for p in sorted(directory.glob('*.capture-receipt.json'))]
    inventory = ROOT/'new-capture-inventory/3862cea977721f6627e98dabb4db0766d06b02a1993498ac2b1518658b9a9f3b.combined-inventory.json'
    snapshots.extend(load_feed_inventory(inventory.parent, inventory))
    evidence = defaultdict(list)
    for snapshot in snapshots:
        for row in snapshot['rows']:
            if row['game_key'] in KEYS and row['score_identity'] is not None:
                points = dict(zip((row['home'], row['away']), row['score_identity'], strict=True))
                a, b = row['teams']
                evidence[row['game_key']].append({
                    'points_a': points[a], 'points_b': points[b],
                    'captured_at': row['public_available_by'],
                    'original': snapshot['original'], 'sha256': snapshot['payload_sha256'],
                    'source_row': row['source_row']})
    report = {'status': 'EVIDENCE_PROPOSALS_ONLY', 'observations_modified': False,
              'frozen_evaluation_modified': False, 'production_ready': False, 'games': []}
    for key in sorted(KEYS):
        groups = defaultdict(list)
        for row in evidence[key]:
            groups[(row['points_a'], row['points_b'])].append(row)
        report['games'].append({'game_key': key, 'score_variants': [
            {'points_a': score[0], 'points_b': score[1],
             'first_observed_capture': min(r['captured_at'] for r in rows),
             'evidence': rows} for score, rows in sorted(groups.items())],
            'publisher': 'FixtureDownload', 'independent_publisher_count': 1,
            'adjudication': 'PENDING_INDEPENDENT_PRIMARY_EVIDENCE'})
    path = save(ROOT/'conflict-review', 'conflict-audit.json', report)
    print(json.dumps({'report': str(ROOT/'conflict-review'/path), 'games': [
        {'game_key': g['game_key'], 'variants': [
            {k: v for k, v in row.items() if k != 'evidence'} for row in g['score_variants']]}
        for g in report['games']]}, indent=2))


if __name__ == '__main__':
    main()
