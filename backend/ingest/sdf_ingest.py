"""Ingest SDF.gz / SDF files: extract hot columns + molblock + cold blobs into DB."""
import gzip
import io
from pathlib import Path
from typing import Any, Iterator

from rdkit import Chem

# Hot columns from SDF (spec)
HOT_TAGS = {
    "PUBCHEM_CONFORMER_ID": "conformer_id",
    "PUBCHEM_MMFF94_ENERGY": "mmff94_energy",
    "PUBCHEM_CONFORMER_RMSD": "conformer_rmsd",
    "PUBCHEM_EFFECTIVE_ROTOR_COUNT": "effective_rotor_count",
    "PUBCHEM_SHAPE_VOLUME": "shape_volume",
    "PUBCHEM_SHAPE_SELFOVERLAP": "shape_selfoverlap",
    "PUBCHEM_HEAVY_ATOM_COUNT": "heavy_atom_count",
    "PUBCHEM_COMPONENT_COUNT": "component_count",
}
# Cold: store as raw blob (we can gzip in DB layer)
COLD_TAGS = [
    "PUBCHEM_SHAPE_FINGERPRINT",
    "PUBCHEM_PHARMACOPHORE_FEATURES",
    "PUBCHEM_MMFF94_PARTIAL_CHARGES",
    "PUBCHEM_COORDINATE_TYPE",
]


def _read_molblock_and_props(supplier) -> Iterator[tuple[int, str, dict[str, Any], dict[str, bytes | None]]]:
    """Yield (cid, molblock, hot_dict, cold_dict) for each molecule."""
    for mol in supplier:
        if mol is None:
            continue
        cid = mol.GetProp("PUBCHEM_COMPOUND_CID") if mol.HasProp("PUBCHEM_COMPOUND_CID") else None
        if not cid:
            continue
        try:
            cid_int = int(float(cid))
        except (TypeError, ValueError):
            continue
        try:
            molblock = Chem.MolToMolBlock(mol)
        except Exception:
            continue
        hot = {}
        for tag, key in HOT_TAGS.items():
            if mol.HasProp(tag):
                val = mol.GetProp(tag)
                try:
                    if key in ("mmff94_energy", "conformer_rmsd", "shape_volume", "shape_selfoverlap"):
                        hot[key] = float(val)
                    elif key in ("effective_rotor_count", "heavy_atom_count", "component_count"):
                        hot[key] = int(float(val))
                    else:
                        hot[key] = val
                except (TypeError, ValueError):
                    hot[key] = None
            else:
                hot[key] = None
        cold = {}
        for tag in COLD_TAGS:
            if mol.HasProp(tag):
                v = mol.GetProp(tag)
                cold[tag] = v.encode("utf-8") if isinstance(v, str) else bytes(v)
            else:
                cold[tag] = None
        yield cid_int, molblock, hot, cold


def iter_sdf_records(path: str | Path) -> Iterator[tuple[int, str, dict[str, Any], dict[str, bytes | None]]]:
    """Open SDF (or .gz) and yield (cid, molblock, hot_dict, cold_dict) per record."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"SDF not found: {path}")
    if path.suffix == ".gz" or path.name.endswith(".sdf.gz"):
        with gzip.open(path, "rb") as f:
            content = f.read()
    else:
        content = path.read_bytes()
    supplier = Chem.MolFromMolBlock
    # SDMolSupplier from block
    block = content.decode("utf-8", errors="replace")
    current = []
    for line in block.splitlines():
        current.append(line)
        if line.strip() == "$$$$":
            mol_block = "\n".join(current)
            current = []
            mol = Chem.MolFromMolBlock(mol_block)
            if mol is None:
                continue
            cid = mol.GetProp("PUBCHEM_COMPOUND_CID") if mol.HasProp("PUBCHEM_COMPOUND_CID") else None
            if not cid:
                continue
            hot = {}
            for tag, key in HOT_TAGS.items():
                if mol.HasProp(tag):
                    val = mol.GetProp(tag)
                    try:
                        if key in ("mmff94_energy", "conformer_rmsd", "shape_volume", "shape_selfoverlap"):
                            hot[key] = float(val)
                        elif key in ("effective_rotor_count", "heavy_atom_count", "component_count"):
                            hot[key] = int(float(val))
                        else:
                            hot[key] = val
                    except (TypeError, ValueError):
                        hot[key] = None
                else:
                    hot[key] = None
            cold = {}
            for ctag in COLD_TAGS:
                if mol.HasProp(ctag):
                    v = mol.GetProp(ctag)
                    cold[ctag] = v.encode("utf-8") if isinstance(v, str) else bytes(v)
                else:
                    cold[ctag] = None
            try:
                cid_int = int(float(cid))
            except (TypeError, ValueError):
                continue
            yield cid_int, mol_block, hot, cold


def iter_sdf_records_supplier(path: str | Path) -> Iterator[tuple[int, str, dict[str, Any], dict[str, bytes | None]]]:
    """Use RDKit SDMolSupplier on (decompressed) stream."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"SDF not found: {path}")
    if path.suffix == ".gz" or str(path).endswith(".sdf.gz"):
        with gzip.open(path, "rb") as f:
            data = f.read()
        supp = Chem.SDMolSupplier(io.BytesIO(data))
    else:
        supp = Chem.SDMolSupplier(str(path))
    yield from _read_molblock_and_props(supp)
