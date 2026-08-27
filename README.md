# GTA Bridge Launcher

Hybrid Python/C++ launcher for GTA games with database-driven content management.

## Overview

This project provides a bridge between 32-bit GTA games and 64-bit database-driven content management, enabling unlimited modding capabilities while respecting memory constraints.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    64-bit Python Launcher                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ GUI (Tkinter│  │ Database   │  │ Git/Repo   │  │ Config   │ │
│  │ /PyQt)      │  │ (SQLite)   │  │ Management │  │ Manager  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │
│           │              │              │              │        │
│           ▼              ▼              ▼              ▼        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              C++ Core Components                             │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │ │
│  │  │ Memory      │  │ Process     │  │ API Bridge  │         │ │
│  │  │ Patcher     │  │ Injector    │  │ (Shared Mem)│         │ │
│  │  │ (C++)       │  │ (C++)       │  │ (C++)       │         │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                   │                              │
│                                   ▼                              │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              32-bit GTA Process                              │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │ │
│  │  │ GTA SA/VC/3 │  │ ASI Loader  │  │ Bridge Hook │         │ │
│  │  │ (Original)  │  │ (Ultimate)  │  │ (Injected)  │         │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
gta_bridge_launcher/
├── launcher.py              # Main entry point
├── requirements.txt         # Python dependencies
├── README.md               # This file
├── config/
│   ├── settings.json        # User preferences
│   └── games.json           # Game configurations
├── database/
│   └── schema.sql           # Database schema
├── managers/
│   ├── git_manager.py       # Git operations
│   ├── config_manager.py    # Configuration
│   └── game_manager.py      # Game operations
├── utils/
│   ├── memory_utils.py      # Memory utilities
│   └── system_utils.py      # System utilities
└── cpp/
    ├── memory_patcher.h     # Memory patcher header
    ├── memory_patcher.cpp   # Memory patcher implementation
    ├── bridge_hook.cpp      # ASI plugin for GTA
    └── memory_overlay.asi.cpp  # Memory overlay ASI plugin
