"""Ingest CSV manifest into dataset + discovered_molecule."""
import csv
import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .parse import parse_discovery_seed

REQUIRED_COLUMNS = [
    "PubChem_CID",
    "SMILES",
    "InChIKey",
    "molecular_formula",
    "molecular_weight",
    "exact_mass",
    "discovery_method",
    "discovery_seed",
]
COLUMN_MAP = {
    "PubChem_CID": "cid",
    "SMILES": "smiles",
    "InChIKey": "inchi_key",
    "molecular_formula": "molecular_formula",
    "molecular_weight": "molecular_weight",
    "exact_mass": "exact_mass",
    "XLogP3": "xlogp3",
    "TPSA": "tpsa",
    "HBA": "hba",
    "HBD": "hbd",
    "rotatable_bonds": "rotatable_bonds",
    "discovery_method": "discovery_method",
    "discovery_seed": "discovery_seed",
    "name": "name",
}


def normalize_discovery_method(method: str | None) -> str:
    """Map similarity -> sim2d for V1 if not derivable."""
    if not method or not str(method).strip():
        return "substructure"
    m = str(method).strip().lower()
    if m in ("substructure", "sim2d", "sim3d"):
        return m
    if m == "similarity":
        return "sim2d"
    return m


def validate_and_load_csv(path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """Load CSV and return (df, list of missing required column names)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    return df, missing


def build_molecule_rows(
    df: pd.DataFrame, dataset_id: str, run_id: str
) -> list[dict[str, Any]]:
    """Build list of dicts for discovered_molecule insert."""
    rows = []
    for _, r in df.iterrows():
        cid = r.get("PubChem_CID")
        if pd.isna(cid):
            continue
        try:
            cid = int(float(cid))
        except (TypeError, ValueError):
            continue
        seed_raw = r.get("discovery_seed")
        seed_name, seed_smiles = parse_discovery_seed(
            None if pd.isna(seed_raw) else str(seed_raw)
        )
        method = normalize_discovery_method(
            None if pd.isna(r.get("discovery_method")) else str(r["discovery_method"])
        )
        rows.append({
            "dataset_id": dataset_id,
            "cid": cid,
            "smiles": None if pd.isna(r.get("SMILES")) else str(r["SMILES"]).strip() or None,
            "inchi_key": None if pd.isna(r.get("InChIKey")) else str(r["InChIKey"]).strip() or None,
            "molecular_formula": None if pd.isna(r.get("molecular_formula")) else str(r["molecular_formula"]).strip() or None,
            "molecular_weight": None if pd.isna(r.get("molecular_weight")) else float(r["molecular_weight"]),
            "exact_mass": None if pd.isna(r.get("exact_mass")) else float(r["exact_mass"]),
            "xlogp3": None if pd.isna(r.get("XLogP3")) else float(r["XLogP3"]),
            "tpsa": None if pd.isna(r.get("TPSA")) else float(r["TPSA"]),
            "hba": None if pd.isna(r.get("HBA")) else int(r["HBA"]),
            "hbd": None if pd.isna(r.get("HBD")) else int(r["HBD"]),
            "rotatable_bonds": None if pd.isna(r.get("rotatable_bonds")) else int(r["rotatable_bonds"]),
            "discovery_method": method,
            "discovery_seed": None if pd.isna(seed_raw) else str(seed_raw).strip() or None,
            "seed_name": seed_name,
            "seed_smiles": seed_smiles,
            "name": None if pd.isna(r.get("name")) else str(r["name"]).strip() or None,
            "ingest_run_id": run_id,
        })
    return rows


def coverage_stats(df: pd.DataFrame) -> dict[str, Any]:
    """Return coverage stats for required/key columns."""
    total = len(df)
    stats = {"total_rows": total}
    for col in ["PubChem_CID", "SMILES", "InChIKey", "molecular_formula", "molecular_weight", "discovery_method", "discovery_seed"]:
        if col not in df.columns:
            stats[col] = 0
            continue
        non_null = df[col].notna().sum()
        stats[col] = int(non_null)
        if total > 0:
            stats[f"{col}_pct"] = round(100.0 * non_null / total, 2)
    return stats
