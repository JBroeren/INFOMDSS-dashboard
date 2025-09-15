-- KNRB Database Schema
-- This file contains the complete database schema for the KNRB scraper
-- Seasons table
CREATE TABLE IF NOT EXISTS knrb_seasons (
    id UUID PRIMARY KEY,
    season_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tournaments table (with scanning flag)
CREATE TABLE IF NOT EXISTS knrb_tournaments (
    id UUID PRIMARY KEY,
    season_id UUID REFERENCES knrb_seasons (id),
    tournament_data JSONB,
    scanned_for_persons BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Matches table
CREATE TABLE IF NOT EXISTS knrb_matches (
    id UUID PRIMARY KEY,
    tournament_id UUID REFERENCES knrb_tournaments (id),
    match_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Races table
CREATE TABLE IF NOT EXISTS knrb_races (
    id UUID PRIMARY KEY,
    match_id UUID REFERENCES knrb_matches (id),
    race_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Persons table
CREATE TABLE IF NOT EXISTS knrb_persons (
    id UUID PRIMARY KEY,
    person_data JSONB,
    race_overview_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Klassementen table
CREATE TABLE IF NOT EXISTS knrb_klassementen (
    id UUID PRIMARY KEY,
    race_id UUID REFERENCES knrb_races (id),
    klassement_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Klassement details table
CREATE TABLE IF NOT EXISTS knrb_klassement_details (
    id UUID PRIMARY KEY,
    klassement_id UUID REFERENCES knrb_klassementen (id),
    klassement_detail_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for tournament scanning
CREATE INDEX IF NOT EXISTS idx_knrb_tournaments_scanned_for_persons ON knrb_tournaments (scanned_for_persons);

-- Additional useful indexes
CREATE INDEX IF NOT EXISTS idx_knrb_tournaments_season_id ON knrb_tournaments (season_id);

CREATE INDEX IF NOT EXISTS idx_knrb_matches_tournament_id ON knrb_matches (tournament_id);

CREATE INDEX IF NOT EXISTS idx_knrb_races_match_id ON knrb_races (match_id);

CREATE INDEX IF NOT EXISTS idx_knrb_klassementen_race_id ON knrb_klassementen (race_id);

CREATE INDEX IF NOT EXISTS idx_knrb_klassement_details_klassement_id ON knrb_klassement_details (klassement_id);


