# Limits & presets
LIMIT_CATEGORIES: Pools, Entity Pointers, Memory, Models, Rendering, Textures, IPL & Scripts, Advanced. Entries {name,type,default,max,description}.
PRESETS: Stock, Balanced, High Performance, Modded, Pushed to Farthest, Top of the 2007 (era-correct Core2/2GB/8800: Peds 240 Vehicles 230 Buildings 260k Objects 42k), PS2 (32MB) Exact, Xbox (64MB) Exact, PS3 512MB, PS4 8GB, PS5 16GB.
Auto-VRAM: SystemUtils.get_top2007_auto_vram = total//4 clamp 512..8192; write_bridge_ini recomputes every boot (32GB -> 8172).
SKYGFX_MODES maps preset -> skygfx.ini [SkyGfx] values (PS2 dualPass, Xbox buildingPipe, PS3+ PBR).
MTA blue #5252 warning: building pool 180000+ can corrupt world — Pushed to Farthest 4M is experimental.
timecyc.dat fix shipped via launcher_data/fixes (dirMult field 52 + line-320 repair + postfx alpha halving; sources gta-reversed TimeCycle.cpp:60-207).
