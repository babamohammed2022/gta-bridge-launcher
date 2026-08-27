# Skill: DLC Packaging

1. Curate content into `launcher_data/dlc/<id>/` + manifest.json
   {id,name,category,default_enabled,layer,order,deploy_mode,files[]}.
2. Modes: modloader (sync into <game>/modloader/<name>), root (ASIs/dlls to
   game root), dircopy (exact rel paths), overwrite (data/models + .original.bak).
3. Conflict groups (vegetation / model_fixes / map): only one member enabled —
   UI greys clashing packs.
4. Deploy via GTALauncher.deploy_dlc(); disable = restore .original.bak.
5. Builders: utils/pack_build.py (modloader packs), utils/package_game_diff.py
   (game-vs-clean-SA diff → layered packs).
6. Refresh launcher_data/dlc/index.json {packs:[...]} after any pack change.
