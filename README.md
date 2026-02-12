# Molecule Explorer (Local Prototype)

A locally hosted web app for **browsing and visualizing** PubChem-derived molecules: drill down by family → seed → method → molecules, inspect metadata and descriptors, and view 3D conformers.

## Goals

- **Structured exploration:** Family → Seed → Method → Molecules → Molecule detail + 3D
- **Technical use:** Provenance, descriptors, 3D metadata, and aggregation views
- **Clean spine:** DB + API contracts that can later grow into search, QC, and cloud

## Stack (V1)

- **ETL:** Ingest CSV manifest(s) + SDF.gz/SDF.zip into a local Postgres DB (hot/cold split)
- **Backend:** FastAPI — browse, aggregates, molecule detail, geometry (molblock)
- **Frontend:** Drilldown explorer, linked histograms, embedded 3D viewer
- **DevEx:** Docker Compose, one-command ingest, migrations

## Repo contents

- **Example inputs** (for development and tests):
  - `discovered_pubchem_10k.csv` — molecule manifest (~10k rows)
  - `pubchem_cid_batch_*.sdf.gz` — PubChem 3D SDF batches
- **Application code** (to be added): `backend/`, `frontend/`, `docker-compose.yml`, ingest CLI, etc.

## Data contracts

- **CSV manifest:** Required columns include `PubChem_CID`, `SMILES`, `InChIKey`, `molecular_formula`, `molecular_weight`, `exact_mass`, `XLogP3`, `TPSA`, `HBA`, `HBD`, `rotatable_bonds`, `discovery_method`, `discovery_seed`. `discovery_seed` is parsed as `seed_name` and `seed_smiles` (split on first `:`).
- **SDF:** Records joined by `PUBCHEM_COMPOUND_CID`; hot fields (e.g. MMFF94_ENERGY, SHAPE_VOLUME) and cold (molblock, shape fingerprint, etc.) stored per spec.

## Status

In development. See the engineering spec and implementation plan for full details.

## License

See repository license.
