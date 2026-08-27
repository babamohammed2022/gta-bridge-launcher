# DLC v2 system
launcher_data/dlc/<id>/ + manifest.json {id,name,category,default_enabled,layer,order,deploy_mode,files[]}.
deploy_mode: modloader (sync to <game>/modloader/<name>), root (copy to game root), dircopy (exact rel paths), overwrite (data/model replace w/ .original.bak backup once).
Disable = restore .original.bak or rmtree. Deploy sorted (layer,order). index.json {packs:[...]}.
21 packs: 11 diff-derived (runtime_redist, cleo_scripts, moonloader_scripts, skygfx_core, silentpatch, limit_adjuster, neo_effects, data_patches, hd_vehicle_textures, particle_overhaul, model_extras) + 10 modloader-curated + bridge_scripts.
CONFLICT_GROUPS (app.py): vegetation {de_vegetation, improved_veg, mobile_vegetation}, model_fixes {proper_models, d_org_patch_sa}, map {parallax, ps2_map_+_fixes}.
DE_Vegetation_by_SA_THE_MODDER + Proper_models live in game modloader/ as testing-off via IgnoreMods (NOT DLC).
Tools: utils/pack_build.py (curate modloader packs), utils/package_game_diff.py (diff game vs clean_sa -> layered packs).


## Quick-mods UI (2026-08-25)
PlayScreen QUICK MODS: one-click pack toggles with CONFLICT_GROUPS mutual exclusion (enabling one disables siblings). Greying = clash + off. Deploy via DeployWorker after toggle.
