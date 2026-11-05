"""Synthetic regression coverage for the 2026-11-05 engineering audit."""
import json
import os
import subprocess
import sys
from datetime import timedelta

import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from betdoctore.api import app
from betdoctore.backtest import run
from betdoctore.cli import app as cli
from betdoctore.domain import Odds
from betdoctore.engine import Model, Settings
from betdoctore.fixtures import dataset
from betdoctore.ingestion import PinnacleAdapter
from betdoctore.storage import SUPPORTED_SCHEMA_REVISION


@pytest.mark.parametrize('value', ['missing', None, 'unknown'])
def test_unconfirmed_market_rule_is_rejected(value):
    _, odds = dataset()
    row = odds[-1].model_dump(mode='json')
    if value == 'missing':
        row.pop('includes_overtime')
    else:
        row['includes_overtime'] = value
    with pytest.raises(ValidationError, match='includes_overtime'):
        Odds.model_validate(row)


@pytest.mark.parametrize('extension', ['csv', 'parquet'])
def test_export_requires_explicit_market_rule(tmp_path, extension):
    _, odds = dataset()
    row = odds[-1].model_dump(mode='json')
    row.pop('includes_overtime')
    frame = pd.DataFrame([row])
    path = tmp_path / f'synthetic.{extension}'
    if extension == 'csv':
        frame.to_csv(path, index=False)
    else:
        frame.to_parquet(path)
    with pytest.raises(ValidationError, match='includes_overtime'):
        PinnacleAdapter(path).snapshots()


def test_ready_requires_revision_and_complete_schema(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path}/synthetic.db'
    monkeypatch.setenv('DATABASE_URL', url)
    engine = create_engine(url)
    client = TestClient(app)
    assert client.get('/ready').status_code == 503
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE feature_snapshots (digest TEXT)'))
    assert client.get('/ready').status_code == 503
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE feature_snapshots'))
    config = Config('alembic.ini')
    assert ScriptDirectory.from_config(config).get_heads() == [SUPPORTED_SCHEMA_REVISION]
    command.upgrade(config, '0001')
    assert client.get('/ready').status_code == 503
    command.upgrade(config, 'head')
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.json()['production_ready'] is False
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'unsupported'"))
    assert client.get('/ready').status_code == 503
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = :version"),
                           {'version': SUPPORTED_SCHEMA_REVISION})
        connection.execute(text('DROP TABLE advanced_stage_rows'))
    assert client.get('/ready').status_code == 503
    engine.dispose()


def test_fixed_model_skips_early_targets_but_evaluates_boundary():
    games, odds = dataset()
    boundary = games[-2].tipoff - timedelta(minutes=60)
    model = Model(trained_until=boundary)
    result = run(games, odds, model, Settings())
    assert {p['game_id'] for p in result['predictions']} == {g.game_id for g in games[-2:]}
    early = [s for s in result['skipped'] if s['reason'] == 'MODEL_TRAINED_AFTER_CUTOFF']
    assert {s['game_id'] for s in early} == {g.game_id for g in games[:-2]}
    assert result['bets'] == []


def test_cli_separates_research_assessment_from_betting_readiness():
    result = CliRunner().invoke(cli, ['status'])
    assert result.exit_code == 0
    status = json.loads(result.output)
    assert '298' in status['FORECAST_EVALUATION_READY']
    assert status['DATA_READY'].startswith('PARTIAL')
    assert status['BACKTEST_READY'].startswith('BLOCKED')
    assert status['PRODUCTION_READY'] is False
    assert status['advanced_data_approved'] is False


def test_installed_package_and_cli_outside_repository(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    code = ("from betdoctore.temporal_evaluation import protocol; "
            "from typer.testing import CliRunner; "
            "from betdoctore.cli import app; "
            "assert protocol()['synthetic'] is False; "
            "result = CliRunner().invoke(app, ['status']); "
            "assert result.exit_code == 0, result.output; print(result.output)")
    result = subprocess.run([sys.executable, '-c', code], check=False, cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['PRODUCTION_READY'] is False
