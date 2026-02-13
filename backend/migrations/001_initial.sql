-- Molecule Explorer V1 schema: hot/cold split for metadata + geometry

-- Datasets (one per CSV ingest)
CREATE TABLE IF NOT EXISTS dataset (
    dataset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ingest_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ingest runs (track each ingest for reporting)
CREATE TABLE IF NOT EXISTS ingest_run (
    run_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    stats JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Hot: molecule metadata from CSV (indexed for filter/aggregate)
CREATE TABLE IF NOT EXISTS discovered_molecule (
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    cid INTEGER NOT NULL,
    smiles TEXT,
    inchi_key TEXT,
    molecular_formula TEXT,
    molecular_weight DOUBLE PRECISION,
    exact_mass DOUBLE PRECISION,
    xlogp3 DOUBLE PRECISION,
    tpsa DOUBLE PRECISION,
    hba INTEGER,
    hbd INTEGER,
    rotatable_bonds INTEGER,
    discovery_method TEXT NOT NULL,
    discovery_seed TEXT,
    seed_name TEXT,
    seed_smiles TEXT,
    name TEXT,
    ingest_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, cid)
);

CREATE INDEX IF NOT EXISTS idx_dm_dataset_seed ON discovered_molecule(dataset_id, seed_name);
CREATE INDEX IF NOT EXISTS idx_dm_dataset_method ON discovered_molecule(dataset_id, discovery_method);
CREATE INDEX IF NOT EXISTS idx_dm_mw ON discovered_molecule(molecular_weight);
CREATE INDEX IF NOT EXISTS idx_dm_tpsa ON discovered_molecule(tpsa);
CREATE INDEX IF NOT EXISTS idx_dm_xlogp3 ON discovered_molecule(xlogp3);

-- Hot: geometry small columns (for range filters / aggregates)
CREATE TABLE IF NOT EXISTS molecule_geometry (
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    cid INTEGER NOT NULL,
    conformer_id TEXT,
    mmff94_energy DOUBLE PRECISION,
    conformer_rmsd DOUBLE PRECISION,
    effective_rotor_count INTEGER,
    shape_volume DOUBLE PRECISION,
    shape_selfoverlap DOUBLE PRECISION,
    heavy_atom_count INTEGER,
    component_count INTEGER,
    ingest_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, cid)
);

CREATE INDEX IF NOT EXISTS idx_mg_mmff94 ON molecule_geometry(mmff94_energy);
CREATE INDEX IF NOT EXISTS idx_mg_shape_volume ON molecule_geometry(shape_volume);

-- Cold: molblock + large blobs (TOAST; loaded only for detail/3D)
CREATE TABLE IF NOT EXISTS molecule_geometry_cold (
    dataset_id TEXT NOT NULL,
    cid INTEGER NOT NULL,
    molblock TEXT,
    shape_fingerprint BYTEA,
    pharmacophore_features BYTEA,
    mmff94_partial_charges BYTEA,
    coordinate_type BYTEA,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, cid),
    FOREIGN KEY (dataset_id, cid) REFERENCES molecule_geometry(dataset_id, cid) ON DELETE CASCADE
);

COMMENT ON TABLE dataset IS 'One row per ingested dataset (CSV manifest identity)';
COMMENT ON TABLE ingest_run IS 'One row per ingest run, stats JSON has row counts and coverage';
COMMENT ON TABLE discovered_molecule IS 'Hot path: CSV metadata keyed by (dataset_id, cid)';
COMMENT ON TABLE molecule_geometry IS 'Hot path: small SDF tags for filtering';
COMMENT ON TABLE molecule_geometry_cold IS 'Cold path: molblock and large blobs, loaded on detail/3D view';
