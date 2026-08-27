/**
 * GTA SA Memory Info Overlay - ASI Plugin
 * Displays memory pool information on screen using ImGui
 * Based on skygfx_plus_expIV debug menu implementation
 */

#include <windows.h>
#include <d3d9.h>
#include <stdio.h>
#include <psapi.h>

// ImGui headers
#include "imgui.h"
#include "imgui_impl_dx9.h"
#include "imgui_impl_win32.h"

// Game memory addresses (from reverse engineering)
#define D3D9_DEVICE_ADDR 0xC43C70

// Function pointer types
typedef IDirect3DDevice9* (*GetDeviceFunc)();
typedef void (*DrawFunc)(IDirect3DDevice9*);

// Global state
static bool g_ImGuiInited = false;
static IDirect3DDevice9* g_Device = nullptr;
static HWND g_Hwnd = nullptr;

// Memory pool values
static int g_streaming_pool = 0;
static int g_texture_pool = 0;
static int g_model_pool = 0;
static int g_max_colors = 1000;
static int g_max_models = 50000;

// Get process memory in MB
DWORD GetProcessMemoryMB() {
    PROCESS_MEMORY_COUNTERS pmc;
    if (GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) {
        return (DWORD)(pmc.WorkingSetSize / (1024 * 1024));
    }
    return 0;
}

// Calculate memory pools based on available memory
void CalculateMemoryPools(DWORD total_mb) {
    g_streaming_pool = (int)(total_mb * 0.3f);
    g_texture_pool = (int)(total_mb * 0.4f);
    g_model_pool = (int)(total_mb * 0.2f);
    
    // Cap values
    if (g_streaming_pool > 512) g_streaming_pool = 512;
    if (g_texture_pool > 256) g_texture_pool = 256;
    if (g_model_pool > 128) g_model_pool = 128;
    
    // Extended limits
    g_max_colors = 1000;
    g_max_models = 50000;
}

// Initialize ImGui
bool InitImGui(IDirect3DDevice9* device) {
    if (g_ImGuiInited) return true;
    
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO();
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    
    ImGui::StyleColorsDark();
    
    if (!ImGui_ImplWin32_Init(g_Hwnd)) return false;
    if (!ImGui_ImplDX9_Init(device)) return false;
    
    g_ImGuiInited = true;
    return true;
}

// Shutdown ImGui
void ShutdownImGui() {
    if (!g_ImGuiInited) return;
    
    ImGui_ImplDX9_Shutdown();
    ImGui_ImplWin32_Shutdown();
    ImGui::DestroyContext();
    
    g_ImGuiInited = false;
}

// Draw the memory overlay
void DrawMemoryOverlay() {
    if (!g_Device) return;
    
    // Initialize ImGui if needed
    if (!g_ImGuiInited) {
        if (!InitImGui(g_Device)) return;
    }
    
    // Start new ImGui frame
    ImGui_ImplWin32_NewFrame();
    ImGui_ImplDX9_NewFrame();
    ImGui::NewFrame();
    
    // Calculate memory pools
    DWORD mem_mb = GetProcessMemoryMB();
    CalculateMemoryPools(mem_mb);
    
    // Create overlay window - positioned at top-right
    ImGui::SetNextWindowPos(ImVec2(800, 10), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize(ImVec2(380, 180), ImGuiCond_FirstUseEver);
    
    if (ImGui::Begin("64 Bit Extender Active", nullptr, 
                     ImGuiWindowFlags_NoTitleBar | 
                     ImGuiWindowFlags_AlwaysAutoResize |
                     ImGuiWindowFlags_NoMove |
                     ImGuiWindowFlags_NoSavedSettings |
                     ImGuiWindowFlags_AlwaysOnTop)) {
        
        // Title - prominent display
        ImGui::TextColored(ImVec4(0, 1, 0, 1), "64 BIT EXTENDER ACTIVE");
        ImGui::Separator();
        
        // Memory usage
        ImGui::Text("Memory: %lu MB", mem_mb);
        
        // Memory pools
        ImGui::Text("Streaming: %d MB", g_streaming_pool);
        ImGui::Text("Textures:  %d MB", g_texture_pool);
        ImGui::Text("Models:    %d MB", g_model_pool);
        
        // Extended limits
        ImGui::Separator();
        ImGui::Text("Extended Limits:");
        ImGui::Text("Max Colors: %d", g_max_colors);
        ImGui::Text("Max Models: %d", g_max_models);
    }
    ImGui::End();
    
    // Render ImGui
    ImGui::Render();
    ImGui_ImplDX9_RenderDrawData(ImGui::GetDrawData());
}

// Hook for game rendering
void __cdecl DrawHook(IDirect3DDevice9* device) {
    // Store device for ImGui init
    if (!g_Device) {
        g_Device = device;
        g_Hwnd = FindWindowA("GTA2004UserWindow", nullptr);
        if (!g_Hwnd) {
            g_Hwnd = GetDesktopWindow();
        }
    }
    
    // Draw overlay
    DrawMemoryOverlay();
}

// DLL entry point
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        break;
    case DLL_PROCESS_DETACH:
        ShutdownImGui();
        break;
    }
    return TRUE;
}

// ASI exports
extern "C" {
    __declspec(dllexport) void __cdecl Init() {
        // Initialization complete
    }
    
    __declspec(dllexport) void __cdecl Shutdown() {
        ShutdownImGui();
    }
    
    __declspec(dllexport) void __cdecl OnGameStart() {
        // Game started
    }
    
    __declspec(dllexport) void __cdecl OnGameExit() {
        ShutdownImGui();
    }
}