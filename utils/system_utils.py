"""
System Utilities - System information and hardware detection
"""

import os
import platform
from typing import Dict, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class SystemUtils:
    """System utilities for hardware detection and resource management"""
    
    @staticmethod
    def get_system_memory() -> int:
        """Get total system RAM in MB"""
        if PSUTIL_AVAILABLE:
            return psutil.virtual_memory().total // (1024 * 1024)
        
        # Fallback for Windows
        if platform.system() == 'Windows':
            try:
                import ctypes
                from ctypes import wintypes
                
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ('dwLength', wintypes.DWORD),
                        ('dwMemoryLoad', wintypes.DWORD),
                        ('ullTotalPhys', ctypes.c_ulonglong),
                        ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong),
                        ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong),
                        ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                    ]
                
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                return stat.ullTotalPhys // (1024 * 1024)
            except:
                pass
        
        # Fallback for Unix-like systems
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        return int(line.split()[1])
        except:
            pass
        
        return 4096  # Default 4GB
    
    @staticmethod
    def get_gpu_memory() -> int:
        """Get total GPU memory in MB (placeholder)"""
        return SystemUtils.get_top2007_auto_vram()

    @staticmethod
    def get_top2007_auto_vram() -> int:
        """Top of the 2007 auto-scaling: 1/4 of system RAM for VRAM, 512 MB min, 8192 MB ridiculous cap (8 GB when 64 GB detected)."""
        total = SystemUtils.get_system_memory()
        vram = total // 4
        # windows check: 32-bit OS cannot address >2048 reliably for the game; extender (64-bit) can go to 8192
        is_64bit_os = platform.machine().endswith('64') or 'AMD64' in platform.machine() or 'ARM64' in platform.machine() or platform.architecture()[0] == '64bit'
        cap = 8192 if (is_64bit_os and SystemUtils.is_windows()) else 4096
        # If Windows allows large address (64-bit), permit up to cap; otherwise conservative
        if vram < 512:
            vram = 512
        if vram > cap:
            vram = cap
        # clamp ridiculous 64GB case to exactly 8192 as requested (64GB//4=16384 -> 8192)
        return vram

    @staticmethod
    def get_top2007_auto_config() -> Dict[str, int]:
        """Return auto-scaled Top 2007 values for current machine. VRAM + MemoryAvailable scale 1/4 RAM, pools stay at bypass-max."""
        vram = SystemUtils.get_top2007_auto_vram()
        # MemoryAvailable in GTA is streaming memory guarantee — keep in sync with VRAM for Top 2007
        return {'VRAM': vram, 'MemoryAvailable': str(vram), 'streaming_vram_mb': vram}
    
    @staticmethod
    def get_cpu_count() -> int:
        """Get number of CPU cores"""
        return os.cpu_count() or 4
    
    @staticmethod
    def get_platform_info() -> Dict[str, str]:
        """Get platform information"""
        return {
            'system': platform.system(),
            'node': platform.node(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor()
        }
    
    @staticmethod
    def is_windows() -> bool:
        """Check if running on Windows"""
        return platform.system() == 'Windows'
    
    @staticmethod
    def is_linux() -> bool:
        """Check if running on Linux"""
        return platform.system() == 'Linux'
    
    @staticmethod
    def is_darwin() -> bool:
        """Check if running on macOS"""
        return platform.system() == 'Darwin'
    
    @staticmethod
    def calculate_dynamic_limits(vram_mb: int, ram_mb: int) -> Dict[str, int]:
        """Calculate optimal limits based on system resources (delegates to pool_planner)"""
        from managers.pool_planner import recommended_pools
        pools = recommended_pools(vram_mb, ram_mb)
        return {
            'streaming_memory_mb': pools['streaming'],
            'texture_memory_mb': pools['textures'],
            'model_memory_mb': pools['models'],
            'max_colors': 1000,
            'max_models': 50000,
        }
    
    @staticmethod
    def get_optimal_vram_percent() -> float:
        """Get optimal VRAM usage percentage based on system"""
        ram_mb = SystemUtils.get_system_memory()
        if ram_mb >= 16384:
            return 0.35  # Use more VRAM on high-end systems
        elif ram_mb >= 8192:
            return 0.30
        else:
            return 0.25  # Conservative on low-end systems