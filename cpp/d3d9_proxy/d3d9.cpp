// GTA Bridge d3d9 proxy — FusionFix pattern (github.com/ThirteenAG/GTAIV.EFLC.FusionFix)
// Sits in the game dir as d3d9.dll. Loads vulkan.dll (DXVK renamed) if present,
// else falls back to the system d3d9.dll. All D3D9 exports are forwarded 1:1,
// so skygfx / gta_bridge / SilentPatch see a normal D3D9 interface while DXVK
// translates everything to Vulkan (unlocks >SM3.0 VRAM budgets on modern GPUs).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

struct d3d9_dll
{
    HMODULE dll;
    FARPROC D3DPERF_BeginEvent;
    FARPROC D3DPERF_EndEvent;
    FARPROC D3DPERF_GetStatus;
    FARPROC D3DPERF_QueryRepeatFrame;
    FARPROC D3DPERF_SetMarker;
    FARPROC D3DPERF_SetOptions;
    FARPROC D3DPERF_SetRegion;
    FARPROC DebugSetLevel;
    FARPROC DebugSetMute;
    FARPROC Direct3D9EnableMaximizedWindowedModeShim;
    FARPROC Direct3DCreate9;
    FARPROC Direct3DCreate9Ex;
    FARPROC Direct3DCreate9On12;
    FARPROC Direct3DCreate9On12Ex;
    FARPROC Direct3DShaderValidatorCreate9;
    FARPROC PSGPError;
    FARPROC PSGPSampleTexture;
} d3d9;

#define STUB(name) __declspec(naked) void _##name() { _asm { jmp [d3d9.name] } }
STUB(D3DPERF_BeginEvent)
STUB(D3DPERF_EndEvent)
STUB(D3DPERF_GetStatus)
STUB(D3DPERF_QueryRepeatFrame)
STUB(D3DPERF_SetMarker)
STUB(D3DPERF_SetOptions)
STUB(D3DPERF_SetRegion)
STUB(DebugSetLevel)
STUB(DebugSetMute)
STUB(Direct3D9EnableMaximizedWindowedModeShim)
STUB(Direct3DCreate9)
STUB(Direct3DCreate9Ex)
STUB(Direct3DCreate9On12)
STUB(Direct3DCreate9On12Ex)
STUB(Direct3DShaderValidatorCreate9)
STUB(PSGPError)
STUB(PSGPSampleTexture)

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
    {
        d3d9.dll = NULL;

        // DXVK first: vulkan.dll next to the game exe (deployed by the launcher).
        d3d9.dll = LoadLibraryW(L"vulkan.dll");

        if (d3d9.dll == NULL)
        {
            // Fallback: system d3d9.dll (native DX9 path).
            WCHAR path[MAX_PATH];
            DWORD pathLen = GetSystemDirectoryW(path, MAX_PATH - wcslen(L"\\d3d9.dll"));
            lstrcpyW(path + pathLen, L"\\d3d9.dll");
            d3d9.dll = LoadLibraryW(path);
        }

        if (d3d9.dll == NULL)
        {
            DWORD error = GetLastError();
            wchar_t errorMsg[512];
            wsprintfW(errorMsg, L"Failed to load both vulkan.dll and d3d9.dll!\nError code: %lu", error);
            MessageBoxW(0, errorMsg, L"GTA Bridge DLL Load Error", MB_ICONERROR);
            ExitProcess(0);
        }

        d3d9.D3DPERF_BeginEvent = GetProcAddress(d3d9.dll, "D3DPERF_BeginEvent");
        d3d9.D3DPERF_EndEvent = GetProcAddress(d3d9.dll, "D3DPERF_EndEvent");
        d3d9.D3DPERF_GetStatus = GetProcAddress(d3d9.dll, "D3DPERF_GetStatus");
        d3d9.D3DPERF_QueryRepeatFrame = GetProcAddress(d3d9.dll, "D3DPERF_QueryRepeatFrame");
        d3d9.D3DPERF_SetMarker = GetProcAddress(d3d9.dll, "D3DPERF_SetMarker");
        d3d9.D3DPERF_SetOptions = GetProcAddress(d3d9.dll, "D3DPERF_SetOptions");
        d3d9.D3DPERF_SetRegion = GetProcAddress(d3d9.dll, "D3DPERF_SetRegion");
        d3d9.DebugSetLevel = GetProcAddress(d3d9.dll, "DebugSetLevel");
        d3d9.DebugSetMute = GetProcAddress(d3d9.dll, "DebugSetMute");
        d3d9.Direct3D9EnableMaximizedWindowedModeShim = GetProcAddress(d3d9.dll, "Direct3D9EnableMaximizedWindowedModeShim");
        d3d9.Direct3DCreate9 = GetProcAddress(d3d9.dll, "Direct3DCreate9");
        d3d9.Direct3DCreate9Ex = GetProcAddress(d3d9.dll, "Direct3DCreate9Ex");
        d3d9.Direct3DCreate9On12 = GetProcAddress(d3d9.dll, "Direct3DCreate9On12");
        d3d9.Direct3DCreate9On12Ex = GetProcAddress(d3d9.dll, "Direct3DCreate9On12Ex");
        d3d9.Direct3DShaderValidatorCreate9 = GetProcAddress(d3d9.dll, "Direct3DShaderValidatorCreate9");
        d3d9.PSGPError = GetProcAddress(d3d9.dll, "PSGPError");
        d3d9.PSGPSampleTexture = GetProcAddress(d3d9.dll, "PSGPSampleTexture");
        break;
    }
    case DLL_PROCESS_DETACH:
    {
        FreeLibrary(d3d9.dll);
        break;
    }
    }
    return TRUE;
}
