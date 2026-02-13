"""ETL DB helpers using asyncpg (sync wrapper for CLI)."""
import asyncio
from pathlib import Path
from typing import Any

import asyncpg


def _get_conn_url(database_url: str) -> str:
    """Convert sqlalchemy async URL to asyncpg URL."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


async def run_migration(conn, migrations_dir: Path) -> None:
    """Run 001_initial.sql if present (statement by statement)."""
    sql_file = migrations_dir / "001_initial.sql"
    if not sql_file.exists():
        return
    sql = sql_file.read_text()
    # Split only on ";\n" to avoid splitting inside COMMENT strings
    statements = []
    for part in sql.replace(";\n", "\x00").split("\x00"):
        part = part.strip()
        while part and part.split("\n")[0].strip().startswith("--"):
            part = "\n".join(part.split("\n")[1:]).strip()
        if not part:
            continue
        if not part.rstrip().endswith(";"):
            part = part + ";"
        statements.append(part)
    for stmt in statements:
        if stmt.strip() != ";":
            await conn.execute(stmt)


async def ensure_dataset_and_run(
    conn: asyncpg.Connection,
    dataset_id: str,
    dataset_name: str,
    run_id: str,
) -> None:
    """Insert or update dataset; insert ingest_run."""
    await conn.execute(
        """
        INSERT INTO dataset (dataset_id, name, ingest_run_id, created_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (dataset_id) DO UPDATE SET
            name = EXCLUDED.name,
            ingest_run_id = EXCLUDED.ingest_run_id
        """,
        dataset_id,
        dataset_name or dataset_id,
        run_id,
    )
    await conn.execute(
        """
        INSERT INTO ingest_run (run_id, dataset_id, started_at, status, created_at)
        VALUES ($1, $2, now(), 'running', now())
        ON CONFLICT (run_id) DO UPDATE SET status = 'running', started_at = now()
        """,
        run_id,
        dataset_id,
    )


async def upsert_molecules(conn: asyncpg.Connection, rows: list[dict[str, Any]]) -> None:
    """Upsert discovered_molecule rows."""
    for r in rows:
        await conn.execute(
            """
            INSERT INTO discovered_molecule (
                dataset_id, cid, smiles, inchi_key, molecular_formula,
                molecular_weight, exact_mass, xlogp3, tpsa, hba, hbd, rotatable_bonds,
                discovery_method, discovery_seed, seed_name, seed_smiles, name, ingest_run_id, created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, now()
            )
            ON CONFLICT (dataset_id, cid) DO UPDATE SET
                smiles = EXCLUDED.smiles,
                inchi_key = EXCLUDED.inchi_key,
                molecular_formula = EXCLUDED.molecular_formula,
                molecular_weight = EXCLUDED.molecular_weight,
                exact_mass = EXCLUDED.exact_mass,
                xlogp3 = EXCLUDED.xlogp3,
                tpsa = EXCLUDED.tpsa,
                hba = EXCLUDED.hba,
                hbd = EXCLUDED.hbd,
                rotatable_bonds = EXCLUDED.rotatable_bonds,
                discovery_method = EXCLUDED.discovery_method,
                discovery_seed = EXCLUDED.discovery_seed,
                seed_name = EXCLUDED.seed_name,
                seed_smiles = EXCLUDED.seed_smiles,
                name = EXCLUDED.name,
                ingest_run_id = EXCLUDED.ingest_run_id
            """,
            r["dataset_id"],
            r["cid"],
            r["smiles"],
            r["inchi_key"],
            r["molecular_formula"],
            r["molecular_weight"],
            r["exact_mass"],
            r["xlogp3"],
            r["tpsa"],
            r["hba"],
            r["hbd"],
            r["rotatable_bonds"],
            r["discovery_method"],
            r["discovery_seed"],
            r["seed_name"],
            r["seed_smiles"],
            r["name"],
            r["ingest_run_id"],
        )


async def finish_run(conn: asyncpg.Connection, run_id: str, stats: dict[str, Any]) -> None:
    """Set ingest_run finished_at and stats."""
    import json
    await conn.execute(
        """
        UPDATE ingest_run
        SET finished_at = now(), status = 'completed', stats = $2::jsonb
        WHERE run_id = $1
        """,
        run_id,
        json.dumps(stats),
    )


async def upsert_geometry(
    conn: asyncpg.Connection,
    dataset_id: str,
    run_id: str,
    cid: int,
    hot: dict[str, Any],
    molblock: str,
    cold_blobs: dict[str, bytes | None],
) -> None:
    """Insert or update molecule_geometry and molecule_geometry_cold."""
    await conn.execute(
        """
        INSERT INTO molecule_geometry (
            dataset_id, cid, conformer_id, mmff94_energy, conformer_rmsd,
            effective_rotor_count, shape_volume, shape_selfoverlap,
            heavy_atom_count, component_count, ingest_run_id, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, now())
        ON CONFLICT (dataset_id, cid) DO UPDATE SET
            conformer_id = EXCLUDED.conformer_id,
            mmff94_energy = EXCLUDED.mmff94_energy,
            conformer_rmsd = EXCLUDED.conformer_rmsd,
            effective_rotor_count = EXCLUDED.effective_rotor_count,
            shape_volume = EXCLUDED.shape_volume,
            shape_selfoverlap = EXCLUDED.shape_selfoverlap,
            heavy_atom_count = EXCLUDED.heavy_atom_count,
            component_count = EXCLUDED.component_count,
            ingest_run_id = EXCLUDED.ingest_run_id
        """,
        dataset_id,
        cid,
        hot.get("conformer_id"),
        hot.get("mmff94_energy"),
        hot.get("conformer_rmsd"),
        hot.get("effective_rotor_count"),
        hot.get("shape_volume"),
        hot.get("shape_selfoverlap"),
        hot.get("heavy_atom_count"),
        hot.get("component_count"),
        run_id,
    )
    # Cold: ensure row exists in geometry_cold (FK references geometry)
    await conn.execute(
        """
        INSERT INTO molecule_geometry_cold (dataset_id, cid, molblock, shape_fingerprint, pharmacophore_features, mmff94_partial_charges, coordinate_type, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, now())
        ON CONFLICT (dataset_id, cid) DO UPDATE SET
            molblock = EXCLUDED.molblock,
            shape_fingerprint = EXCLUDED.shape_fingerprint,
            pharmacophore_features = EXCLUDED.pharmacophore_features,
            mmff94_partial_charges = EXCLUDED.mmff94_partial_charges,
            coordinate_type = EXCLUDED.coordinate_type
        """,
        dataset_id,
        cid,
        molblock,
        cold_blobs.get("PUBCHEM_SHAPE_FINGERPRINT"),
        cold_blobs.get("PUBCHEM_PHARMACOPHORE_FEATURES"),
        cold_blobs.get("PUBCHEM_MMFF94_PARTIAL_CHARGES"),
        cold_blobs.get("PUBCHEM_COORDINATE_TYPE"),
    )


def run_async(coro):
    return asyncio.run(coro)
