/**
 * GTA SA Engine-Grade Performance Overlay — ASI Plugin
 *
 * Reuses existing CHud::Draw hook pattern (0x53E4FF) and native font
 * rendering from bridge.cpp.  D3D9 EndScene vtable hook for Present-time
 * rendering.  F7 cycle FULL / MIN / OFF, persistent via gta_bridge.ini
 * [OVERLAY] state=N.  CSV autolog when sweep_log=1 in [BRIDGE].
 *
 * Build: premake5 vs2022 -> MSBuild Win32 x86 -> memory_overlay.asi
 * cp1252 console ASCII only.
 */

#include <windows.h>
#include <d3d9.h>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
#include <cstdint>

// injector + pool struct (reuse from asi_bridge)
#include "../asi_bridge/src/shared/injector/injector.hpp"
#include "../asi_bridge/src/shared/structs/CPool.h"

// ============================================================================
// Constants
// ============================================================================

// D3D9 device pointer (game global)
#define D3D9_DEVICE_PTR    0xC43C70

// CHud::Draw hook site (same as bridge.cpp — we chain via vtable instead)
// We use D3D9 EndScene vtable hook to avoid conflict with bridge's CHud hook.
#define D3D9_ENDSCENE_IDX  42

// CPools globals (plugin-sdk CPools.cpp lines 9-25, VERIFIED)
#define POOL_GLOBALS_BASE  0xB74484

// Streaming memory (VERIFIED plugin-sdk CStreaming.cpp:11)
#define STREAMING_AVAIL    0x8A5A80
#define STREAMING_USED     0x8E4CB4

// Native font function addresses (reused from bridge.cpp)
#define FONT_SETSCALE      0x719380
#define FONT_SETCOLOR      0x719430
#define FONT_SETFONTSTYLE  0x719490
#define FONT_SETDROPCOLOR  0x719510
#define FONT_SETEDGE       0x719590
#define FONT_SETPROP       0x7195B0
#define FONT_SETBG         0x7195C0
#define FONT_SETJUSTIFY    0x719600
#define FONT_SETRIGHTWRAP  0x7194F0
#define FONT_SETWRAPX      0x7194D0
#define FONT_SETORIENT     0x719610
#define FONT_PRINTSTRING   0x71A700
#define RSGLOBAL           0xC17040
#define GETINTERFACECOLOUR 0x58FEA0
#define INTERFACECOLOUR    0xBAB22C

// Sparkline
#define SPARKLINE_FRAMES   120

// ============================================================================
// Types
// ============================================================================

typedef HRESULT (__stdcall *EndSceneFn)(IDirect3DDevice9*);

struct CRGBA {
    unsigned char r, g, b, a;
    CRGBA() {}
    CRGBA(unsigned char R, unsigned char G, unsigned char B, unsigned char A)
        : r(R), g(G), b(B), a(A) {}
};

// ============================================================================
// Global state
// ============================================================================

static IDirect3DDevice9* g_device = nullptr;
static uintptr_t*        g_vtable = nullptr;
static EndSceneFn        g_originalEndScene = nullptr;
static bool              g_hooked = false;

// Overlay state
enum OverlayState { OVERLAY_FULL = 0, OVERLAY_MIN = 1, OVERLAY_OFF = 2 };
static OverlayState g_overlayState = OVERLAY_FULL;
static bool         g_overlayInited = false;

// FPS tracking
static LARGE_INTEGER g_freq = {};
static LARGE_INTEGER g_lastTime = {};
static float         g_fpsCurrent = 0.0f;
static float         g_frameMsCurrent = 0.0f;
static float         g_fpsMin = 999.0f;
static float         g_fpsAvg = 0.0f;
static float         g_fpsMax = 0.0f;
static int           g_fpsCount = 0;
static float         g_fpsSum = 0.0f;
static float         g_fpsSessionMin = 999.0f;
static float         g_fpsSessionMax = 0.0f;
static float         g_fpsSessionSum = 0.0f;
static int           g_fpsSessionCount = 0;
static float         g_frameMsMax = 0.0f;

