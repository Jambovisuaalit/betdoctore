"""Issue private ground-truth decisions; never rewrite historical feature observations."""
import hashlib
import json
from pathlib import Path

from betdoctore.capture_inventory import save

EVIDENCE = Path('data/evaluation/primary-result-evidence')
# Reviewed provider representations, not original HTTP wire bytes or past archive captures.
CASES = (
    ('nba:2023-10-25:LAC:POR', 123, 111, '5c4373af5d0b028fe0f16b014ba2fa84d3397f944e173e8e7b753edc2e6732f3',
     'https://www.nba.com/game/por-vs-lac-0022300074', "Clippers' 123-111 win"),
    ('nba:2024-01-23:NOP:UTA', 153, 124, '2f93ea4df527bb51fd21abb942cc0391f1b4e32d3831ef5490d2cc61957b6d33',
     'https://www.nba.com/pelicans/news/pelicans-delivered-memorable-record-setting-performance-vs-utah',
     '153-124 victory over Utah'),
    ('nba:2024-11-02:MEM:PHI', 124, 107, 'c9ea6cac7fe53498b4dca807f6f92abfb97bcb64c1171a9e772728d9a76c9a63',
     'https://www.nba.com/watch/video/game-recap-grizzlies-124-76ers-107',
     'Game Recap: Grizzlies 124, 76ers 107'),
    ('nba:2025-01-25:MEM:UTA', 125, 103, '7d7b0e685b48117d993f23b36069276e79fe52f1c313bccd36306eb9b6169fdd',
     'https://www.nba.com/game/0022400643', '125-103 over Jazz'),
)
AUDIT = 'e80d87b04f137af4520ada193c26de7e966caa1eebf9531f84c58cb46bf7e219'


def verified_json(path, digest):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f'Evidence digest mismatch: {path.name}')
    return json.loads(raw)


def decide(evidence=EVIDENCE, audit_directory=Path('data/evaluation/conflict-review')):
    audit = verified_json(audit_directory / f'{AUDIT}.conflict-audit.json', AUDIT)
    games = {game['game_key']: game for game in audit['games']}
    decisions = []
    for number, (key, a, b, digest, url, text) in enumerate(CASES, 1):
        path = evidence / f'firecrawl-official-{number}.json'
        payload = verified_json(path, digest)
        source = payload['source']
        metadata = source['metadata']
        if (payload['url'] != url or metadata['sourceURL'] != url
                or metadata['statusCode'] != 200 or not source.get('rawHtml')
                or text not in source['markdown']
                or payload['historical_availability_proven'] is not False
                or payload['original_http_wire_bytes_verified'] is not False):
            raise ValueError(f'Official evidence contract failed: {key}')
        variants = games[key]['score_variants']
        if not variants or any((v['points_a'], v['points_b']) == (a, b) for v in variants):
            raise ValueError(f'Expected conflicting FixtureDownload observation: {key}')
        decisions.append({
            'game_key': key, 'decision': 'ACCEPT_OFFICIAL_RESULT_FOR_GROUND_TRUTH_REVIEW',
            'points_a': a, 'points_b': b, 'team_order': key.split(':')[2:],
            'rejected_score_variants': variants, 'rejected_publisher': 'FixtureDownload',
            'evidence_file': path.name, 'evidence_sha256': digest, 'source_url': url,
            'evidence_grade': 'OFFICIAL_CONTENT_VIA_PROVIDER_REPRESENTATION',
            'original_http_wire_bytes_verified': False,
            'historical_t60_availability_proven': False,
            'historical_feature_replacement_authorized': False,
            'reason': 'Reviewed official report supports the accepted score; archived '
                      'FixtureDownload scores disagree. Preserve both source observations.',
        })
    return {
        'schema_version': 1, 'decision_date': '2026-11-05',
        'scope': 'PRIVATE_NONCOMMERCIAL_GROUND_TRUTH_ADJUDICATION_ONLY',
        'conflict_audit_sha256': AUDIT, 'decisions': decisions,
        'observations_modified': False, 'regular_manifest_modified': False,
        'frozen_forecasts_modified': False, 'frozen_evaluation_modified': False,
        'automatic_ingestion_approval': False, 'production_ready': False,
        'open_gates': ['HISTORICAL_T60_AVAILABILITY', 'LONGER_TEMPORAL_COVERAGE',
                       'ADVANCED_SOURCE_ADMISSION', 'BETTING_EDGE_VALIDATION'],
    }


if __name__ == '__main__':
    report = decide()
    name = save(EVIDENCE, 'result-adjudication.json', report)
    print(EVIDENCE / name)
