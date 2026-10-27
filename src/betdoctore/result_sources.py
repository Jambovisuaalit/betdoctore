"""Pinned, explicitly licensed result acquisition and reproducible import evidence."""
import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .results import BasicResult, audit, parse_neil_paine
from .storage import BasicResultRow, ResultSourceSnapshot

COMMIT = "9a485bacef9f18f6a8e3ec671f13b9609386f0fa"
SOURCE_URL = (f"https://raw.githubusercontent.com/Neil-Paine-1/NBA-elo/{COMMIT}/"
              "NBA%20Elo%202025%20-%20nba_elo.csv")
SOURCE_SHA256 = "a0d7d27e829ed73d5c132d86ee6e41d4fd07c684c3d23c9c8a8d42f2de9924a5"
LICENSE_URL = f"https://raw.githubusercontent.com/Neil-Paine-1/NBA-elo/{COMMIT}/LICENSE.txt"
LICENSE_SHA256 = "1545615554fbf1609c3ce1d18f38d879acb4c305d72822f6aeb0c0e4d4a6872d"
ATTRIBUTION = ("NBA Elo archive: Neil Paine, MIT, Copyright (c) 2024 Neil Paine; "
               "derived from FiveThirtyEight NBA Elo, CC BY 4.0. BetDoctore extracts final "
               "scores and calendar-date metadata, canonicalizes teams and validates opposing rows. "
               "No Elo, forecasts or RAPTOR imported. No endorsement implied.")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_once(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as target:
            target.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError(f"Immutable artifact differs: {path.name}") from None


def acquire(directory: Path, client: httpx.Client | None = None) -> Path:
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        # Reuse recorded acquisition time, never rewrite history on repeat runs.
        verify_bundle(directory)
        return manifest_path
    owned = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=False)
    try:
        payloads = []
        for url, expected in ((SOURCE_URL, SOURCE_SHA256), (LICENSE_URL, LICENSE_SHA256)):
            response = client.get(url)
            response.raise_for_status()
            if sha256(response.content) != expected:
                raise ValueError("Pinned source/license checksum mismatch; review source update")
            payloads.append(response.content)
    finally:
        if owned:
            client.close()
    retrieved = datetime.now(UTC).isoformat()
    write_once(directory / "source.csv", payloads[0])
    write_once(directory / "LICENSE-Neil-Paine.txt", payloads[1])
    manifest = {"schema_version": 1, "source": "neil-paine-nba-elo", "url": SOURCE_URL,
                "git_commit": COMMIT, "sha256": SOURCE_SHA256, "bytes": len(payloads[0]),
                "license_url": LICENSE_URL, "license_sha256": LICENSE_SHA256,
                "license": "MIT; original FiveThirtyEight data attribution CC BY 4.0 retained",
                "original_license_url": "https://github.com/fivethirtyeight/data/blob/master/LICENSE",
                "attribution": ATTRIBUTION, "retrieved_at": retrieved,
                "historical_publication_time": None, "historical_availability_verified": False,
                "source_approval": "explicit archive MIT grant; retain upstream attribution",
                "date_precision": "calendar_date_only", "advanced_statistics_imported": False}
    write_once(manifest_path, json.dumps(manifest, indent=2, sort_keys=True).encode())
    return manifest_path


def verify_bundle(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if (manifest["url"], manifest["sha256"], manifest["git_commit"]) != (
            SOURCE_URL, SOURCE_SHA256, COMMIT):
        raise ValueError("Unapproved source manifest")
    if sha256((directory / "source.csv").read_bytes()) != SOURCE_SHA256:
        raise ValueError("Source checksum mismatch")
    if (manifest["license_url"] != LICENSE_URL or manifest["license_sha256"] != LICENSE_SHA256
            or sha256((directory / "LICENSE-Neil-Paine.txt").read_bytes()) != LICENSE_SHA256):
        raise ValueError("License checksum mismatch")
    received = datetime.fromisoformat(manifest["retrieved_at"])
    if received.utcoffset() is None or received > datetime.now(UTC):
        raise ValueError("Invalid acquisition timestamp")
    return manifest


def normalize(directory: Path, start: date, end: date) -> tuple[list[BasicResult], dict, dict]:
    manifest = verify_bundle(directory)
    raw = (directory / "source.csv").read_text()
    results, parsing = parse_neil_paine(list(csv.DictReader(io.StringIO(raw))),
                                      manifest["sha256"],
                                      datetime.fromisoformat(manifest["retrieved_at"]), start, end)
    report = audit(results, start, end, parsing)
    report["source_manifest"] = manifest
    report["parsing"] = parsing
    normalized = json.dumps([r.model_dump(mode="json") for r in results],
                            sort_keys=True, indent=2).encode()
    report["normalized_sha256"] = sha256(normalized)
    report["parser_version"] = "basic-results-v1"
    report_id = sha256(json.dumps(report, sort_keys=True).encode())
    write_once(directory / f"{report_id}.results.json", normalized)
    write_once(directory / f"{report_id}.audit.json", json.dumps(report, indent=2, sort_keys=True).encode())
    return results, report, manifest


def persist(session: Session, results: list[BasicResult], manifest: dict, report: dict) -> dict:
    """Fail the batch closed on structural defects; completeness remains a separate gate."""
    if report["structural_status"] != "PASS" or report["errors"]:
        raise ValueError("Structurally invalid batch; inspect audit, no rows persisted")
    if any(r.source_snapshot_sha256 != manifest["sha256"] for r in results):
        raise ValueError("Record provenance does not match source manifest")
    existing = session.get(ResultSourceSnapshot, manifest["sha256"])
    if existing is None:
        session.add(ResultSourceSnapshot(sha256=manifest["sha256"], source=manifest["source"],
                                        retrieved_at=datetime.fromisoformat(manifest["retrieved_at"]),
                                        manifest=manifest))
    elif existing.manifest != manifest:
        raise ValueError("Source snapshot manifest conflict")
    inserted, duplicates = 0, 0
    for record in results:
        row = session.scalar(select(BasicResultRow).where(
            BasicResultRow.snapshot_sha256 == manifest["sha256"],
            BasicResultRow.game_key == record.game_key))
        payload = record.model_dump(mode="json")
        if row is not None:
            if row.payload != payload:
                raise ValueError("Immutable result conflict")
            duplicates += 1
        else:
            session.add(BasicResultRow(snapshot_sha256=manifest["sha256"],
                                       game_key=record.game_key, payload=payload))
            inserted += 1
    session.flush()
    return {"inserted": inserted, "duplicates": duplicates,
            "advanced_statistics_imported": False}
