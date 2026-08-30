#include <windows.h>
#include <string>
#include <map>
#include <functional>
#include <fstream>
#include <sstream>
#include <vector>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <cmath>

// injector + pool struct
#include "injector/injector.hpp"
#include "injector/utility.hpp"
#include "CPool.h"

// ============================================================================
// GTA Bridge ASI v2 — "builds on top" architecture (m1598)
//
// LimitAdjuster.asi = THE limit authority (pool resizing via its own ini,
//   written by the launcher into III.VC.SA.LimitAdjuster.ini).
// This ASI NO LONGER patches pool ctor call sites (that caused the
//   dual-patcher conflict, m1595). Instead it:
//   - READS live pool usage via CPool* globals (plugin-sdk CPools.cpp)
//   - patches streaming memory (CStreaming::ms_memoryAvailable 0x8A5F10)
//   - patches vegetation LOD constants (CPlantMgr, GTAV-recipe scaling)
//   - runs a per-frame dynamic render-distance scaler driven by pool headroom
//   - serves the \\.\pipe\gta_bridge protocol for the 64-bit launcher
// ============================================================================

// -------- helpers --------
static uint32_t MbToBytes(uint32_t mb) { return mb * 1048576u; }
static uint32_t BytesToMb(uint32_t b)  { return b / 1048576u; }
static int vkBridgeText = VK_F5;

static std::string trim(const std::string &s) {
    size_t a = 0;
    while (a < s.size() && (s[a]==' '||s[a]=='\t'||s[a]=='\r'||s[a]=='\n')) ++a;
    size_t b = s.size();
    while (b > a && (s[b-1]==' '||s[b-1]=='\t'||s[b-1]=='\r'||s[b-1]=='\n')) --b;
    return s.substr(a, b-a);
}

