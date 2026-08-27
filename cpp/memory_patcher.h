/**
 * GTA Bridge Launcher - Memory Patcher Helper
 * C++ component for memory patching and process injection
 * 
 * This file provides the core memory patching functionality
 * for extending GTA game limits.
 */

#ifndef MEMORY_PATCHER_H
#define MEMORY_PATCHER_H

#include <windows.h>
#include <tlhelp32.h>
#include <string>
#include <vector>
#include <cstdint>

namespace GTA {

// Memory addresses for GTA San Andreas (reverse engineered)
namespace Addresses {
    constexpr uintptr_t SECTOR_ARRAY_ADDR = 0xBC40E0;
    constexpr uintptr_t CAMERA_ADDR = 0xB6F028;
    constexpr uintptr_t WORLD_PTR = 0xB794D0;
    constexpr uintptr_t STREAMING_MEMORY_ADDR = 0x8A5A80;
    constexpr uintptr_t COLOR_TABLE_ADDR = 0x8F1A80;
    constexpr uintptr_t MAX_COLORS_ADDR = 0x8F1A84;
}

// Default limits
namespace Limits {
    constexpr int DEFAULT_MAX_COLORS = 128;
    constexpr int DEFAULT_MAX_MODELS = 20000;
    constexpr int DEFAULT_STREAMING_MB = 512;
}

struct PatchResult {
    bool success;
    std::string message;
    DWORD error_code;
};

class MemoryPatcher {
private:
    HANDLE process_handle;
    DWORD process_id;
    bool is_attached;
    
    bool AttachToProcess(const std::string& process_name);
    bool ReadMemory(uintptr_t address, void* buffer, size_t size);
    bool WriteMemory(uintptr_t address, const void* buffer, size_t size);
    bool ProtectMemory(uintptr_t address, size_t size, DWORD protection);
    
public:
    MemoryPatcher();
    ~MemoryPatcher();
    
    bool Connect(const std::string& process_name);
    void Disconnect();
    
    PatchResult PatchMaxColors(int new_limit);
    PatchResult PatchStreamingMemory(int mb_limit);
    PatchResult PatchMaxModels(int new_limit);
    
    bool IsConnected() const { return is_attached; }
    DWORD GetProcessId() const { return process_id; }
};

// Shared memory structure for communication with Python
struct SharedMemoryHeader {
    uint32_t magic;
    uint32_t version;
    uint32_t command;
    uint32_t data_size;
    uint64_t timestamp;
};

enum Command {
    CMD_PATCH_COLORS = 1,
    CMD_PATCH_MEMORY = 2,
    CMD_GET_STATUS = 3,
    CMD_SHUTDOWN = 4
};

class SharedMemoryBridge {
private:
    HANDLE shared_memory;
    void* mapped_memory;
    std::string name;
    
public:
    SharedMemoryBridge(const std::string& name);
    ~SharedMemoryBridge();
    
    bool Create();
    bool Open();
    void Close();
    
    bool WriteData(const void* data, size_t size);
    bool ReadData(void* buffer, size_t size);
};

} // namespace GTA

#endif // MEMORY_PATCHER_H