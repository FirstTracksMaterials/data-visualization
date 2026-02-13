"""Parse discovery_seed into seed_name and seed_smiles (split on first ':')."""
from typing import Tuple


def parse_discovery_seed(discovery_seed: str | None) -> Tuple[str | None, str | None]:
    """Return (seed_name, seed_smiles). For CID-only seeds, seed_smiles may be None."""
    if not discovery_seed or not str(discovery_seed).strip():
        return None, None
    s = str(discovery_seed).strip()
    if ":" in s:
        name, _, rest = s.partition(":")
        return name.strip() or None, rest.strip() or None
    return s, None
