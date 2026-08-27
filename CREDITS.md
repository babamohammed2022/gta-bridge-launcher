# CREDITS

GTA Bridge Launcher suite stands on the shoulders of the GTA modding community.
If we borrowed your work and missed you, tell us and we'll fix it.

## Libraries & tools bundled or derived from

| Project | Author(s) | License | What we use |
|---|---|---|---|
| III.VC.SA.LimitAdjuster | ThirteenAG + contributors | MIT | Pool hook pattern (PoolAdjuster CALL-site), MemoryAvailable addresses, INI layout |
| plugin-sdk | DK22Pac + contributors | MIT | SA structures, patch/injector helpers |
| injector | ThirteenAG | MIT | MakeCALL / memory patching |
| SilentPatch | Silent | (see repo) | Reference for timecyc directionalMult fix research |
| Ultimate ASI Loader | ThirteenAG | MIT | vorbisFile.dll ASI loading convention |
| modloader | thelink2012 + contributors | MIT | Runtime file stacking; our DLC deploy targets its folder format |
| CLEO / CLEO5 | CLEO team (cleo.li) | freeware | Script runtime for diag HUD |
| MoonLoader | thelink2012? (FYP) | freeware | Lua diag overlay |
| skygfx | aap (ThirteenAG ecosystem) | MIT | PS2/Xbox pipeline emulation research |
| fastman92 limit adjuster | fastman92 | view-only source | ID-limit research reference |
| Ariane | Dryxio (+ aap's euryopa, librw/Southland-FR) | see repo | External asset previewer integration |
| MTA:SA (mtasa-blue) | Multi Theft Auto contributors | MIT | Pool-capacity safety findings (#5252), CPathFind alloc-guard pattern (#5245), DX9 SceneView foundation via Neon #59 |
| MTA:SA Neon | Dryxio + contributors | MIT (inherits mtasa-blue) | LIMIT_PATCHING.md methodology, extended-lights research (#17/#18/#22), FPS limiter port (#32) |
| GGMM (GTA Garage Mod Manager) | Jernej L "Delfi" | freeware (2005-2007) | UX concept our MODS tab modernizes |
| Pricedown font | Typodermic Fonts (Ray Larabie) | free desktop license (EULA in fonts/) | Display typeface |
| PyQt5 | Riverbank Computing | GPL/commercial | UI framework |
| PyInstaller | PyInstaller contributors | GPL with runtime exception | Packaging |

## Research sources
- GTAMods wiki (gtamods.com) — GFDL 1.3+: file-format documentation mirrored into vault notes
- gta-reversed (Dryxio fork) — TimeCycle reader semantics
- GTAForums/GTAGarage community threads — timecyc.dat column semantics, carcols behavior

## Special thanks
- The GTA reverse-engineering community at large — three decades of shared knowledge.
