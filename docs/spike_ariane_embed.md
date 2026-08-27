# Ariane Embedded Pane — Research Spike

Date: 2026-08-26 | Status: RECOMMENDATION — phased, start with (c)

## Inventory (E:/SDKs/ariane/src)
- librw-based (euryopa fork), C++14, ~40k LOC
- Parsers: IDE, IPL, IMG, COL, TXD, DFF — all custom code in `src/`
- Render: custom D3D9 + GL3 backends (heavy, do NOT port)
- UI: ImGui-style overlay + win32 window
- Hot-reload ariane.asi for in-game use

## Port vs Reuse Assessment

| Subsystem | Port to Python? | Effort | Value |
|-----------|----------------|--------|-------|
| IDE parser (text) | YES — trivial | ~150 LOC | High: item browser, conflict debugging |
| IPL parser (text) | YES — trivial | ~150 LOC | High: placement inspector |
| IMG archive reader | YES — small | ~200 LOC | High: browse gta3.img in launcher |
| COL parser (binary) | YES — moderate | ~400 LOC | Medium: collision viewer |
| DFF parser | PARTIAL — txdlite pattern extends | ~800 LOC | Medium: model info, texture-ref audit (would have caught today's bridge issue automatically) |
| TXD | DONE (txdlite) | — | — |
| D3D9/GL3 viewport | NO — reuse Ariane exe | 0 | Pop-out already shipped |
| World/streaming sim | NO | — | Low value vs cost |

## Recommendation: three phases

**Phase 1 (recommended first, ~1 day): "Map Data Inspector" pane**
- Python ports of IDE/IPL/IMG readers
- Launcher pane: browse gta3.img entries, view IDE item definitions, IPL placements
- Killer feature: **DFF texture-ref audit across all mods** — cross-references every DFF's material texture names against loaded TXD sets and lists unresolved ones. Would have auto-detected today's white-building and bridge conflicts in seconds.
- Zero render code, zero risk.

**Phase 2 (~2-3 days): COL + DFF info**
- Collision viewer (wireframe preview via matplotlib/pyqtgraph)
- DFF geometry stats (poly counts, material lists, bounding boxes)

**Phase 3 (deferred, big): 3D viewport**
- Only if Phase 1-2 prove daily-use value. Options: pyqtgraph OpenGL, or keep using Ariane exe pop-out for 3D (already shipped).

## Go/No-Go
Phase 1 is GO (high value, low risk, direct answer to today's mod-conflict debugging pain).
Phase 2 GO after Phase 1 proves out. Phase 3 NO-GO for now — Ariane pop-out covers 3D.
