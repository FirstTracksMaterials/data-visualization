.PHONY: migrate ingest-csv ingest-sdf ingest up dev backend-run

# Default DB URL (override with export DATABASE_URL=...)
export DATABASE_URL ?= postgresql://postgres:postgres@localhost:5432/molecule_explorer

# Ingest: run migrations, load CSV, then SDF. Example:
#   make ingest DATASET_ID=photoinitiators_10k CSV=tests/data/discovered_pubchem_10k.csv SDF="tests/data/*.sdf.gz"
DATASET_ID ?= default
CSV ?= tests/data/discovered_pubchem_10k.csv
SDF ?= tests/data/pubchem_cid_batch_0.sdf.gz tests/data/pubchem_cid_batch_10005000.sdf.gz

migrate:
	cd backend && python3 -m ingest.cli migrate

ingest-csv:
	PYTHONPATH=backend python3 -m ingest.cli csv --dataset-id $(DATASET_ID) $(CSV)

ingest-sdf:
	PYTHONPATH=backend python3 -m ingest.cli sdf --dataset-id $(DATASET_ID) $(SDF)

ingest: migrate ingest-csv ingest-sdf
	@echo "Ingest complete for dataset $(DATASET_ID)"

up:
	docker compose up -d postgres
	@echo "Waiting for Postgres..."
	sleep 3
	$(MAKE) migrate

dev: up
	docker compose up backend

backend-run:
	cd backend && PYTHONPATH=. python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