// Safe read of uint32 at absolute address
static bool safeReadU32(uintptr_t addr, uint32_t &out) {
    __try {
        out = *(volatile uint32_t*)addr;
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

// Safe read of float at absolute address
static bool safeReadFloat(uintptr_t addr, float &out) {
    __try {
        out = *(volatile float*)addr;
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        return false;
    }
}

// -------- Pool globals (plugin-sdk-sa CPools.cpp lines 9-25) --------
// Pointer-to-pointer globals: the game stores CPool* here after init.
// LimitAdjuster resizes pools; we read the live objects. NO HOOKING.
struct PoolGlobal { const char* name; uintptr_t addr; };
static const PoolGlobal g_poolGlobals[] = {
    {"PtrNodeSingle",   0xB74484},
    {"PtrNodeDouble",   0xB74488},
    {"EntryInfoNode",   0xB7448C},
    {"Peds",            0xB74490},
    {"Vehicles",        0xB74494},
    {"Buildings",       0xB74498},
    {"Objects",         0xB7449C},
    {"Dummys",          0xB744A0},
    {"ColModel",        0xB744A4},
    {"Task",            0xB744A8},
    {"Event",           0xB744AC},
    {"PointRoute",      0xB744B0},
    {"PatrolRoute",     0xB744B4},
    {"NodeRoute",       0xB744B8},
    {"TaskAllocator",   0xB744BC},
    {"PedIntelligence", 0xB744C0},
    {"PedAttractors",   0xB744C4},
};

using GPool = CPool<char,char>;

static bool ReadPoolUsage(uintptr_t globalAddr, int &used, int &maxv) {
    uint32_t raw = 0;
    if(!safeReadU32(globalAddr, raw)) return false;
    GPool* p = (GPool*)(uintptr_t)raw;
    if(!p) return false;
    __try {
        maxv = p->m_Size;
        if(maxv <= 0 || maxv > 10000000) return false;
        used = 0;
        for(int i=0;i<maxv;++i) if(!p->IsFreeSlotAtIndex(i)) ++used;
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}

// Maps for the pipe protocol + overlay
static std::map<std::string, std::function<bool(int&,int&)>> g_usage;

static void RegisterUsageReaders() {
    static bool done=false;
    if(done) return;
    done=true;
    for(auto &pg : g_poolGlobals) {
        uintptr_t addr = pg.addr;
        g_usage[pg.name] = [addr](int &u,int &m){ return ReadPoolUsage(addr,u,m); };
    }
}

// -------- Game dir / ini --------
static std::string GetGameDir() {
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    std::string s(path);
    size_t pos = s.find_last_of("\\/");
    if(pos != std::string::npos) s = s.substr(0, pos);
    return s;
}

// -------- Bridge-specific patches --------
// Streaming memory: CStreaming::ms_memoryAvailable (default 256MB).
// VERIFIED address 0x8A5A80 (plugin-sdk-sa CStreaming.cpp:11).
// LAA ceiling 0x7FFFFFFF (~2048MB) — beyond that, VA fragmentation OOM.
static void ApplyStreamingMemory(uint32_t mb) {
    uint64_t bytes = (uint64_t)mb * 1048576u;
    if(bytes > 0x7FFFFFFFull) bytes = 0x7FFFFFFFull;
    injector::WriteMemory<uint32_t>(injector::memory_pointer(0x8A5A80), (uint32_t)bytes, true);
}

// Vegetation (CPlantMgr) GTAV-recipe scaling — DISABLED by default.
// Addresses from Gemini research were UNVERIFIED and crashed the game
// (wrote through 0x53BAF4 pointer + float at 0x5DBC3A). Do NOT enable
// until addresses are verified from gta-reversed CPlantMgr or a binary
// pattern scan of the actual SA 1.0 US executable.
static void ApplyVegetationPatches() {
    // intentionally empty — see comment above
}

// -------- Dynamic render-distance scaler (per-frame, pool-headroom driven) --------
// CRenderer::ms_lodDistScale = 0x8CD800 (float, default 1.2) — VERIFIED
// plugin-sdk-sa CRenderer.cpp:31. MixSets-style knob.
// Far clip NOT patched: real far clip = m_fFarClip short table at 0xB7B1D0
// (per-weather/hour), interpolated by CTimeCycle — no safe single float.
static float g_maxLodScale = 4.0f;
static bool  g_dynamicLod = true; // [BRIDGE] DYNAMIC_LOD=0 freezes lodDistScale at stock 1.2 (user kill-switch)
static float GovernorLodFactor(); // Streaming Supervisor below
// ---- anti-flicker control-loop damping (player-idle LOD oscillation fix) ----
static double   g_headEma = -1.0;
static float    g_lastScaleWritten = 0.0f;
static float    g_lastDir = 0.0f;
static uint32_t g_lastDirChangeTick = 0;
static uint32_t g_lastWriteTick = 0;
// ---- instrumentation state (exposed from DynamicRenderScale to DrawStatsBlock) ----
static float    g_lodTarget     = 1.2f;    // pre-clamp target this frame (headroom-derived)
// ---- camera-velocity tracking for speed-scaled LOD ----
static float    g_camSpeed    = 0.0f;      // EMA-smoothed camera speed (m/s)
static float    g_prevCamX    = 0.0f;
static float    g_prevCamY    = 0.0f;
static bool     g_camLayoutOk = false;     // true after first sane camera-position read
static uint32_t g_camLastTick = 0;
static const float SLEW_PER_SEC = 0.35f;   // max scale units per second
static const float DEADBAND     = 0.15f;   // ignore small headroom wobble
static const uint32_t HOLD_MS   = 2500;    // min hold before reversing direction
static void DynamicRenderScale() {
    // ---- camera-velocity tracking (always runs, even if dynamic LOD disabled) ----
    uint32_t now = GetTickCount();
    uint32_t camDt = now - g_camLastTick;
    g_camLastTick = now;
    uint32_t rawX=0, rawY=0;
    if(safeReadU32(0xB6F030, rawX) && safeReadU32(0xB6F034, rawY)) {
        float fx = *(float*)&rawX;
        float fy = *(float*)&rawY;
        // SA world: valid coords typically within [-3000, 3000]; use generous sanity
        if(fx > -10000.0f && fx < 10000.0f && fy > -10000.0f && fy < 10000.0f) {
            if(g_camLastTick > 0 && camDt > 0 && camDt < 500) {
                float dx = fx - g_prevCamX;
                float dy = fy - g_prevCamY;
                float dist = sqrtf(dx*dx + dy*dy);
                float dtSec = (float)camDt / 1000.0f;
                float speed = dist / dtSec;
                if(speed < 200.0f) { // ~720 km/h sanity ceiling
                    g_camLayoutOk = true;
                    g_camSpeed = (g_camSpeed == 0.0f) ? speed : g_camSpeed + (speed - g_camSpeed) * 0.1f;
                }
            }
            g_prevCamX = fx;
            g_prevCamY = fy;
        }
    }
    if(!g_dynamicLod) return; // kill-switch: stock render distance, no adaptation
    int u=0,m=0; double head=0.0; int n=0;
    if(ReadPoolUsage(0xB74498, u, m) && m>0){ head += 1.0-(double)u/(double)m; ++n; } // Buildings
    if(ReadPoolUsage(0xB7449C, u, m) && m>0){ head += 1.0-(double)u/(double)m; ++n; } // Objects
    if(!n) return;
    head /= (double)n;
    // smooth headroom (EMA) so per-frame streaming noise doesn't pass through
    g_headEma = (g_headEma < 0.0) ? head : g_headEma + (head - g_headEma) * 0.04;
    // base 1.2 (stock default) scaled by smoothed headroom up to 1.2*max_scale
    float target = (float)(1.2 * (1.0 + g_headEma * (double)(g_maxLodScale-1.0f)));
    if(target < 1.2f) target = 1.2f;
    g_lodTarget = target; // expose pre-velocity pre-clamp target for HUD

    // velocity-scaled LOD: push scale up when moving fast (distant LODs visible)
    if(g_camLayoutOk) {
        float speedFactor = g_camSpeed * 0.05f;
        if(speedFactor > 1.2f) speedFactor = 1.2f;
        target += speedFactor;
    }

    float cap = 1.2f * g_maxLodScale * GovernorLodFactor();
    if(target > cap) target = cap;
    float cur = g_lastScaleWritten > 0.0f ? g_lastScaleWritten : target;
    float delta = target - cur;
    if(fabs(delta) < DEADBAND) return;                                    // deadband
    float dir = delta > 0.0f ? 1.0f : -1.0f;
    if(dir != g_lastDir && (now - g_lastDirChangeTick) < HOLD_MS) return; // hold before reversing
    if(dir != g_lastDir){ g_lastDir = dir; g_lastDirChangeTick = now; }
    if(now - g_lastWriteTick < 200) return;                               // max 5 writes/sec
    float step = SLEW_PER_SEC * (float)(now - g_lastWriteTick) / 1000.0f;
    if(step > fabs(delta)) step = fabs(delta);
    float scale = cur + dir * step;
    injector::WriteMemory<float>(injector::memory_pointer(0x8CD800), scale, true);
    g_lastScaleWritten = scale;
    g_lastWriteTick = now;
}

// -------- Streaming Supervisor v1 (PS2-throttle removal) --------
// VERIFIED addresses (plugin-sdk-sa CStreaming.cpp):
//   RemoveAllUnusedModels   0x40CF80
//   RemoveBigBuildings      0x4093B0
//   PurgeRequestList        0x40C1E0
//   LoadAllRequestedModels  0x40EA10 (bool bOnlyPriorityRequests)
// DVD-era design loads one small block per channel per frame; we add a
// supervisor that drains priority requests every tick and evicts unused
// models under memory pressure so load/unload tracks actual demand.
static bool GetMemUsage(int &availMb, int &usedMb); // fwd
static void SessionLogWrite(const char* fmt, ...);   // fwd (defined below, used by pump logging)
static bool g_streamGovernor = true;
static float g_pressSoft = 0.85f, g_pressHard = 0.93f;
static float g_fpsMin = 40.0f, g_fpsMax = 55.0f;
static float g_fpsAvg = 60.0f;
static uint32_t g_fpsTick = 0, g_fpsFrames = 0, g_supTick = 0;
// Buildings-headroom priority pump state
static int      g_pumpBurstCount = 0;
static uint32_t g_pumpLastLogTick = 0;
static bool     g_pumpEverLogged = false;

typedef void (*FnVoid)();
static FnVoid CStream_RemoveAllUnused = (FnVoid)0x40CF80;
static FnVoid CStream_RemoveBigBuildings = (FnVoid)0x4093B0;
static FnVoid CStream_PurgeRequestList = (FnVoid)0x40C1E0;
typedef void (*FnLoadAll)(bool);
static FnLoadAll CStream_LoadAllRequested = (FnLoadAll)0x40EA10;

// FPS-based multiplier applied to the lodDistScale cap (1.0 when healthy).
static float GovernorLodFactor() {
    if(!g_streamGovernor) return 1.0f;
    if(g_fpsAvg >= g_fpsMax) return 1.0f;
    if(g_fpsAvg <= g_fpsMin * 0.6f) return 0.5f;
    if(g_fpsAvg <= g_fpsMin) return 0.7f;
    float t = (g_fpsAvg - g_fpsMin) / (g_fpsMax - g_fpsMin);
    return 0.7f + 0.3f * t;
}

static void StreamingSupervisor() {
    // rolling FPS (1s window)
    uint32_t now = GetTickCount();
    ++g_fpsFrames;
    if(!g_fpsTick) { g_fpsTick = now; }
    else if(now - g_fpsTick >= 1000) {
        g_fpsAvg = 1000.0f * (float)g_fpsFrames / (float)(now - g_fpsTick);
        g_fpsFrames = 0; g_fpsTick = now;
    }
    if(!g_streamGovernor) return;

    // --- Buildings-headroom priority pump (every tick, before rate-limiter) ---
    int bU=0, bM=0;
    bool buildingsOk = ReadPoolUsage(0xB74498, bU, bM) && bM > 0;
    float buildingsHead = buildingsOk ? (1.0f - (float)bU/(float)bM) : 1.0f;

    bool pumpThisTick = false;
    if(buildingsHead < 0.15f) {
        // burst: max 10 consecutive ticks, then 1 cooldown
        if(g_pumpBurstCount < 10) { pumpThisTick = true; ++g_pumpBurstCount; }
        else                        { g_pumpBurstCount = 0; }
    } else if(buildingsHead < 0.30f) {
        pumpThisTick = true;
        g_pumpBurstCount = 0;
    } else {
        g_pumpBurstCount = 0;
    }

    if(pumpThisTick) {
        CStream_LoadAllRequested(true);
        if(!g_pumpEverLogged || (now - g_pumpLastLogTick) >= 30000) {
            g_pumpEverLogged = true;
            g_pumpLastLogTick = now;
            SessionLogWrite("PRIORITY_PUMP %d", g_pumpBurstCount > 0 ? g_pumpBurstCount : 1);
        }
    }

    // --- Rate-limited memory-pressure eviction (gated: no RemoveBigBuildings when buildings full) ---
    if(now - g_supTick < 750) return;
    g_supTick = now;
    int a=-1,u=-1;
    if(!GetMemUsage(a,u) || a<=0) return;
    float pressure = (float)u / (float)a;
    if(pressure >= g_pressHard) {
        CStream_PurgeRequestList();
        if(buildingsHead >= 0.30f) CStream_RemoveBigBuildings(); // gate: don't fight the pump
        CStream_RemoveAllUnused();
    } else if(pressure >= g_pressSoft) {
        CStream_RemoveAllUnused();
    }
    // else low pressure: pump already handled above
}

// -------- Bridge ini ([OPTIONS] + [BRIDGE]) --------
static uint32_t g_streamingMemMb = 1024;
static bool g_vegetationBoost = false;

static void ApplyBridgeIni(const std::string &iniPath) {
    std::ifstream f(iniPath);
    if(!f) return;
    std::string line, section;
    while(std::getline(f, line)) {
        std::string t = trim(line);
        if(t.empty() || t[0]==';' || t[0]=='#' || t[0]=='/') continue;
        if(t.front()=='[' && t.back()==']') {
            section = trim(t.substr(1, t.size()-2));
            for(char &c: section) c = toupper(c);
            continue;
        }
        if(section!="OPTIONS" && section!="BRIDGE") continue;
        auto eq=t.find('=');
        if(eq==std::string::npos) continue;
        std::string k=trim(t.substr(0,eq)); std::string v=trim(t.substr(eq+1));
        for(char &c:k) c=toupper(c);
        auto sc = v.find(';');
        if(sc!=std::string::npos) v = trim(v.substr(0,sc));
        if(k=="DEBUGTEXTKEY"){ try{ vkBridgeText=std::stoi(v,nullptr,0);}catch(...){} }
        else if(k=="STREAMING_MEM_MB"){ try{ g_streamingMemMb=(uint32_t)std::stoul(v);}catch(...){} }
        else if(k=="MAX_LOD_SCALE"){ try{ g_maxLodScale=std::stof(v);}catch(...){} }
        else if(k=="DYNAMIC_LOD"){ g_dynamicLod = (v!="0"); }
        else if(k=="VEGETATION_BOOST"){ g_vegetationBoost = (v=="1"||v=="true"||v=="yes"); }
        else if(k=="STREAM_GOVERNOR"){ g_streamGovernor = (v=="1"||v=="true"||v=="yes"); }
        else if(k=="PRESS_SOFT"){ try{ g_pressSoft=std::stof(v);}catch(...){} }
        else if(k=="PRESS_HARD"){ try{ g_pressHard=std::stof(v);}catch(...){} }
        else if(k=="FPS_MIN"){ try{ g_fpsMin=std::stof(v);}catch(...){} }
        else if(k=="FPS_MAX"){ try{ g_fpsMax=std::stof(v);}catch(...){} }
    }
}

// -------- Pipe server --------
static const char* PIPE_NAME = "\\\\.\\pipe\\gta_bridge";
// Mirage Pool v1: launcher-owned shared section (64-bit side creates, we map a view)
static const char* SHM_NAME = "GTA_BRIDGE_SHM";
static HANDLE g_shmHandle = NULL;
static void* g_shmView = nullptr;
static size_t g_shmSize = 0;
static volatile bool g_shutdown = false;
static HANDLE g_thread = NULL;

static bool GetMemUsage(int &availMb, int &usedMb) {
    uint32_t availRaw=0, usedRaw=0;
    if(!safeReadU32(0x8A5A80, availRaw)) return false;
    if(!safeReadU32(0x8E4CB4, usedRaw)) return false;
    availMb = (int)BytesToMb(availRaw);
    usedMb  = (int)BytesToMb(usedRaw);
    return true;
}

static injector::hook_back<void(*)()> DrawHUD;
static uint32_t current_limit = 0;
static const uint32_t limits_per_page = 18;
static float currposx, currposy;
static bool BeginDraw(){ currposx=10.0f; currposy=105.0f; return true; }
static void EndDraw(){ static void (*RenderFontBuffer)() = injector::lazy_pointer<0x719840>::get(); RenderFontBuffer(); }
static void* g_colourOv = nullptr;               // transient CRGBA* override consumed by DrawTextInternal
static void DrawTextInternal(const char* text, float x, float y, float sx, float sy){
    struct CRGBA{ unsigned char r,g,b,a; CRGBA(unsigned char R,unsigned char G,unsigned char B,unsigned char A):r(R),g(G),b(B),a(A){} CRGBA(){} };
    static void* pInterfaceColour = injector::lazy_pointer<0xBAB22C>::get();
    static void* pGetInterfaceColour = injector::lazy_pointer<0x58FEA0>::get();
    static int* pRsGlobal = injector::lazy_pointer<0xC17040>::get();
    static void (*SetScale)(float,float) = injector::lazy_pointer<0x719380>::get();
    static void (*SetColor)(void*) = injector::lazy_pointer<0x719430>::get();
    static void (*SetFontStyle)(short) = injector::lazy_pointer<0x719490>::get();
    static void (*SetDropColor)(CRGBA) = injector::lazy_pointer<0x719510>::get();
    static void (*SetEdge)(short) = injector::lazy_pointer<0x719590>::get();
    static void (*SetProportional)(bool) = injector::lazy_pointer<0x7195B0>::get();
    static void (*SetBackground)(bool,bool) = injector::lazy_pointer<0x7195C0>::get();
    static void (*SetJustify)(bool) = injector::lazy_pointer<0x719600>::get();
    static void (*SetRightJustifyWrap)(float) = injector::lazy_pointer<0x7194F0>::get();
    static void (*SetWrapx)(float) = injector::lazy_pointer<0x7194D0>::get();
    static void (*SetOrientation)(int) = injector::lazy_pointer<0x719610>::get();
    static void (*PrintString)(float,float,const char*) = injector::lazy_pointer<0x71A700>::get();
    CRGBA rgba(0x1B,0x59,0x82,0xFF);
    if(pGetInterfaceColour && pInterfaceColour) ((CRGBA*(__thiscall*)(void*,CRGBA*,unsigned char))pGetInterfaceColour)(pInterfaceColour,&rgba,4);
    if(g_colourOv) rgba=*(CRGBA*)g_colourOv;
    float screenx = (float)((signed int)*(pRsGlobal+1))/640.0f;
    float screeny = (float)((signed int)*(pRsGlobal+2))/448.0f;
    SetFontStyle(1); SetJustify(0); SetBackground(0,0); SetProportional(true); SetOrientation(1); SetRightJustifyWrap(0); SetWrapx(640.0f*screenx); SetEdge(1); SetDropColor(CRGBA(0,0,0,0xFF)); SetColor(&rgba); SetScale(screenx*sx, screeny*sy);
    PrintString(screenx*x, screeny*y, text);
}
static void DrawText(const char* t){ const float x=currposx,y=currposy; const float sx=0.60f*0.65f,sy=0.89f*0.65f; currposy+=sy*20; DrawTextInternal(t,x,y,sx,sy); }
static void DrawLine(const char* n,const char* v){ char b[1024]; sprintf(b,"%s: %s",n,v); DrawText(b); }

// ===== Engine stat HUD (F7 cycle FULL/MIN/OFF) - renders through native font path =====
struct StatCol{unsigned char r,g,b,a;};
static StatCol COL_WHITE={0xFF,0xFF,0xFF,0xFF}, COL_GREEN={0x66,0xCC,0x66,0xFF},
              COL_YELL={0xE6,0xC8,0x4A,0xFF},  COL_RED ={0xE6,0x5C,0x4A,0xFF};

static int      s_ovMode   = 0;                  // 0 OFF 1 FULL 2 MIN (persisted [OVERLAY] state)
static bool     s_f7Prev   = false;
static double   s_avgMs    = 16.6;
static float    s_minFps   = 1e9f, s_maxFps = 0.f;
static uint32_t s_frameCount = 0, s_lastTick = 0, s_lastCsv = 0, s_lastFrameMs = 16;
static uint32_t s_ftHist[120];                   // last frametimes (ms)
static int      s_ftIdx = 0;
static bool     s_wantDiag = false;              // set by DrawBridgeOverlay before StatHudFrame

static std::string OvIniPath(){ return GetGameDir()+"\\gta_bridge.ini"; }
static void SaveOverlayMode(){
    char v[4]; sprintf(v,"%d",s_ovMode);
    WritePrivateProfileStringA("OVERLAY","state",v,OvIniPath().c_str());
}
static void LoadOverlayState(){
    s_ovMode = GetPrivateProfileIntA("OVERLAY","state",0,OvIniPath().c_str());
    if(s_ovMode<0||s_ovMode>2) s_ovMode=0;
}
static int PoolUsageByName(const char* sub,int& u,int& m){
    std::string want=sub; for(auto&c:want)c=(char)tolower(c);
    for(auto&kv:g_usage){ std::string k=kv.first; for(auto&c:k)c=(char)tolower(c);
        if(k==want && kv.second(u,m)) return 1; }                       // exact first (Models, not ColModel)
    for(auto&kv:g_usage){ std::string k=kv.first; for(auto&c:k)c=(char)tolower(c);
        if(k.find(want)!=std::string::npos && kv.second(u,m)) return 1; }
    return 0;
}

// ===== Session log (gta_bridge_session.log) — human-readable, crash-safe =====
// FORMAT:
//   ==== GTA BRIDGE SESSION 2026-08-27 14:55:02 ====
//   [14:55:02] INIT asi=v2.3 streaming=<dbMB> lod=<maxLodScale> overlay=<0|1|2>
//   [14:55:10] OVERLAY mode=FULL (user F7)
//   [14:55:11] SAMPLE fps=30.3 avg_ms=33.1 min=31.8 max=32.8 stream_used=10 models=9959/10150
//   ...
//   [15:02:44] POOLWARN <poolname> used>=95%
//   [15:03:00] EXIT duration=478s frames=14320 avg_fps=30.1
static FILE*       g_sessionLog = nullptr;
static bool        g_sessionHeaderWritten = false;
static uint32_t    g_sessionStartTick = 0;
static std::map<std::string,uint32_t> g_poolWarnTick; // throttle POOLWARN per pool per 30s

static void SessionLogWrite(const char* fmt, ...) {
    if(!g_sessionLog) {
        std::string path = GetGameDir() + "\\gta_bridge_session.log";
        fopen_s(&g_sessionLog, path.c_str(), "a");
        if(!g_sessionLog) return;
    }
    SYSTEMTIME st;
    GetLocalTime(&st);
    char prefix[32];
    sprintf(prefix, "[%02d:%02d:%02d] ", st.wHour, st.wMinute, st.wSecond);
    fputs(prefix, g_sessionLog);
    va_list args;
    va_start(args, fmt);
    vfprintf(g_sessionLog, fmt, args);
    va_end(args);
    fputc('\n', g_sessionLog);
    fflush(g_sessionLog);
}

static void SessionInit() {
    if(g_sessionHeaderWritten) return;
    g_sessionHeaderWritten = true;
    g_sessionStartTick = GetTickCount();
    std::string path = GetGameDir() + "\\gta_bridge_session.log";
    fopen_s(&g_sessionLog, path.c_str(), "a");
    if(!g_sessionLog) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(g_sessionLog, "==== GTA BRIDGE SESSION %04d-%02d-%02d %02d:%02d:%02d ====\n",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    // INIT line
    fprintf(g_sessionLog, "[%02d:%02d:%02d] INIT asi=v2.3 streaming=%d lod=%.1f overlay=%d\n",
            st.wHour, st.wMinute, st.wSecond,
            g_streamingMemMb, g_maxLodScale, s_ovMode);
    fflush(g_sessionLog);
}

static void SessionExit() {
    if(!g_sessionLog) return;
    uint32_t now = GetTickCount();
    uint32_t durationMs = now - g_sessionStartTick;
    float durationSec = (float)durationMs / 1000.0f;
    float avgFps = (durationSec > 0.0f) ? (float)s_frameCount / durationSec : 0.0f;
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(g_sessionLog, "[%02d:%02d:%02d] EXIT duration=%.0fs frames=%u avg_fps=%.1f\n",
            st.wHour, st.wMinute, st.wSecond,
            durationSec, s_frameCount, avgFps);
    fflush(g_sessionLog);
    fclose(g_sessionLog);
    g_sessionLog = nullptr;
}

static void StatHudFrame(){
    DWORD now=GetTickCount();
    if(s_lastTick==0){ s_lastTick=now; s_lastCsv=now; return; }
    uint32_t dt=now-s_lastTick; if(dt==0)return; s_lastTick=now; ++s_frameCount;
    s_lastFrameMs=dt;
    double fps=1000.0/dt; if(fps>s_maxFps)s_maxFps=(float)fps; if(fps<s_minFps)s_minFps=(float)fps;
    s_avgMs+=((double)dt-s_avgMs)*0.05;             // smoothed frame ms
    s_ftHist[s_ftIdx]=dt; s_ftIdx=(s_ftIdx+1)%120;
    // F7 edge detect -> cycle mode + persist + session min/max reset + log
    bool f7now=(GetKeyState(VK_F7)&0x8000)!=0;
    if(f7now&&!s_f7Prev){
        s_ovMode=(s_ovMode+1)%3; SaveOverlayMode(); s_minFps=1e9f;s_maxFps=0.f;
        const char* modeStr = s_ovMode==1?"FULL":(s_ovMode==2?"MIN":"OFF");
        SessionLogWrite("OVERLAY mode=%s (user F7)", modeStr);
    }
    s_f7Prev=f7now;
    // 1Hz tick: CSV autolog, session SAMPLE, POOLWARN
    if((now-s_lastCsv)>=1000){
        s_lastCsv=now;
        // CSV autolog when sweep candidate active ([BRIDGE] SWEEP_LOG=1)
        if(s_ovMode&&GetPrivateProfileIntA("BRIDGE","SWEEP_LOG",0,OvIniPath().c_str())){
            int au=-1,uu=-1; bool sm=GetMemUsage(au,uu);
            int tu=-1,tm=-1,mu=-1,mm=-1;
            PoolUsageByName("textur",tu,tm); PoolUsageByName("model",mu,mm);
            FILE*f=nullptr; fopen_s(&f,(GetGameDir()+"\\gta_bridge_stats.csv").c_str(),"a");
            if(f){ if(ftell(f)==0) fputs("ts,fps,min,avg,max,max_ms,streaming_used,textures_used,models_used\n",f);
                   fprintf(f,"%lu,%.1f,%.1f,%.1f,%.1f,%lu,%d,%d,%d\n",(unsigned long)now,
                           fps,s_minFps,(float)(1000.0/s_avgMs),s_maxFps,(unsigned long)s_lastFrameMs,
                           uu,tu>=0?tu:-1,mu>=0?mu:-1); fclose(f);}
        }
        // Session SAMPLE (when overlay visible OR F5 diag page on)
        if(s_ovMode!=0 || s_wantDiag){
            int au=-1,uu=-1; GetMemUsage(au,uu);
            int mu=-1,mm=-1; PoolUsageByName("model",mu,mm);
            SessionLogWrite("SAMPLE fps=%.1f avg_ms=%.1f min=%.1f max=%.1f stream_used=%d models=%d/%d",
                            fps,(float)(1000.0/s_avgMs),s_minFps,s_maxFps,
                            uu,mu>=0?mu:-1,mm>=0?mm:-1);
        }
        // POOLWARN: any pool >=95% used, throttled 30s per pool
        uint32_t nowMs = GetTickCount();
        for(auto &pg : g_poolGlobals){
            int used=0,maxv=0;
            if(!ReadPoolUsage(pg.addr,used,maxv) || maxv<=0) continue;
            if(used*100/maxv >= 95){
                auto it = g_poolWarnTick.find(pg.name);
                if(it==g_poolWarnTick.end() || (nowMs-it->second)>=30000){
                    g_poolWarnTick[pg.name]=nowMs;
                    SessionLogWrite("POOLWARN %s used=%d/%d (%d%%)",pg.name,used,maxv,used*100/maxv);
                }
            }
        }
    }
}
static void StatsText(const char* t,float x,float y,float sc,const StatCol* c){
    StatCol tmp={0,0,0,0};
    if(c){ tmp=*c; g_colourOv=&tmp; }
    DrawTextInternal(t,x,y,sc,sc);                  // c==nullptr -> interface blue like F5
    g_colourOv=nullptr;
}
static void DrawSparkline(char* out){                     // 60-char compact ascii sparkline
    static const char* LV=" _.-oO#";
    for(int i=0;i<60;++i){
        uint32_t ms=s_ftHist[(s_ftIdx+(i*2))%120];
        int l = (ms==0)?0 : ms<20?2 : ms<34?4 : ms<50?5 : 6;
        out[i]=LV[l];
    } out[60]='\0';
}
static void DrawStatsBlock(bool full){
    float sx=10.f,y=105.f; const float lh=13.5f, sc=0.44f;   // same anchor line as F5 diag
    double avfps=1000.0/s_avgMs;
    const StatCol& fc = avfps>50?COL_GREEN:(avfps>30?COL_YELL:COL_RED);
    char b[192];
    StatsText("GTA BRIDGE STATS [F7 FULL/MIN/OFF]",sx,y,sc,nullptr); y+=lh;
    sprintf(b,"FPS %5.1f  (%4.1f ms)",avfps,s_avgMs);
    StatsText(b,sx,y,sc*1.2f,&fc); y+=lh*1.6f;
    if(s_minFps<=s_maxFps) { sprintf(b,"MIN %5.1f   AVG %5.1f   MAX %5.1f",s_minFps,avfps,s_maxFps); StatsText(b,sx,y,sc,nullptr); y+=lh; }
    if(full){
        {   // LOD instrumentation line
            float lodCur = 0.0f;
            safeReadFloat(0x8CD800, lodCur);
            char spdBuf[16];
            if(g_camLayoutOk) sprintf(spdBuf, "%.1f", g_camSpeed);
            else spdBuf[0]='-', spdBuf[1]='\0';
            sprintf(b, "LOD %.2f tgt=%.2f gov=%.2f spd=%s", lodCur, g_lodTarget, GovernorLodFactor(), spdBuf);
            StatsText(b,sx,y,sc,nullptr); y+=lh;
        }
        char sp[62]; DrawSparkline(sp); StatsText(sp,sx,y,sc*0.82f,&COL_GREEN); y+=lh;
        int au,u; if(GetMemUsage(au,u)){ sprintf(b,"STREAMING %d MB used / %d avail",u,au); StatsText(b,sx,y,sc,nullptr); y+=lh; }
        int tu,tm; if(PoolUsageByName("textures",tu,tm)){ sprintf(b,"TEXTURES  %d / %d",tu,tm); StatsText(b,sx,y,sc,nullptr); y+=lh; }
        int mu,mm; if(PoolUsageByName("models",mu,mm)){ sprintf(b,"MODELS    %d / %d",mu,mm); StatsText(b,sx,y,sc,nullptr); y+=lh; }
    }
}

static bool TestShouldDraw(){
    static bool should=false, prev=false, curr=false;
    curr=(GetKeyState(vkBridgeText)&0x8000)!=0;
    if(curr && !prev){ if(!should){ current_limit=0; should=true; } else { current_limit+=limits_per_page; should=current_limit<g_usage.size(); } }
    prev=curr; return should;
}
static void DrawBridgeOverlay(){
    DrawHUD.fun?DrawHUD.fun():void();
    // dynamic render scale runs EVERY frame (before any early return)
    DynamicRenderScale();
    // streaming supervisor: pressure-driven eviction + priority fast-load drain
    StreamingSupervisor();
    s_wantDiag = TestShouldDraw();
    StatHudFrame();
    if(!s_wantDiag && s_ovMode==0) return;
    if(!BeginDraw()) return;
    if(s_ovMode) DrawStatsBlock(s_ovMode==1);
    if(s_wantDiag){
    // header
    DrawText("GTA BRIDGE — diag (F5 page)");
    // system mem vs streaming mem
    MEMORYSTATUSEX sys{sizeof(sys)}; if(GlobalMemoryStatusEx(&sys)){ char b[128]; sprintf(b,"SYS RAM: %llu / %llu MB (load %lu%%)", (sys.ullTotalPhys - sys.ullAvailPhys)/1048576, sys.ullTotalPhys/1048576, sys.dwMemoryLoad); DrawText(b); }
    int a=-1,u=-1; if(GetMemUsage(a,u)){ char b[64]; sprintf(b,"STREAM MEM avail %d used %d MB",a,u); DrawText(b); }
    { char b[64]; sprintf(b,"LOD scale: %.2f (max %.2f)", g_maxLodScale>0?1.0f:g_maxLodScale, g_maxLodScale); DrawText(b); }
    // SkyGfx hint if present
    { std::ifstream f(GetGameDir()+"\\skygfx.ini"); if(f){ DrawText("SkyGfx: present (PS2/Xbox pipes)"); } }
    // pools paged
    unsigned i=0,drawn=0;
    for(auto &kv: g_usage){ if(i>=current_limit && (i<current_limit+limits_per_page || drawn<limits_per_page)){ int used=-1,maxv=-1; if(kv.second(used,maxv)){ char ub[64]; sprintf(ub,"%d / %d",used,maxv); DrawLine(kv.first.c_str(),ub); ++drawn; } } ++i; }
    }
    EndDraw();
}
static void PatchDrawer(){ LoadOverlayState(); SessionInit(); DrawHUD.fun = injector::MakeCALL(0x53E4FF, DrawBridgeOverlay).get(); }

static DWORD WINAPI PipeServerThread(LPVOID) {
    while(!g_shutdown) {
        HANDLE hPipe = CreateNamedPipeA(
            PIPE_NAME,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1, 4096, 4096, 0, NULL);
        if(hPipe==INVALID_HANDLE_VALUE) { Sleep(500); continue; }
        BOOL connected = ConnectNamedPipe(hPipe, NULL) ? TRUE : (GetLastError()==ERROR_PIPE_CONNECTED);
        if(!connected) { CloseHandle(hPipe); if(g_shutdown) break; continue; }
        // serve this client until disconnect
        char buf[1024];
        DWORD readBytes=0;
        while(!g_shutdown) {
            BOOL ok = ReadFile(hPipe, buf, sizeof(buf)-1, &readBytes, NULL);
            if(!ok || readBytes==0) break;
            buf[readBytes]='\0';
            std::string line(buf, readBytes);
            line = trim(line);
            std::string reply;
            if(line=="HELLO") {
                reply = "OK GTABRIDGE 2.0\n";
            } else if(line=="PING") {
                reply = "PONG\n";
            } else if(line=="STATUS") {
                reply = "STATUS alive\n";
            } else if(line=="MEM") {
                int a=-1,u=-1;
                if(GetMemUsage(a,u)) { char tmp[64]; sprintf(tmp,"MEM %d %d\n",a,u); reply=tmp; }
                else reply="MEM -1 -1\n";
            } else if(line.rfind("USAGE",0)==0) {
                std::string name = trim(line.size()>5?line.substr(5):"");
                int used=-1,maxv=-1;
                auto it=g_usage.find(name);
                if(it!=g_usage.end() && it->second(used,maxv)) {
                    char tmp[128]; sprintf(tmp,"USAGE %s %d %d\n",name.c_str(),used,maxv); reply=tmp;
                } else {
                    char tmp[128]; sprintf(tmp,"USAGE %s -1 -1\n",name.c_str()); reply=tmp;
                }
            } else if(line.rfind("SHM_OPEN",0)==0) {
                // SHM_OPEN <size_mb> — map launcher-created shared section
                std::string arg = trim(line.size()>8?line.substr(8):"");
                try {
                    size_t mb = (size_t)std::stoul(arg);
                    size_t bytes = mb * 1024 * 1024;
                    if(g_shmView) { reply="OK SHM already\n"; }
                    else {
                        g_shmHandle = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, SHM_NAME);
                        if(!g_shmHandle) { reply="ERR shm open failed\n"; }
                        else {
                            g_shmView = MapViewOfFile(g_shmHandle, FILE_MAP_ALL_ACCESS, 0, 0, bytes);
                            if(!g_shmView) { CloseHandle(g_shmHandle); g_shmHandle=NULL; reply="ERR shm map failed\n"; }
                            else { g_shmSize = bytes; char tmp[64]; sprintf(tmp,"OK SHM %zu\n", bytes); reply=tmp; }
                        }
                    }
                } catch(...) { reply="ERR shm arg\n"; }
            } else if(line.rfind("SHM_READ",0)==0) {
                // SHM_READ <offset> <len> — hex dump of shared bytes
                if(!g_shmView) { reply="ERR shm not open\n"; }
                else {
                    size_t off=0, len=0;
                    sscanf(line.c_str(), "SHM_READ %zu %zu", &off, &len);
                    if(len>256) len=256;
                    if(off+len>g_shmSize) { reply="ERR shm range\n"; }
                    else {
                        unsigned char* p = (unsigned char*)g_shmView + off;
                        std::string hex="OK SHMREAD ";
                        char hx[4];
                        for(size_t i=0;i<len;++i){ sprintf(hx,"%02X",p[i]); hex+=hx; }
                        hex+="\n"; reply=hex;
                    }
                }
            } else if(line=="SHM_STAT") {
                char tmp[96]; sprintf(tmp,"SHMSTAT %p %p %zu\n",(void*)g_shmHandle,g_shmView,g_shmSize); reply=tmp;
            } else {
                reply="ERR unknown\n";
            }
            DWORD written=0;
            WriteFile(hPipe, reply.c_str(), (DWORD)reply.size(), &written, NULL);
            FlushFileBuffers(hPipe);
        }
        DisconnectNamedPipe(hPipe);
        CloseHandle(hPipe);
    }
    return 0;
}

// -------- DllMain --------
BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        std::string gameDir = GetGameDir();
        ApplyBridgeIni(gameDir + "\\gta_bridge.ini");
        RegisterUsageReaders();
        ApplyStreamingMemory(g_streamingMemMb);
        if(g_vegetationBoost) ApplyVegetationPatches();
        PatchDrawer();
        g_shutdown = false;
        g_thread = CreateThread(NULL, 0, PipeServerThread, NULL, 0, NULL);
    } else if(reason==DLL_PROCESS_DETACH) {
        SessionExit();
        g_shutdown = true;
        // wake pipe if waiting: connect as client to unblock ConnectNamedPipe
        HANDLE h = CreateFileA(PIPE_NAME, GENERIC_READ|GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
        if(h!=INVALID_HANDLE_VALUE) CloseHandle(h);
        if(g_thread) { WaitForSingleObject(g_thread, 1500); CloseHandle(g_thread); g_thread=NULL; }
    }
    return TRUE;
}