```

## Memory Overlay

The project includes an ASI plugin that displays memory pool information on screen:

### Files
- `cpp/memory_overlay.asi.cpp` - ImGui-based overlay plugin

### How to Build
1. Compile with Visual Studio or MSVC:
   ```bash
   cl /LD cpp/memory_overlay.asi.cpp /Fe:memory_overlay.asi /I"path\to\imgui"
   ```

2. Copy `memory_overlay.asi` to your GTA SA directory

3. Launch GTA SA - the overlay will appear on screen showing:
   - Current memory usage
   - Streaming pool size
   - Texture pool size
   - Model pool size
   - Extended limits (Max Colors, Max Models)

### Console Overlay (Alternative)
Run `overlay_demo.py` for a console-based overlay that shows memory info while the game runs.

## Features

- **Database-Driven Content**: SQLite database for world data, color palettes, and limits
- **Git Integration**: Automatic cloning and updating of limit extender repositories
- **Dynamic Limits**: Calculate optimal limits based on system VRAM/RAM
- **Memory Patching**: C++ memory patcher for runtime modifications
- **Shared Memory Bridge**: Communication between Python and GTA process

## Installation

1. Install Python 3.8+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Pre-built EXE

A pre-built executable is available in the `dist/` folder:
- `dist/launcher.exe` - Standalone GUI launcher (no Python installation required)

To build your own EXE:
```bash
pip install pyinstaller
pyinstaller --onefile --windowed launcher.py
```

The EXE will be created in `dist/launcher.exe`

## Usage

### GUI Mode (Recommended)

Simply run the launcher:
```bash
python launcher.py
```

The GUI provides:
- Game selection dropdown (GTA SA, VC, III)
- Browse button to select the 32-bit executable
- Play button to launch with extended limits
- System information display

### Console Mode

If Tkinter is not available, the launcher falls back to console mode:
```bash
# Set game path and launch
export GTA_PATH="/path/to/gta/san/andreas"
python launcher.py
```

## How to Test

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the launcher:**
   ```bash
   python launcher.py
   ```

3. **In the GUI:**
   - Select your game from the dropdown
   - Click "Browse..." to select the 32-bit GTA executable
   - Click "Play" to launch with extended limits

4. **Verify limits are applied:**
   - Check the database file `gta_limits.db` for applied limits
   - Monitor system resources during gameplay

## Memory Addresses (GTA San Andreas)

| Address | Description |
|---------|-------------|
| 0xBC40E0 | CSector array |
| 0xB6F028 | CCamera instance |
| 0xB794D0 | RpWorld pointer |
| 0x8A5A80 | Streaming memory limit |
| 0x8F1A80 | Color table |
| 0x8F1A84 | Max colors limit |

## VRAM Scaling

The launcher calculates dynamic limits based on available VRAM:

```python
streaming_memory_mb = min(int(vram_mb * 0.3), 2048)  # 30% of VRAM, max 2GB
texture_memory_mb = min(int(vram_mb * 0.4), 1024)    # 40% of VRAM, max 1GB
model_memory_mb = min(int(vram_mb * 0.2), 512)       # 20% of VRAM, max 512MB
```

## Debugging

The launcher creates a log file at `launcher.log` in the same directory as the executable. This log includes:
- Game launch attempts
- Process IDs
- Error messages
- Memory calculations

To debug launch issues:
1. Run the launcher from command line: `launcher.exe`
2. Check `launcher.log` for detailed error messages
3. Verify the game executable path is correct

## License

MIT License
---

## Memory & Tooling Harness

This project carries a self-contained knowledge harness (ported from dirtysa). All agents/sessions should route lookups through it before grepping.

### .sadie — knowledge librarian (pure Python + SQLite, zero deps)
```bash
python .sadie/sadie.py init        # rebuild index from .serena/memories + workflows
python .sadie/sadie.py search "pipe protocol"   # title search
python .sadie/sadie.py query "SELECT title, location FROM items"
python .sadie/sadie.py stats
```
Knowledge lives in `.serena/memories/*.md` (project, asi-bridge, dlc-system, limits-presets, build-process, vault-refs). **Amend those files when architecture changes, then re-run `init`.**

### .harness-memory — session memory (npx, optional)
```bash
npx harness-memory init --db .harness-memory/memory.sqlite
npx harness-memory dream:run --db .harness-memory/memory.sqlite --trigger manual --json
```
Slash-commands for agents: `.opencode/commands/harness-memory-{init,dream,why}.md`.

### Workflow rules
1. Before exploring code, `python .sadie/sadie.py search "<topic>"`.
2. After meaningful work, update `.serena/memories/*.md` + re-init.
3. Build/verify per `.sadie/workflows/01-build-test-cycle.md`; pre-flight checks in `.sadie/checks/pre-flight.md`.

### Vault bridge + MiMoCode layer

- `python .sadie/sadie_vault_sync.py` — indexes the Obsidian vault
  (`E:/dev(dave)/GTA SA Reverse Engineering Documentation`, 124+ notes) into
  `sadie.db` as `vault/*` items. Idempotent (hash-tracked); re-run after vault
  edits. Search vault knowledge with `python .sadie/sadie.py search "<title>"`.
- `.mimocode/skills/` — MiMoCode-style playbooks: `launcher-build-test-cycle`
  (edit→compile→offscreen smoke→verify→package→memory-refresh) and
  `dlc-packaging` (manifest v2, deploy modes, conflict groups).
- Full memory loop after meaningful work:
  1. update `.serena/memories/*.md`
  2. `python .sadie/sadie.py init`
  3. `python .sadie/sadie_vault_sync.py`
  4. optional: `npx harness-memory dream:run --db .harness-memory/memory.sqlite --trigger manual`
