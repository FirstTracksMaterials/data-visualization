"""CLI: migrate, ingest CSV, ingest SDF."""
import asyncio
import sys
import uuid
from pathlib import Path

import asyncpg

from . import db as ingest_db
from . import csv_ingest, sdf_ingest


def _conn_url() -> str:
    import os
    url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/molecule_explorer")
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def migrate() -> None:
    """Run migrations."""
    conn = await asyncpg.connect(_conn_url())
    try:
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        await ingest_db.run_migration(conn, migrations_dir)
        print("Migrations OK")
    finally:
        await conn.close()


async def ingest_csv(dataset_id: str, csv_path: str, dataset_name: str | None = None) -> None:
    """Ingest one CSV manifest into dataset + discovered_molecule."""
    df, missing = csv_ingest.validate_and_load_csv(csv_path)
    if missing:
        print(f"Missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)
    run_id = str(uuid.uuid4())
    rows = csv_ingest.build_molecule_rows(df, dataset_id, run_id)
    stats = csv_ingest.coverage_stats(df)
    stats["molecules_upserted"] = len(rows)

    conn = await asyncpg.connect(_conn_url())
    try:
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        await ingest_db.run_migration(conn, migrations_dir)
        await ingest_db.ensure_dataset_and_run(conn, dataset_id, dataset_name or dataset_id, run_id)
        await ingest_db.upsert_molecules(conn, rows)
        await ingest_db.finish_run(conn, run_id, stats)
        print(f"CSV ingest done: dataset_id={dataset_id}, run_id={run_id}, rows={len(rows)}")
        print("Stats:", stats)
    finally:
        await conn.close()


async def ingest_sdf(dataset_id: str, sdf_paths: list[str], run_id: str | None = None) -> None:
    """Ingest SDF file(s) into molecule_geometry + molecule_geometry_cold. Only CIDs present in discovered_molecule are stored."""
    conn = await asyncpg.connect(_conn_url())
    try:
        # Fetch valid CIDs for this dataset
        valid_cids = set(
            row["cid"]
            for row in await conn.fetch(
                "SELECT cid FROM discovered_molecule WHERE dataset_id = $1", dataset_id
            )
        )
        if not run_id:
            run_id = str(uuid.uuid4())
        count = 0
        skipped = 0
        for path in sdf_paths:
            for cid, molblock, hot, cold in sdf_ingest.iter_sdf_records(path):
                if cid not in valid_cids:
                    skipped += 1
                    continue
                await ingest_db.upsert_geometry(conn, dataset_id, run_id, cid, hot, molblock, cold)
                count += 1
                if count % 500 == 0:
                    print(f"  SDF: {count} geometry rows...")
        print(f"SDF ingest done: dataset_id={dataset_id}, geometry rows={count}, skipped (not in manifest)={skipped}")
    finally:
        await conn.close()


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Molecule Explorer ingest")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Run DB migrations")
    csv_p = sub.add_parser("csv", help="Ingest CSV manifest")
    csv_p.add_argument("--dataset-id", required=True, help="Dataset ID")
    csv_p.add_argument("--name", default=None, help="Dataset display name")
    csv_p.add_argument("csv_path", help="Path to manifest CSV")
    sdf_p = sub.add_parser("sdf", help="Ingest SDF file(s)")
    sdf_p.add_argument("--dataset-id", required=True, help="Dataset ID (must already have CSV loaded)")
    sdf_p.add_argument("sdf_paths", nargs="+", help="Paths to SDF or SDF.gz files")
    args = p.parse_args()

    if args.cmd == "migrate":
        asyncio.run(migrate())
    elif args.cmd == "csv":
        asyncio.run(ingest_csv(args.dataset_id, args.csv_path, args.name))
    elif args.cmd == "sdf":
        asyncio.run(ingest_sdf(args.dataset_id, args.sdf_paths))


if __name__ == "__main__":
    main()
