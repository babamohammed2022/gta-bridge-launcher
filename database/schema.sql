-- GTA Bridge Launcher Database Schema
-- SQLite schema for game data and limits

-- Game limits configuration
CREATE TABLE IF NOT EXISTS game_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL,
    limit_name TEXT NOT NULL,
    current_value INTEGER NOT NULL DEFAULT 0,
    max_value INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game, limit_name)
);

-- World data (IPL entries)
CREATE TABLE IF NOT EXISTS world_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    pos_x REAL NOT NULL,
    pos_y REAL NOT NULL,
    pos_z REAL NOT NULL,
    rot_x REAL DEFAULT 0,
    rot_y REAL DEFAULT 0,
    rot_z REAL DEFAULT 0,
    sector_x INTEGER,
    sector_y INTEGER,
    morton_code INTEGER NOT NULL,
    data_type TEXT DEFAULT 'inst',
    properties TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(model_id, data_type)
);

-- Color palettes (unlimited colors)
CREATE TABLE IF NOT EXISTS color_palettes (
    color_id INTEGER PRIMARY KEY,
    r INTEGER NOT NULL CHECK(r BETWEEN 0 AND 255),
    g INTEGER NOT NULL CHECK(g BETWEEN 0 AND 255),
    b INTEGER NOT NULL CHECK(b BETWEEN 0 AND 255),
    name TEXT,
    radio_name TEXT,
    is_custom BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- VRAM configuration
CREATE TABLE IF NOT EXISTS vram_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_vram_mb INTEGER NOT NULL,
    streaming_percent REAL DEFAULT 0.3,
    texture_percent REAL DEFAULT 0.4,
    model_percent REAL DEFAULT 0.2,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Game installations
CREATE TABLE IF NOT EXISTS game_installations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL,
    path TEXT NOT NULL,
    version TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game, path)
);

-- Mod entries
CREATE TABLE IF NOT EXISTS mods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT,
    path TEXT NOT NULL,
    game TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    dependencies TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_world_morton ON world_data(morton_code);
CREATE INDEX IF NOT EXISTS idx_world_sector ON world_data(sector_x, sector_y);
CREATE INDEX IF NOT EXISTS idx_game_limits ON game_limits(game, limit_name);
CREATE INDEX IF NOT EXISTS idx_color_palettes ON color_palettes(color_id);
CREATE INDEX IF NOT EXISTS idx_mods_game ON mods(game, is_active);

-- Insert default VRAM config
INSERT OR IGNORE INTO vram_config (id, total_vram_mb) VALUES (1, 2048);