// Sparkline buffer (circular, last N frame times in ms)
static float  g_sparkline[SPARKLINE_FRAMES] = {};
static int    g_sparklinePos = 0;
static int    g_sparklineCount = 0;

// Pool data (cached every 500ms)
static int g_streamAvailMb = 0;
static int g_streamUsedMb = 0;
static int g_texUsed = 0, g_texMax = 0;
static int g_modelUsed = 0, g_modelMax = 0;
static int g_buildUsed = 0, g_buildMax = 0;
static uint32_t g_lastPoolTick = 0;

// CSV autolog
static bool  g_sweepLog = false;
static bool  g_csvHeaderWritten = false;
static uint32_t g_lastCsvTick = 0;
static char  g_csvPath[MAX_PATH] = {};

// Key state (F7)
static bool g_f7Prev = false;

// ============================================================================
// Safe memory reads (same pattern as bridge.cpp)
// ============================================================================

static bool SafeReadU32(uintptr_t addr, uint32_t& out) {
    __try { out = *(volatile uint32_t*)addr; return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}

static bool SafeReadFloat(uintptr_t addr, float& out) {
    __try { out = *(volatile float*)addr; return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}

// ============================================================================
// Pool reading (mirrors bridge.cpp ReadPoolUsage)
// ============================================================================

using GPool = CPool<char, char>;

static bool ReadPoolUsage(uintptr_t globalAddr, int& used, int& maxv) {
    uint32_t raw = 0;
    if (!SafeReadU32(globalAddr, raw)) return false;
    GPool* p = (GPool*)(uintptr_t)raw;
    if (!p) return false;
    __try {
        maxv = p->m_Size;
        if (maxv <= 0 || maxv > 10000000) return false;
        used = 0;
        for (int i = 0; i < maxv; ++i)
            if (!p->IsFreeSlotAtIndex(i)) ++used;
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}

// ============================================================================
// Game dir / ini helpers
// ============================================================================

static std::string GetGameDir() {
    char path[MAX_PATH];
    GetModuleFileNameA(NULL, path, MAX_PATH);
    std::string s(path);
    size_t pos = s.find_last_of("\\/");
    if (pos != std::string::npos) s = s.substr(0, pos);
    return s;
}

static std::string Trim(const std::string& s) {
    size_t a = 0;
    while (a < s.size() && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r' || s[a] == '\n')) ++a;
    size_t b = s.size();
    while (b > a && (s[b-1] == ' ' || s[b-1] == '\t' || s[b-1] == '\r' || s[b-1] == '\n')) --b;
    return s.substr(a, b - a);
}

static void ParseOverlayIni() {
    std::string iniPath = GetGameDir() + "\\gta_bridge.ini";
    std::ifstream f(iniPath);
    if (!f) return;
    std::string line, section;
    while (std::getline(f, line)) {
        std::string t = Trim(line);
        if (t.empty() || t[0] == ';' || t[0] == '#' || t[0] == '/') continue;
        if (t.front() == '[' && t.back() == ']') {
            section = Trim(t.substr(1, t.size() - 2));
            for (char& c : section) c = toupper(c);
            continue;
        }
        if (section != "OVERLAY") continue;
        auto eq = t.find('=');
        if (eq == std::string::npos) continue;
        std::string k = Trim(t.substr(0, eq));
        std::string v = Trim(t.substr(eq + 1));
        for (char& c : k) c = toupper(c);
        auto sc = v.find(';');
        if (sc != std::string::npos) v = Trim(v.substr(0, sc));
        if (k == "STATE") {
            int s = 0;
            try { s = std::stoi(v); } catch (...) {}
            if (s >= 0 && s <= 2) g_overlayState = (OverlayState)s;
        }
    }
    // Also check [BRIDGE] for sweep_log
    // Re-parse for BRIDGE section
    f.clear(); f.seekg(0);
    section.clear();
    while (std::getline(f, line)) {
        std::string t = Trim(line);
        if (t.empty() || t[0] == ';' || t[0] == '#' || t[0] == '/') continue;
        if (t.front() == '[' && t.back() == ']') {
            section = Trim(t.substr(1, t.size() - 2));
            for (char& c : section) c = toupper(c);
            continue;
        }
        if (section != "BRIDGE") continue;
        auto eq = t.find('=');
        if (eq == std::string::npos) continue;
        std::string k = Trim(t.substr(0, eq));
        std::string v = Trim(t.substr(eq + 1));
        for (char& c : k) c = toupper(c);
        auto sc = v.find(';');
        if (sc != std::string::npos) v = Trim(v.substr(0, sc));
        if (k == "SWEEP_LOG") {
            g_sweepLog = (v == "1" || v == "true" || v == "yes");
        }
    }
}

static void WriteOverlayState(OverlayState state) {
    std::string iniPath = GetGameDir() + "\\gta_bridge.ini";
    // Read existing ini
    std::ifstream f(iniPath);
    std::vector<std::string> lines;
    std::string line;
    bool foundOverlay = false;
    bool inOverlay = false;
    while (std::getline(f, line)) {
        std::string t = Trim(line);
        if (t.front() == '[' && t.back() == ']') {
            std::string s = Trim(t.substr(1, t.size() - 2));
            for (char& c : s) c = toupper(c);
            inOverlay = (s == "OVERLAY");
        } else if (inOverlay && t.find('=') != std::string::npos) {
            std::string k = Trim(t.substr(0, t.find('=')));
            for (char& c : k) c = toupper(c);
            if (k == "STATE") {
                char buf[32];
                sprintf(buf, "state=%d", (int)state);
                lines.push_back(buf);
                foundOverlay = true;
                continue;
            }
        }
        lines.push_back(line);
    }
    f.close();
    if (!foundOverlay) {
        // Add [OVERLAY] section
        lines.push_back("[OVERLAY]");
        char buf[32];
        sprintf(buf, "state=%d", (int)state);
        lines.push_back(buf);
    }
    std::ofstream out(iniPath);
    for (const auto& l : lines) out << l << "\n";
}

// ============================================================================
// Native font rendering (reuses addresses from bridge.cpp)
// ============================================================================

static void BeginDraw(float& cx, float& cy) {
    cx = 10.0f; cy = 10.0f;
}

static void DrawTextInternal(const char* text, float x, float y,
                             float sx, float sy,
                             unsigned char r, unsigned char g,
                             unsigned char b, unsigned char a) {
    static void* pInterfaceColour = injector::lazy_pointer<INTERFACECOLOUR>::get();
    static void* pGetInterfaceColour = injector::lazy_pointer<GETINTERFACECOLOUR>::get();
    static int* pRsGlobal = injector::lazy_pointer<RSGLOBAL>::get();
    static void (*SetScale)(float, float) = injector::lazy_pointer<FONT_SETSCALE>::get();
    static void (*SetColor)(void*) = injector::lazy_pointer<FONT_SETCOLOR>::get();
    static void (*SetFontStyle)(short) = injector::lazy_pointer<FONT_SETFONTSTYLE>::get();
    static void (*SetDropColor)(CRGBA) = injector::lazy_pointer<FONT_SETDROPCOLOR>::get();
    static void (*SetEdge)(short) = injector::lazy_pointer<FONT_SETEDGE>::get();
    static void (*SetProportional)(bool) = injector::lazy_pointer<FONT_SETPROP>::get();
    static void (*SetBackground)(bool, bool) = injector::lazy_pointer<FONT_SETBG>::get();
    static void (*SetJustify)(bool) = injector::lazy_pointer<FONT_SETJUSTIFY>::get();
    static void (*SetRightJustifyWrap)(float) = injector::lazy_pointer<FONT_SETRIGHTWRAP>::get();
    static void (*SetWrapx)(float) = injector::lazy_pointer<FONT_SETWRAPX>::get();
    static void (*SetOrientation)(int) = injector::lazy_pointer<FONT_SETORIENT>::get();
    static void (*PrintString)(float, float, const char*) = injector::lazy_pointer<FONT_PRINTSTRING>::get();

    CRGBA rgba(r, g, b, a);
    if (pGetInterfaceColour && pInterfaceColour)
        ((CRGBA*(__thiscall*)(void*, CRGBA*, unsigned char))pGetInterfaceColour)
            (pInterfaceColour, &rgba, 4);

    float screenx = (float)((signed int)*(pRsGlobal + 1)) / 640.0f;
    float screeny = (float)((signed int)*(pRsGlobal + 2)) / 448.0f;

    SetFontStyle(1);
    SetJustify(0);
    SetBackground(0, 0);
    SetProportional(true);
    SetOrientation(1);
    SetRightJustifyWrap(0);
    SetWrapx(640.0f * screenx);
    SetEdge(1);
    SetDropColor(CRGBA(0, 0, 0, 0xFF));
    SetColor(&rgba);
    SetScale(screenx * sx, screeny * sy);
    PrintString(screenx * x, screeny * y, text);
}

static void DrawText(float& cx, float& cy, const char* text,
                     unsigned char r, unsigned char g,
                     unsigned char b, unsigned char a,
                     float sx = 0.60f, float sy = 0.89f) {
    DrawTextInternal(text, cx, cy, sx, sy, r, g, b, a);
    cy += sy * 20.0f;
}

// ============================================================================
// FPS calculation
// ============================================================================

static void UpdateFps() {
    if (g_freq.QuadPart == 0) {
        QueryPerformanceFrequency(&g_freq);
        QueryPerformanceCounter(&g_lastTime);
        return;
    }
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    double dt = (double)(now.QuadPart - g_lastTime.QuadPart) / (double)g_freq.QuadPart;
    g_lastTime = now;

    if (dt <= 0.0) dt = 0.001;
    g_frameMsCurrent = (float)(dt * 1000.0);
    g_fpsCurrent = 1.0f / (float)dt;

    // Rolling average (last 30 frames)
    g_fpsSum += g_fpsCurrent;
    g_fpsCount++;
    if (g_fpsCount >= 30) {
        g_fpsAvg = g_fpsSum / (float)g_fpsCount;
        g_fpsSum = 0.0f;
        g_fpsCount = 0;
    }

    // Session stats
    g_fpsSessionSum += g_fpsCurrent;
    g_fpsSessionCount++;
    if (g_fpsCurrent < g_fpsSessionMin) g_fpsSessionMin = g_fpsCurrent;
    if (g_fpsCurrent > g_fpsSessionMax) g_fpsSessionMax = g_fpsCurrent;
    if (g_frameMsCurrent > g_frameMsMax) g_frameMsMax = g_frameMsCurrent;

    // Sparkline
    g_sparkline[g_sparklinePos] = g_frameMsCurrent;
    g_sparklinePos = (g_sparklinePos + 1) % SPARKLINE_FRAMES;
    if (g_sparklineCount < SPARKLINE_FRAMES) g_sparklineCount++;
}

// ============================================================================
// Pool data refresh (every 500ms)
// ============================================================================

static void RefreshPoolData() {
    uint32_t now = GetTickCount();
    if (now - g_lastPoolTick < 500) return;
    g_lastPoolTick = now;

    uint32_t availRaw = 0, usedRaw = 0;
    if (SafeReadU32(STREAMING_AVAIL, availRaw))
        g_streamAvailMb = (int)(availRaw / 1048576u);
    if (SafeReadU32(STREAMING_USED, usedRaw))
        g_streamUsedMb = (int)(usedRaw / 1048576u);

    // Texture pool = PtrNodeSingle (index 0) — textures use PtrNodeSingle
    ReadPoolUsage(POOL_GLOBALS_BASE + 0, g_texUsed, g_texMax);       // PtrNodeSingle
    // Model pool = Buildings (index 4)
    ReadPoolUsage(POOL_GLOBALS_BASE + 16, g_modelUsed, g_modelMax);  // Buildings
    // Also read Buildings for streaming bar
    ReadPoolUsage(POOL_GLOBALS_BASE + 16, g_buildUsed, g_buildMax);
}

// ============================================================================
// CSV autolog
// ============================================================================

static void WriteCsvLog() {
    if (!g_sweepLog) return;
    uint32_t now = GetTickCount();
    if (now - g_lastCsvTick < 1000) return;
    g_lastCsvTick = now;

    if (g_csvPath[0] == '\0') {
        sprintf(g_csvPath, "%s\\gta_bridge_stats.csv", GetGameDir().c_str());
    }

    std::ofstream csv(g_csvPath, std::ios::app);
    if (!csv) return;

    if (!g_csvHeaderWritten) {
        csv << "ts,fps,min,avg,max,max_ms,streaming,textures,models\n";
        g_csvHeaderWritten = true;
    }

    SYSTEMTIME st;
    GetLocalTime(&st);
    char ts[64];
    sprintf(ts, "%04d-%02d-%02d %02d:%02d:%02d.%03d",
            st.wYear, st.wMonth, st.wDay,
            st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);

    csv << ts << ","
        << g_fpsCurrent << ","
        << g_fpsSessionMin << ","
        << (g_fpsSessionCount > 0 ? g_fpsSessionSum / g_fpsSessionCount : 0.0f) << ","
        << g_fpsSessionMax << ","
        << g_frameMsMax << ","
        << g_streamUsedMb << "/" << g_streamAvailMb << ","
        << g_texUsed << "/" << g_texMax << ","
        << g_modelUsed << "/" << g_modelMax << "\n";
    csv.flush();
}

// ============================================================================
// FPS color helper
// ============================================================================

static void FpsColor(float fps, unsigned char& r, unsigned char& g, unsigned char& b) {
    if (fps >= 50.0f)  { r = 0x66; g = 0xCC; b = 0x66; }  // green
    else if (fps >= 30.0f) { r = 0xFF; g = 0xFF; b = 0x00; }  // yellow
    else                 { r = 0xFF; g = 0x00; b = 0x00; }  // red
}

// ============================================================================
// Sparkline render
// ============================================================================

static void RenderSparkline(float& cx, float& cy) {
    if (g_sparklineCount < 2) return;

    // Find max ms for scaling
    float maxMs = 0.0f;
    for (int i = 0; i < g_sparklineCount; ++i) {
        if (g_sparkline[i] > maxMs) maxMs = g_sparkline[i];
    }
    if (maxMs < 1.0f) maxMs = 33.0f; // ~30fps floor
    if (maxMs < 33.0f) maxMs = 33.0f;

    int count = g_sparklineCount;
    int start = (g_sparklinePos - count + SPARKLINE_FRAMES) % SPARKLINE_FRAMES;

    // Render sparkline as individual characters (block elements)
    // We use the native font to draw a single line with sparkline chars
    // Since we can't do pixel-perfect rendering with the game font,
    // render a text-based representation
    char sparkBuf[256];
    int pos = 0;
    sparkBuf[pos++] = '[';

    // Scale: 5 height levels using block chars
    static const char levels[] = " \x81\x82\x83\x84\x85"; // space, low to full block
    // Use ASCII-safe chars: _ . o O # for 5 levels
    static const char asciiLevels[] = " _.oO#";

    for (int i = 0; i < count && pos < 250; ++i) {
        int idx = (start + i) % SPARKLINE_FRAMES;
        float ms = g_sparkline[idx];
        int level = (int)((ms / maxMs) * 4.0f);
        if (level < 0) level = 0;
        if (level > 4) level = 4;
        sparkBuf[pos++] = asciiLevels[level];
    }
    sparkBuf[pos++] = ']';
    sparkBuf[pos] = '\0';

    DrawText(cx, cy, sparkBuf, 0xAA, 0xAA, 0xAA, 0xFF, 0.40f, 0.60f);
}

// ============================================================================
// Main overlay draw
// ============================================================================

static void DrawOverlay() {
    if (g_overlayState == OVERLAY_OFF) return;
    if (!g_device) return;

    // Update FPS every frame
    UpdateFps();

    // Refresh pool data periodically
    RefreshPoolData();

    // CSV autolog
    WriteCsvLog();

    // Check F7 key
    bool f7Curr = (GetKeyState(VK_F7) & 0x8000) != 0;
    if (f7Curr && !g_f7Prev) {
        g_overlayState = (OverlayState)((g_overlayState + 1) % 3);
        WriteOverlayState(g_overlayState);
    }
    g_f7Prev = f7Curr;

    if (g_overlayState == OVERLAY_OFF) return;

    // ---- Draw backdrop ----
    // We can't easily draw a filled rect with the native font system,
    // so we draw the backdrop using D3D9 directly
    D3DVIEWPORT9 vp;
    g_device->GetViewport(&vp);

    // Semi-transparent dark backdrop
    struct Vertex { float x, y, z, rhw; DWORD color; };
    Vertex verts[4] = {
        { 0.0f, 0.0f, 0.0f, 1.0f, 0xB4000000 },
        { vp.Width * 0.38f, 0.0f, 0.0f, 1.0f, 0xB4000000 },
        { 0.0f, 300.0f, 0.0f, 1.0f, 0xB4000000 },
        { vp.Width * 0.38f, 300.0f, 0.0f, 1.0f, 0xB4000000 },
    };

    g_device->SetRenderState(D3DRS_ALPHABLENDENABLE, TRUE);
    g_device->SetRenderState(D3DRS_SRCBLEND, D3DBLEND_SRCALPHA);
    g_device->SetRenderState(D3DRS_DESTBLEND, D3DBLEND_INVSRCALPHA);
    g_device->SetRenderState(D3DRS_ZENABLE, FALSE);
    g_device->SetRenderState(D3DRS_FOGENABLE, FALSE);
    g_device->SetTexture(0, NULL);
    g_device->SetFVF(D3DFVF_XYZRHW | D3DFVF_DIFFUSE);
    g_device->DrawPrimitiveUP(D3DPT_TRIANGLESTRIP, 2, verts, sizeof(Vertex));

    // Restore some states for font rendering
    g_device->SetRenderState(D3DRS_ZENABLE, TRUE);

    // ---- Draw text overlay ----
    float cx, cy;
    BeginDraw(cx, cy);

    // FPS line
    unsigned char fr, fg, fb;
    FpsColor(g_fpsCurrent, fr, fg, fb);
    char fpsBuf[64];
    sprintf(fpsBuf, "FPS  %.1f (%.1f ms)", g_fpsCurrent, g_frameMsCurrent);
    DrawText(cx, cy, fpsBuf, fr, fg, fb, 0xFF, 0.85f, 1.10f);

    if (g_overlayState == OVERLAY_FULL) {
        // Session stats
        float avg = g_fpsSessionCount > 0 ? g_fpsSessionSum / g_fpsSessionCount : 0.0f;
        char statBuf[128];
        sprintf(statBuf, "MIN %.1f  AVG %.1f  MAX %.1f (session)",
                g_fpsSessionMin, avg, g_fpsSessionMax);
        DrawText(cx, cy, statBuf, 0xCC, 0xCC, 0xCC, 0xFF, 0.55f, 0.80f);

        // Sparkline
        RenderSparkline(cx, cy);

        // Streaming bar
        char streamBuf[128];
        int pct = g_streamAvailMb > 0 ? (g_streamUsedMb * 100 / g_streamAvailMb) : 0;
        int barLen = 20;
        int filled = (pct * barLen) / 100;
        if (filled > barLen) filled = barLen;
        char bar[32];
        for (int i = 0; i < barLen; ++i)
            bar[i] = (i < filled) ? '#' : '.';
        bar[barLen] = '\0';
        sprintf(streamBuf, "STREAMING  %d/%d MB  [%s]",
                g_streamUsedMb, g_streamAvailMb, bar);
        DrawText(cx, cy, streamBuf, 0xBB, 0xBB, 0xBB, 0xFF, 0.50f, 0.75f);

        // Textures
        char texBuf[128];
        sprintf(texBuf, "TEXTURES %d/%d MB",
                g_texUsed, g_texMax > 0 ? g_texMax : 0);
        DrawText(cx, cy, texBuf, 0xBB, 0xBB, 0xBB, 0xFF, 0.50f, 0.75f);

        // Models
        char modelBuf[128];
        sprintf(modelBuf, "MODELS   %d/%d",
                g_modelUsed, g_modelMax > 0 ? g_modelMax : 0);
        DrawText(cx, cy, modelBuf, 0xBB, 0xBB, 0xBB, 0xFF, 0.50f, 0.75f);

        // Toggle hint
        DrawText(cx, cy, "[F7] FULL / MIN / OFF", 0x88, 0x88, 0x88, 0xFF, 0.40f, 0.60f);
    } else {
        // MIN mode: only FPS + streaming bar
        char streamBuf[64];
        sprintf(streamBuf, "STREAM %d/%d MB",
                g_streamUsedMb, g_streamAvailMb);
        DrawText(cx, cy, streamBuf, 0xBB, 0xBB, 0xBB, 0xFF, 0.45f, 0.65f);
    }
}

// ============================================================================
// D3D9 EndScene vtable hook
// ============================================================================

static HRESULT __stdcall EndSceneHook(IDirect3DDevice9* device) {
    // Store device on first call
    if (!g_device) {
        g_device = device;
    }

    // Draw overlay
    DrawOverlay();

    // Call original
    return g_originalEndScene(device);
}

static bool HookEndScene() {
    if (g_hooked) return true;

    // Get D3D9 device from game global
    uint32_t devPtr = 0;
    if (!SafeReadU32(D3D9_DEVICE_PTR, devPtr) || devPtr == 0) {
        // Try to find device via proxy
        return false;
    }

    g_device = (IDirect3DDevice9*)(uintptr_t)devPtr;
    if (!g_device) return false;

    // Read vtable
    g_vtable = *(uintptr_t**)g_device;
    if (!g_vtable) return false;

    // Save original EndScene
    g_originalEndScene = (EndSceneFn)g_vtable[D3D9_ENDSCENE_IDX];

    // Hook: write our function pointer into vtable
    DWORD oldProtect;
    if (!VirtualProtect(&g_vtable[D3D9_ENDSCENE_IDX], sizeof(uintptr_t),
                        PAGE_EXECUTE_READWRITE, &oldProtect)) {
        return false;
    }

    g_vtable[D3D9_ENDSCENE_IDX] = (uintptr_t)EndSceneHook;

    VirtualProtect(&g_vtable[D3D9_ENDSCENE_IDX], sizeof(uintptr_t),
                   oldProtect, &oldProtect);

    g_hooked = true;
    return true;
}

static void UnhookEndScene() {
    if (!g_hooked || !g_vtable || !g_originalEndScene) return;

    DWORD oldProtect;
    VirtualProtect(&g_vtable[D3D9_ENDSCENE_IDX], sizeof(uintptr_t),
                   PAGE_EXECUTE_READWRITE, &oldProtect);
    g_vtable[D3D9_ENDSCENE_IDX] = (uintptr_t)g_originalEndScene;
    VirtualProtect(&g_vtable[D3D9_ENDSCENE_IDX], sizeof(uintptr_t),
                   oldProtect, &oldProtect);
    g_hooked = false;
}

// ============================================================================
// Init thread (delayed to ensure D3D9 device is created)
// ============================================================================

static DWORD WINAPI InitThread(LPVOID) {
    // Wait for game to initialize D3D9
    for (int i = 0; i < 300; ++i) {
        uint32_t devPtr = 0;
        if (SafeReadU32(D3D9_DEVICE_PTR, devPtr) && devPtr != 0) {
            break;
        }
        Sleep(100);
    }

    // Parse ini
    ParseOverlayIni();

    // Hook EndScene
    for (int i = 0; i < 50; ++i) {
        if (HookEndScene()) break;
        Sleep(200);
    }

    g_overlayInited = true;
    return 0;
}

// ============================================================================
// DLL entry point
// ============================================================================

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        CreateThread(NULL, 0, InitThread, NULL, 0, NULL);
    } else if (reason == DLL_PROCESS_DETACH) {
        UnhookEndScene();
    }
    return TRUE;
}

// ============================================================================
// ASI exports
// ============================================================================

extern "C" {
    __declspec(dllexport) void __cdecl Init() {}
    __declspec(dllexport) void __cdecl Shutdown() { UnhookEndScene(); }
    __declspec(dllexport) void __cdecl OnGameStart() {}
    __declspec(dllexport) void __cdecl OnGameExit() { UnhookEndScene(); }
}