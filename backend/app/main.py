"""FastAPI app: datasets, families, seeds, molecules query/aggregates/detail/geometry, runs."""
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .adapter_moleculoids import molblock_to_moleculoids_json

# ---------------------------------------------------------------------------
# DB pool
# ---------------------------------------------------------------------------

def _pg_url() -> str:
    u = settings.database_url
    if u.startswith("postgresql+asyncpg://"):
        u = u.replace("postgresql+asyncpg://", "postgresql://", 1)
    return u


pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(_pg_url(), min_size=1, max_size=10)
    yield
    if pool:
        await pool.close()


async def get_conn():
    async with pool.acquire() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class Page(BaseModel):
    limit: int = 100
    offset: int = 0


class SortItem(BaseModel):
    field: str
    dir: str = "asc"


class MoleculesQueryBody(BaseModel):
    seed_name: str | None = None
    methods: list[str] | None = None
    ranges: dict[str, list[float]] | None = None
    sort: list[SortItem] | None = None
    page: Page | None = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Molecule Explorer API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

@app.get("/datasets")
async def list_datasets(conn: asyncpg.Connection = Depends(get_conn)):
    rows = await conn.fetch(
        """
        SELECT d.dataset_id, d.name, d.created_at,
               (SELECT COUNT(*) FROM discovered_molecule m WHERE m.dataset_id = d.dataset_id) AS molecule_count
        FROM dataset d
        ORDER BY d.created_at DESC
        """
    )
    return {
        "datasets": [
            {
                "dataset_id": r["dataset_id"],
                "name": r["name"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "molecule_count": r["molecule_count"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@app.get("/datasets/{dataset_id}/families")
async def list_families(dataset_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    rows = await conn.fetch(
        "SELECT DISTINCT seed_name AS family FROM discovered_molecule WHERE dataset_id = $1 AND seed_name IS NOT NULL ORDER BY seed_name",
        dataset_id,
    )
    return {"families": [r["family"] for r in rows], "dataset_id": dataset_id}


@app.get("/datasets/{dataset_id}/seeds")
async def list_seeds(
    dataset_id: str,
    family: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_conn),
):
    if family:
        rows = await conn.fetch(
            "SELECT DISTINCT discovery_seed, seed_name, seed_smiles FROM discovered_molecule WHERE dataset_id = $1 AND seed_name = $2 ORDER BY discovery_seed",
            dataset_id,
            family,
        )
    else:
        rows = await conn.fetch(
            "SELECT DISTINCT discovery_seed, seed_name, seed_smiles FROM discovered_molecule WHERE dataset_id = $1 ORDER BY seed_name, discovery_seed",
            dataset_id,
        )
    return {
        "seeds": [
            {"discovery_seed": r["discovery_seed"], "seed_name": r["seed_name"], "seed_smiles": r["seed_smiles"]}
            for r in rows
        ],
        "dataset_id": dataset_id,
    }


# ---------------------------------------------------------------------------
# Molecules query (filter + sort + page)
# ---------------------------------------------------------------------------

def _build_where(params: dict, body: MoleculesQueryBody) -> tuple[str, list]:
    conditions = ["m.dataset_id = $1"]
    args: list[Any] = [params["dataset_id"]]
    idx = 2
    if body.seed_name:
        conditions.append(f"m.seed_name = ${idx}")
        args.append(body.seed_name)
        idx += 1
    if body.methods:
        conditions.append(f"m.discovery_method = ANY(${idx}::text[])")
        args.append(body.methods)
        idx += 1
    if body.ranges:
        for field, pair in body.ranges.items():
            if len(pair) >= 2 and field in (
                "molecular_weight", "TPSA", "XLogP3", "HBA", "HBD", "rotatable_bonds",
                "mmff94_energy", "shape_volume",
            ):
                col = "m." + field if field in ("molecular_weight", "TPSA", "XLogP3", "HBA", "HBD", "rotatable_bonds") else "g." + field
                if field in ("mmff94_energy", "shape_volume"):
                    conditions.append(f"g.cid = m.cid AND g.{field} IS NOT NULL AND g.{field} >= ${idx} AND g.{field} <= ${idx+1}")
                else:
                    conditions.append(f"m.{field} IS NOT NULL AND m.{field} >= ${idx} AND m.{field} <= ${idx+1}")
                args.extend([float(pair[0]), float(pair[1])])
                idx += 2
    return " AND ".join(conditions), args


@app.post("/datasets/{dataset_id}/molecules/query")
async def query_molecules(
    dataset_id: str,
    body: MoleculesQueryBody,
    conn: asyncpg.Connection = Depends(get_conn),
):
    page = body.page or Page()
    where, args = _build_where({"dataset_id": dataset_id}, body)
    use_geom = (
        (body.ranges and any(k in ("mmff94_energy", "shape_volume") for k in body.ranges))
        or (body.sort and any(s.field in ("mmff94_energy", "shape_volume") for s in (body.sort or [])))
    )
    from_clause = "FROM discovered_molecule m"
    if use_geom:
        from_clause += " LEFT JOIN molecule_geometry g ON g.dataset_id = m.dataset_id AND g.cid = m.cid"
    order = "m.cid ASC"
    if body.sort and body.sort:
        parts = []
        for s in body.sort:
            col = f"g.{s.field}" if s.field in ("mmff94_energy", "shape_volume") else f"m.{s.field}"
            parts.append(f"{col} {'ASC' if s.dir == 'asc' else 'DESC'}")
        order = ", ".join(parts)
    n = len(args)
    args.extend([page.limit, page.offset])
    rows = await conn.fetch(
        f"""
        SELECT m.cid, m.smiles, m.inchi_key, m.molecular_formula, m.molecular_weight, m.exact_mass,
               m.xlogp3, m.tpsa, m.hba, m.hbd, m.rotatable_bonds, m.discovery_method, m.discovery_seed, m.seed_name, m.name
        {from_clause}
        WHERE {where}
        ORDER BY {order}
        LIMIT ${n + 1} OFFSET ${n + 2}
        """,
        *args,
    )
    total = await conn.fetchval(
        f"SELECT COUNT(*) {from_clause} WHERE {where}",
        *args[:n],
    )
    return {
        "molecules": [
            {
                "cid": r["cid"],
                "smiles": r["smiles"],
                "inchi_key": r["inchi_key"],
                "molecular_formula": r["molecular_formula"],
                "molecular_weight": r["molecular_weight"],
                "exact_mass": r["exact_mass"],
                "xlogp3": r["xlogp3"],
                "tpsa": r["tpsa"],
                "hba": r["hba"],
                "hbd": r["hbd"],
                "rotatable_bonds": r["rotatable_bonds"],
                "discovery_method": r["discovery_method"],
                "discovery_seed": r["discovery_seed"],
                "seed_name": r["seed_name"],
                "name": r["name"],
            }
            for r in rows
        ],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@app.post("/datasets/{dataset_id}/molecules/aggregates")
async def aggregates_molecules(
    dataset_id: str,
    body: MoleculesQueryBody,
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Return histogram bins for numeric fields. Request body can include same filters as query."""
    where, args = _build_where({"dataset_id": dataset_id}, body)
    from_clause = "FROM discovered_molecule m LEFT JOIN molecule_geometry g ON g.dataset_id = m.dataset_id AND g.cid = m.cid"
    fields = [
        ("molecular_weight", "m.molecular_weight"),
        ("TPSA", "m.tpsa"),
        ("XLogP3", "m.xlogp3"),
        ("HBA", "m.hba"),
        ("HBD", "m.hbd"),
        ("rotatable_bonds", "m.rotatable_bonds"),
        ("mmff94_energy", "g.mmff94_energy"),
        ("shape_volume", "g.shape_volume"),
    ]
    result = {}
    for name, col in fields:
        row = await conn.fetchrow(
            f"SELECT COUNT(*) AS n, MIN({col}) AS lo, MAX({col}) AS hi {from_clause} WHERE {where} AND {col} IS NOT NULL",
            *args,
        )
        if row and row["n"] and row["n"] > 0:
            result[name] = {"count": row["n"], "min": float(row["lo"]) if row["lo"] is not None else None, "max": float(row["hi"]) if row["hi"] is not None else None}
    return {"aggregates": result, "dataset_id": dataset_id}


@app.get("/datasets/{dataset_id}/molecules/{cid}")
async def get_molecule(
    dataset_id: str,
    cid: int,
    conn: asyncpg.Connection = Depends(get_conn),
):
    r = await conn.fetchrow(
        "SELECT cid, smiles, inchi_key, molecular_formula, molecular_weight, exact_mass, xlogp3, tpsa, hba, hbd, rotatable_bonds, discovery_method, discovery_seed, seed_name, seed_smiles, name FROM discovered_molecule WHERE dataset_id = $1 AND cid = $2",
        dataset_id,
        cid,
    )
    if not r:
        raise HTTPException(status_code=404, detail="Molecule not found")
    g = await conn.fetchrow(
        "SELECT conformer_id, mmff94_energy, conformer_rmsd, effective_rotor_count, shape_volume, shape_selfoverlap, heavy_atom_count, component_count FROM molecule_geometry WHERE dataset_id = $1 AND cid = $2",
        dataset_id,
        cid,
    )
    out = {
        "cid": r["cid"],
        "smiles": r["smiles"],
        "inchi_key": r["inchi_key"],
        "molecular_formula": r["molecular_formula"],
        "molecular_weight": r["molecular_weight"],
        "exact_mass": r["exact_mass"],
        "xlogp3": r["xlogp3"],
        "tpsa": r["tpsa"],
        "hba": r["hba"],
        "hbd": r["hbd"],
        "rotatable_bonds": r["rotatable_bonds"],
        "discovery_method": r["discovery_method"],
        "discovery_seed": r["discovery_seed"],
        "seed_name": r["seed_name"],
        "seed_smiles": r["seed_smiles"],
        "name": r["name"],
    }
    if g:
        out["geometry"] = {
            "conformer_id": g["conformer_id"],
            "mmff94_energy": g["mmff94_energy"],
            "conformer_rmsd": g["conformer_rmsd"],
            "effective_rotor_count": g["effective_rotor_count"],
            "shape_volume": g["shape_volume"],
            "shape_selfoverlap": g["shape_selfoverlap"],
            "heavy_atom_count": g["heavy_atom_count"],
            "component_count": g["component_count"],
        }
    return out


@app.get("/datasets/{dataset_id}/molecules/{cid}/geometry")
async def get_geometry(
    dataset_id: str,
    cid: int,
    format: str = Query("molblock", description="molblock or moleculoids_json"),
    conn: asyncpg.Connection = Depends(get_conn),
):
    cold = await conn.fetchrow(
        "SELECT molblock FROM molecule_geometry_cold WHERE dataset_id = $1 AND cid = $2",
        dataset_id,
        cid,
    )
    if not cold or not cold["molblock"]:
        raise HTTPException(status_code=404, detail="Geometry not found")
    molblock = cold["molblock"]
    if format == "moleculoids_json":
        try:
            data = molblock_to_moleculoids_json(molblock)
            return data
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return molblock


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@app.get("/runs")
async def list_runs(conn: asyncpg.Connection = Depends(get_conn)):
    rows = await conn.fetch(
        "SELECT run_id, dataset_id, started_at, finished_at, status, stats, created_at FROM ingest_run ORDER BY started_at DESC LIMIT 100"
    )
    return {
        "runs": [
            {
                "run_id": r["run_id"],
                "dataset_id": r["dataset_id"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
                "status": r["status"],
                "stats": r["stats"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@app.get("/runs/{run_id}")
async def get_run(run_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    r = await conn.fetchrow(
        "SELECT run_id, dataset_id, started_at, finished_at, status, stats, created_at FROM ingest_run WHERE run_id = $1",
        run_id,
    )
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": r["run_id"],
        "dataset_id": r["dataset_id"],
        "started_at": r["started_at"].isoformat() if r["started_at"] else None,
        "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
        "status": r["status"],
        "stats": r["stats"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
