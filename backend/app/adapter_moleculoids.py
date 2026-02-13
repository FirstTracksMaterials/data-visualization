"""Convert molblock to Moleculoids JSON scene format."""
from typing import Any

from rdkit import Chem


def molblock_to_moleculoids_json(molblock: str) -> dict[str, Any]:
    """Convert a single MOL block to Moleculoids POST /scenes JSON body."""
    mol = Chem.MolFromMolBlock(molblock)
    if mol is None:
        raise ValueError("Invalid molblock")
    conf = mol.GetConformer()
    positions = []
    atomic_numbers = []
    for i in range(mol.GetNumAtoms()):
        pos = conf.GetAtomPosition(i)
        positions.append([float(pos.x), float(pos.y), float(pos.z)])
        atomic_numbers.append(int(mol.GetAtomWithIdx(i).GetAtomicNum()))
    bonds_indices = []
    bonds_orders = []
    for b in mol.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        bonds_indices.append([i, j])
        order = b.GetBondTypeAsDouble()
        if order == 1.5:
            bonds_orders.append(1.5)
        else:
            bonds_orders.append(int(order))
    return {
        "atoms": {
            "positions": positions,
            "atomic_numbers": atomic_numbers,
            "count": len(positions),
        },
        "bonds": {
            "indices": bonds_indices,
            "orders": bonds_orders,
            "count": len(bonds_indices),
        },
        "metadata": {"name": "molecule"},
    }
