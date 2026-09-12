# GTA Bridge Launcher

Hybrid Python/C++ launcher for 32-bit GTA games with database-driven content and memory management.

## Overview

This repository contains a hybrid Python/C++ launcher for 32-bit GTA games.

This software combines a Python-based launcher with native C++ components to manage game installations, modding-related data, runtime memory configuration, and communication with the game process.

This project is designed to keep the original 32-bit GTA executable as the main game process while providing additional tools for configuration and memory management.

## Features

This software provides the following features:

* **Game Management** — Select and launch supported GTA installations
* **Database-Driven Configuration** — Store limits, settings, and modding data using SQLite
* **Git Integration** — Manage repository-based content
* **Dynamic Memory Limits** — Calculate configurable limits based on available system resources
* **Memory Patching** — Apply runtime modifications through native C++
* **Shared Memory Bridge** — Communication between the launcher and the GTA process
* **Memory Overlay** — Optional in-game overlay for monitoring memory pools

## Architecture

This repository uses a hybrid architecture in which the Python launcher manages configuration and content while native C++ components handle game-process operations.

```text
64-bit Python Launcher
        │
        ├── GUI
        ├── SQLite Database
        ├── Git / Repository Manager
        └── Configuration Manager
        │
        ▼
C++ Core
        │
        ├── Memory Patcher
        ├── Process / Injection Components
        └── Shared Memory API Bridge
        │
        ▼
32-bit GTA Process
        │
        ├── GTA SA / VC / III
        ├── ASI Loader
        └── Bridge Hook
```

## Project Structure

This repository is organized into Python management components, configuration and database files, and native C++ components.

```text
gta_bridge_launcher/
├── launcher.py
├── requirements.txt
├── README.md
│
├── config/
│   ├── settings.json
│   └── games.json
│
├── database/
│   └── schema.sql
│
├── managers/
│   ├── git_manager.py
│   ├── config_manager.py
│   └── game_manager.py
│
├── utils/
│   ├── memory_utils.py
│   └── system_utils.py
│
└── cpp/
    ├── memory_patcher.h
    ├── memory_patcher.cpp
    ├── bridge_hook.cpp
    └── memory_overlay.asi.cpp
```

## Requirements

This software requires:

* Windows
* Python 3.8 or newer
* A supported 32-bit GTA installation
* Git for repository-based content management

This repository may also require a compatible Visual Studio/MSVC toolchain when building the native C++ components.

## Installation

This repository can be used directly from source or through a pre-built executable when one is available.

### From Source

Clone this repository and install its Python dependencies:

```cmd
git clone https://github.com/silskrill89/gta-bridge-launcher.git
cd gta-bridge-launcher
pip install -r requirements.txt
```

Start the software with:

```cmd
python launcher.py
```

### Pre-built Executable

If this repository provides a pre-built executable, the launcher can be started directly from:

```text
dist/launcher.exe
```

This standalone executable does not require a separate Python installation.

### Building the Executable

This repository can be packaged as a standalone executable using PyInstaller.

Install PyInstaller:

```cmd
pip install pyinstaller
```

Build the launcher:

```cmd
pyinstaller --onefile --windowed launcher.py
```

The resulting executable is placed in:

```text
dist/launcher.exe
```

## Game Configuration

This software requires the executable of the GTA installation that should be launched.

This path must point directly to the game's executable.

Example:

```text
GTA San Andreas/
└── gta_sa.exe
```

The launcher should not be configured to use a shortcut or an unrelated executable.

## Usage

This software provides a graphical interface for normal operation.

### GUI

The graphical interface provides:

* Game selection
* Game executable selection
* Launch controls
* System information
* Memory configuration

Start the launcher with:

```cmd
python launcher.py
```

### Console

This software can also be started from a Windows command prompt:

```cmd
set GTA_PATH=C:\Games\GTA San Andreas
python launcher.py
```

If the graphical interface cannot be initialized, the launcher can fall back to console-based operation.

## Memory Overlay

This repository includes an optional ASI plugin for displaying memory information while the game is running.

The overlay can display:

* Current memory usage
* Streaming pool size
* Texture pool size
* Model pool size
* Extended limits

### Building

This component requires a compatible Visual Studio/MSVC environment and the required Dear ImGui dependencies.

After compilation, the resulting `.asi` file can be placed in the GTA installation directory.

## VRAM Scaling

This software can calculate memory limits according to the available VRAM.

The current implementation uses heuristic percentages and maximum values:

```python
streaming_memory_mb = min(int(vram_mb * 0.3), 2048)
texture_memory_mb = min(int(vram_mb * 0.4), 1024)
model_memory_mb = min(int(vram_mb * 0.2), 512)
```

These calculations are heuristics and should not be considered guaranteed optimal values for every system.

## Memory Addresses

This repository currently uses the following GTA San Andreas memory addresses for memory-related operations:

| Address    | Description            |
| ---------- | ---------------------- |
| `0xBC40E0` | CSector array          |
| `0xB6F028` | CCamera instance       |
| `0xB794D0` | RpWorld pointer        |
| `0x8A5A80` | Streaming memory limit |
| `0x8F1A80` | Color table            |
| `0x8F1A84` | Maximum colors limit   |

These addresses are version-specific and may not apply to other GTA executables.

## Debugging

This software creates a diagnostic log named `launcher.log`.

The log may contain:

* Game launch attempts
* Process IDs
* Error messages
* Memory calculations

To troubleshoot launch problems:

1. Start the launcher from a command prompt.
2. Check `launcher.log`.
3. Verify the GTA executable path.
4. Verify that the required dependencies are installed.

## Testing

This repository can be manually verified by installing the dependencies and starting the launcher:

```cmd
pip install -r requirements.txt
python launcher.py
```

The basic verification procedure is:

1. Select a supported GTA installation.
2. Select its executable.
3. Start the game.
4. Verify that the launcher completes without errors.
5. Check `launcher.log` for diagnostic information.
6. Verify the expected memory configuration in-game.

## Development

This repository keeps development-specific workflows and internal tooling separate from the main user documentation.

Development documentation can be placed in:

```text
docs/development.md
```

This keeps the main README focused on installation, usage, features, and troubleshooting.

## License

This repository is released under the MIT License.
