# launcher_data/fixes — shipped data corrections

Deployed to the game directory by `GTALauncher.deploy_fixes()` on every launch
(original file backed up once as `<name>.original.bak` before first overwrite).

## timecyc.dat

Corrected GTA San Andreas PC `data/timecyc.dat` (184 weather-hour lines × 52 fields).

Base: Rockstar stock `H:/games/clean_sa/data/timecyc.dat` (also present in any clean install).
This shipped file is byte-identical to the proven-working file in
`E:/games/gtasa_skygfx_plus/data/timecyc.dat`.

### Fixes applied (vs stock)

1. **Missing `directionalMult` column (field 52) appended — value `1.00` on 180 lines, `0.00` on 4.**
   The SA PC reader (`CTimeCycle::Load`_, see gta-reversed
   `source/game_sa/TimeCycle.cpp:60-207`) sscanf's **52** fields and stores
   `m_nDirectionalMult[h][w] = uint8(dirMult * 100)`. Stock PC lines have only 51
   fields → directional mult parses as garbage/0 → the sun's directional light is
   effectively disabled and a hardcoded fixed-colour vehicle light substitutes
   (the "vehicles too bright" bug SilentPatch also addresses).

2. **Line 320 first-triple repair.** R* shipping mistake (called out by a comment
   in the reader itself next to the `if (n < 51)` warning): the first ambient RGB
   triple is a lone `255` instead of three values (`22 22 22`), shifting every
   later field on the line by 2. Repaired to the intended triple.

3. **postfx1A / postfx2A alpha normalization (columns 41/45, 1-based).**
   The reader **doubles** both postfx alphas on load (`uint8(postFx1A * 2.f)`).
   Stock ships `255`, which doubles/wraps to 254 with wrong filter strength.
   Shipped values are pre-halved (mostly `127`, a few hand-tuned like `111`) so
   post-double they land at console-intended colour-filter strength.

### Sources

- Reader ground truth: gta-reversed (`E:/SDKs/gta-reversed/source/game_sa/TimeCycle.cpp`)
- Format/columns: gtamods.com wiki "Time cycle" + vault `GTAMods Wiki/Time cycle` research,
  vault `Fixed Function to Shader Linearization.md` §5
- Alpha tuning + repaired line reference: skygfx project research
  (`usePCTimecyc`, `rgb2pc` alpha handling in `E:/SDKs/skygfx/src/postfx.cpp:1231-1239`)
- Validation: token-level compare vs clean_sa stock (184×52 after fix, single
  repaired line) and byte-compare vs live working install.

### Deploy behavior

- `deploy_fixes()` runs from `launch_game()` before the game starts.
- If the game dir has no `timecyc.dat.original.bak`, the current file is backed up first.
- Delete `timecyc.dat.original.bak` restore path: rename it back over `timecyc.dat`.
