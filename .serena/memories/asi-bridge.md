# ASI Bridge protocol
Pipe \.\pipe\gta_bridge, line protocol: HELLO->GTABRIDGE 1.0, PING, STATUS, MEM -> 'MEM avail used', USAGE <pool> -> 'USAGE n used max'.
Pool CALL-site hooks: Peds 0x550FF8, Vehicles 0x55102D, Buildings 0x551065, Objects 0x55109D, Dummys 0x5510D5. MemoryAvailable cap 0x5B8E64+6, usage 0x8A5A80/0x8E4CB4, 2GB cap. Overlay hook CHud::Draw 0x53E4FF.
Pools read (-1,-1) until ~9s after boot (CPool init). Client must retry first pipe open (EINVAL/ENOENT transient).
Build: premake5 vs2022 Win32 staticruntime -> MSBuild /p:Platform=Win32 -> asi_bridge/bin/gta_bridge.asi (PE 0x014C x86). Test: test_bridge_sim.py 14 checks.


## Verified vs hallucinated addresses (2026-08-25 — CRITICAL, Gemini hallucinated 3)
| What | Address | Status |
|---|---|---|
| CStreaming::ms_memoryAvailable (u32 bytes, default 256MB) | 0x8A5A80 | VERIFIED plugin-sdk CStreaming.cpp:11 — bridge writes streaming_mem_mb (default 1024, cap 0x7FFFFFFF) |
| CRenderer::ms_lodDistScale (float, default 1.2 NOT 1.0) | 0x8CD800 | VERIFIED CRenderer.cpp:31 — DynamicRenderScale per-frame 1.2..4.8 pool-headroom-driven |
| CTimeCycle far clip | 0xB7B1D0 | short TABLE [184] per-weather/hour — NOT a writable float; far-clip patching DEFERRED |
| CPlantMgr vegetation (TRILOC_FAR 0x53BAF4, ALPHA_FAR 0x5DBC3A) | — | UNVERIFIED (Gemini) — DISABLED, crashed game; verify from binary before enabling |
| CPools globals (CPool* ptr-to-ptr, 17 pools) | 0xB74484-0xB744C4 | VERIFIED plugin-sdk CPools.cpp:9-25 — g_usage readers, NO HOOKING |

## Architecture rules (hard-won)
- LimitAdjuster.asi = SOLE limit authority (18 MTA-max values in III.VC.SA.LimitAdjuster.ini [SALIMITS]: Buildings 32000, PtrNodes 90000/74800, VisiblePtrs 8192+8192, Coronas 4096, MemoryAvailable 4095, EntryInfo 72600, ColModel 30000, Objects 1200, Peds/PedInt 140, Vehicles 110, Dummys 2500, StreamingObjInst 30000, StaticShadows 2048).
- DLC packs must NEVER ship .ini overrides (limit_adjuster pack clobbered our MTA values every launch = whole crash saga).
- bridge.asi v2.1: no pool hooks; reads live pools via CPools globals; streaming mem + DynamicRenderScale (max_lod_scale=4.0 from gta_bridge.ini [BRIDGE]); vegetation DISABLED; pipe HELLO GTABRIDGE 2.0.
- NEVER trust LLM-hallucinated addresses — verify every address against plugin-sdk-sa/gta-reversed before writing.
