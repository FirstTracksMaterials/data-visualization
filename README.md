# Molecule Explorer (Local Prototype)

A locally hosted web app for **browsing and visualizing** PubChem-derived molecules: drill down by family → seed → method → molecules, inspect metadata and descriptors, and view 3D conformers.

## Goals

- **Structured exploration:** Family → Seed → Method → Molecules → Molecule detail + 3D
- **Technical use:** Provenance, descriptors, 3D metadata, and aggregation views
- **Clean spine:** DB + API contracts that can later grow into search, QC, and cloud

## Stack (V1)

- **ETL:** Ingest CSV manifest(s) + SDF.gz/SDF.zip into a local Postgres DB (hot/cold split)
- **Backend:** FastAPI — browse, aggregates, molecule detail, geometry (molblock + Moleculoids JSON)
- **Frontend:** Vite app — drilldown explorer, molecule detail, embedded 3D viewer (Moleculoids)
- **DevEx:** Docker Compose (Postgres + backend), Makefile for one-command ingest and run

## Repo contents

| Path | Description |
|------|-------------|
| `tests/data/` | Example inputs: `discovered_pubchem_10k.csv` (~10k rows), `pubchem_cid_batch_*.sdf.gz` |
| `assets/` | First Tracks Materials logo (`first-tracks-materials-logo.png`) |
| `backend/` | FastAPI app, ingest CLI (CSV + SDF), migrations, Moleculoids JSON adapter |
| `frontend/` | Vite app: drilldown (dataset → families → seeds → molecules), detail panel, 3D viewer |
| `docker-compose.yml` | Postgres + backend services |
| `Makefile` | `migrate`, `ingest-csv`, `ingest-sdf`, `ingest`, `up`, `backend-run` |
| `index.html` | Static landing page (dark theme, logo) |

## UI theme

- **Dark mode** with First Tracks Materials brand colors
- **Primary blue:** `#4472c4` — headings, links, accents
- **Accent orange:** `#c17636` — CTAs, highlights
- **Logo:** `assets/first-tracks-materials-logo.png` (and `frontend/public/logo.png` for the app)

## Data contracts

- **CSV manifest:** Required columns: `PubChem_CID`, `SMILES`, `InChIKey`, `molecular_formula`, `molecular_weight`, `exact_mass`, `discovery_method`, `discovery_seed`. Optional: `XLogP3`, `TPSA`, `HBA`, `HBD`, `rotatable_bonds`. `discovery_seed` is parsed as `seed_name` and `seed_smiles` (split on first `:`).
- **SDF:** Joined by `PUBCHEM_COMPOUND_CID`. Hot columns: conformer_id, mmff94_energy, shape_volume, etc. Cold: molblock, shape_fingerprint, pharmacophore_features, mmff94_partial_charges.

---

## How to run

### Prerequisites

- **Docker** (for Postgres), or a running Postgres instance
- **Python 3.10+** with `asyncpg`, `pandas`, `rdkit`, `fastapi`, `uvicorn` (see `backend/requirements.txt`)
- **Node.js 18+** (for the frontend)
- **Moleculoids** (optional, for 3D): run from a local clone on port 8001

### 1. Start Postgres

```bash
docker compose up -d postgres
```

Wait for the DB to be ready (a few seconds). Or set `DATABASE_URL` to an existing Postgres instance and ensure the database `molecule_explorer` exists.

### 2. Run migrations

```bash
make migrate
```

This applies `backend/migrations/001_initial.sql` (dataset, ingest_run, discovered_molecule, molecule_geometry, molecule_geometry_cold).

### 3. Ingest data

**Full ingest (CSV + SDF):**

```bash
make ingest DATASET_ID=photoinitiators_10k
```

This uses `tests/data/discovered_pubchem_10k.csv` and the two SDF files in `tests/data/`. To use your own paths:

```bash
make ingest-csv DATASET_ID=my_dataset CSV=path/to/manifest.csv
make ingest-sdf DATASET_ID=my_dataset SDF="path/to/a.sdf.gz path/to/b.sdf.gz"
```

Geometry is only stored for CIDs that exist in the CSV manifest. The sample SDF batches may not overlap the sample CSV CIDs, so geometry rows can be 0 until you use matching data.

### 4. Start the backend API

```bash
make backend-run
```

API runs at **http://localhost:8000**. Endpoints: `GET /datasets`, `GET /datasets/{id}/families`, `GET /datasets/{id}/seeds`, `POST /datasets/{id}/molecules/query`, `POST /datasets/{id}/molecules/aggregates`, `GET /datasets/{id}/molecules/{cid}`, `GET /datasets/{id}/molecules/{cid}/geometry?format=molblock|moleculoids_json`, `GET /runs`, `GET /runs/{run_id}`, `GET /health`.

### 5. Start the frontend

```bash
cd frontend && npm install && npm run dev
```

App runs at **http://localhost:5173**. Select a dataset, then family → seeds → molecule table; click a row for detail and (if geometry exists) 3D.

**Optional env (e.g. in `frontend/.env`):**

- `VITE_API_URL=http://localhost:8000` — backend API (default)
- `VITE_MOLECULOIDS_URL=http://localhost:8001` — Moleculoids server for 3D

### 6. 3D viewer (Moleculoids)

To load 3D for a molecule, Moleculoids must be running. From your [moleculoids](https://github.com/FirstTracksMaterials/moleculoids) clone:

```bash
cd /path/to/moleculoids && moleculoids serve --no-open --port 8001
```

Then open a molecule in the app; the frontend fetches geometry as Moleculoids JSON, POSTs it to Moleculoids, and embeds `<moleculoids-viewer>`.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/molecule_explorer` | Postgres connection (use `postgresql://` for the ingest CLI; backend accepts `postgresql+asyncpg://`). |
| `MOLECULOIDS_BASE_URL` | `http://localhost:8001` | Used by the backend (e.g. for future proxy); frontend uses `VITE_MOLECULOIDS_URL`. |

---

## Status

V1 implemented: ETL (CSV + SDF, hot/cold split), migrations, FastAPI with all spec’d endpoints, molblock → Moleculoids JSON adapter, frontend drilldown and molecule detail with optional 3D via Moleculoids.

## License

See repository license.
