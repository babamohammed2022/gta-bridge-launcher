/**
 * GTA Bridge Launcher - Memory Patcher Implementation
 */

#include "memory_patcher.h"
#include <psapi.h>
#include <iostream>
#include <cstring>

namespace GTA {

MemoryPatcher::MemoryPatcher() 
    : process_handle(nullptr), process_id(0), is_attached(false) {}

MemoryPatcher::~MemoryPatcher() {
    Disconnect();
}

bool MemoryPatcher::AttachToProcess(const std::string& process_name) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return false;
    }
    
    PROCESSENTRY32 entry;
    entry.dwSize = sizeof(PROCESSENTRY32);
    
    if (Process32First(snapshot, &entry)) {
        do {
            if (_stricmp(entry.szExeFile, process_name.c_str()) == 0) {
                process_id = entry.th32ProcessID;
                process_handle = OpenProcess(PROCESS_VM_OPERATION | 
                                           PROCESS_VM_WRITE | 
                                           PROCESS_VM_READ, 
                                           FALSE, process_id);
                if (process_handle) {
                    is_attached = true;
                    CloseHandle(snapshot);
                    return true;
                }
            }
        } while (Process32Next(snapshot, &entry));
    }
    
    CloseHandle(snapshot);
    return false;
}

bool MemoryPatcher::ReadMemory(uintptr_t address, void* buffer, size_t size) {
    if (!is_attached || !process_handle) return false;
    return ReadProcessMemory(process_handle, (LPCVOID)address, buffer, size, nullptr);
}

bool MemoryPatcher::WriteMemory(uintptr_t address, const void* buffer, size_t size) {
    if (!is_attached || !process_handle) return false;
    return WriteProcessMemory(process_handle, (LPVOID)address, buffer, size, nullptr);
}

bool MemoryPatcher::ProtectMemory(uintptr_t address, size_t size, DWORD protection) {
    if (!is_attached || !process_handle) return false;
    DWORD old_protection;
    return VirtualProtectEx(process_handle, (LPVOID)address, size, protection, &old_protection);
}

bool MemoryPatcher::Connect(const std::string& process_name) {
    if (is_attached) {
        Disconnect();
    }
    return AttachToProcess(process_name);
}

void MemoryPatcher::Disconnect() {
    if (process_handle) {
        CloseHandle(process_handle);
        process_handle = nullptr;
    }
    is_attached = false;
    process_id = 0;
}

PatchResult MemoryPatcher::PatchMaxColors(int new_limit) {
    PatchResult result{false, "", 0};
    
    // Read current value
    int current_value = Limits::DEFAULT_MAX_COLORS;
    if (!ReadMemory(Addresses::MAX_COLORS_ADDR, &current_value, sizeof(int))) {
        result.message = "Failed to read current color limit";
        result.error_code = GetLastError();
        return result;
    }
    
    // Make memory writable
    if (!ProtectMemory(Addresses::MAX_COLORS_ADDR, sizeof(int), PAGE_EXECUTE_READWRITE)) {
        result.message = "Failed to set memory protection";
        result.error_code = GetLastError();
        return result;
    }
    
    // Write new value
    if (!WriteMemory(Addresses::MAX_COLORS_ADDR, &new_limit, sizeof(int))) {
        result.message = "Failed to write new color limit";
        result.error_code = GetLastError();
        return result;
    }
    
    result.success = true;
    result.message = "Successfully patched max colors to " + std::to_string(new_limit);
    return result;
}

PatchResult MemoryPatcher::PatchStreamingMemory(int mb_limit) {
    PatchResult result{false, "", 0};
    
    // Convert MB to bytes (assuming 1024*1024 per MB)
    int bytes_limit = mb_limit * 1024 * 1024;
    
    // Make memory writable
    if (!ProtectMemory(Addresses::STREAMING_MEMORY_ADDR, sizeof(int), PAGE_EXECUTE_READWRITE)) {
        result.message = "Failed to set memory protection";
        result.error_code = GetLastError();
        return result;
    }
    
    // Write new value
    if (!WriteMemory(Addresses::STREAMING_MEMORY_ADDR, &bytes_limit, sizeof(int))) {
        result.message = "Failed to write streaming memory limit";
        result.error_code = GetLastError();
        return result;
    }
    
    result.success = true;
    result.message = "Successfully patched streaming memory to " + std::to_string(mb_limit) + "MB";
    return result;
}

PatchResult MemoryPatcher::PatchMaxModels(int new_limit) {
    PatchResult result{false, "", 0};
    
    // Make memory writable
    if (!ProtectMemory(Addresses::SECTOR_ARRAY_ADDR, sizeof(int), PAGE_EXECUTE_READWRITE)) {
        result.message = "Failed to set memory protection";
        result.error_code = GetLastError();
        return result;
    }
    
    // Write new value
    if (!WriteMemory(Addresses::SECTOR_ARRAY_ADDR, &new_limit, sizeof(int))) {
        result.message = "Failed to write max models limit";
        result.error_code = GetLastError();
        return result;
    }
    
    result.success = true;
    result.message = "Successfully patched max models to " + std::to_string(new_limit);
    return result;
}

// Shared Memory Bridge Implementation
SharedMemoryBridge::SharedMemoryBridge(const std::string& name)
    : shared_memory(nullptr), mapped_memory(nullptr), name(name) {}

SharedMemoryBridge::~SharedMemoryBridge() {
    Close();
}

bool SharedMemoryBridge::Create() {
    shared_memory = CreateFileMappingA(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0,
        4096,
        name.c_str()
    );
    
    if (!shared_memory) {
        return false;
    }
    
    mapped_memory = MapViewOfFile(shared_memory, FILE_MAP_ALL_ACCESS, 0, 0, 4096);
    return mapped_memory != nullptr;
}

bool SharedMemoryBridge::Open() {
    shared_memory = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name.c_str());
    if (!shared_memory) {
        return false;
    }
    
    mapped_memory = MapViewOfFile(shared_memory, FILE_MAP_ALL_ACCESS, 0, 0, 4096);
    return mapped_memory != nullptr;
}

void SharedMemoryBridge::Close() {
    if (mapped_memory) {
        UnmapViewOfFile(mapped_memory);
        mapped_memory = nullptr;
    }
    if (shared_memory) {
        CloseHandle(shared_memory);
        shared_memory = nullptr;
    }
}

bool SharedMemoryBridge::WriteData(const void* data, size_t size) {
    if (!mapped_memory || size > 4096 - sizeof(SharedMemoryHeader)) {
        return false;
    }
    
    auto* header = static_cast<SharedMemoryHeader*>(mapped_memory);
    header->magic = 0x47415441; // 'GTA'
    header->version = 1;
    header->data_size = static_cast<uint32_t>(size);
    header->timestamp = GetTickCount64();
    
    const char* src = static_cast<const char*>(data);
    char* dst = static_cast<char*>(mapped_memory) + sizeof(SharedMemoryHeader);
    memcpy(dst, src, size);
    
    return true;
}

bool SharedMemoryBridge::ReadData(void* buffer, size_t size) {
    if (!mapped_memory) {
        return false;
    }
    
    auto* header = static_cast<SharedMemoryHeader*>(mapped_memory);
    if (header->magic != 0x47415441) {
        return false;
    }
    
    const char* src = static_cast<const char*>(mapped_memory) + sizeof(SharedMemoryHeader);
    char* dst = static_cast<char*>(buffer);
    memcpy(dst, src, std::min(size, header->data_size));
    
    return true;
}

} // namespace GTA