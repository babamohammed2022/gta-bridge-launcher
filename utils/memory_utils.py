"""
Memory Utilities - Memory-related helper functions
"""

import struct
from typing import Tuple, Optional


class MemoryUtils:
    """Utilities for memory operations"""
    
    @staticmethod
    def read_int32(data: bytes, offset: int) -> int:
        """Read a 32-bit integer from bytes"""
        return struct.unpack('<i', data[offset:offset+4])[0]
    
    @staticmethod
    def write_int32(value: int) -> bytes:
        """Write a 32-bit integer to bytes"""
        return struct.pack('<i', value)
    
    @staticmethod
    def read_float(data: bytes, offset: int) -> float:
        """Read a 32-bit float from bytes"""
        return struct.unpack('<f', data[offset:offset+4])[0]
    
    @staticmethod
    def write_float(value: float) -> bytes:
        """Write a 32-bit float to bytes"""
        return struct.pack('<f', value)
    
    @staticmethod
    def calculate_morton_code(x: int, y: int) -> int:
        """Calculate Morton (Z-order) code for 2D coordinates"""
        def part1by2(n):
            n = (n | (n << 16)) & 0x0000FFFF
            n = (n | (n << 8)) & 0x00FF00FF
            n = (n | (n << 4)) & 0x0F0F0F0F
            n = (n | (n << 2)) & 0x33333333
            n = (n | (n << 1)) & 0x55555555
            return n
        
        return (part1by2(x) << 1) | part1by2(y)
    
    @staticmethod
    def sector_to_morton(sector_x: int, sector_y: int, sector_size: int = 128) -> int:
        """Convert sector coordinates to Morton code"""
        # GTA SA uses 128x128 sector size
        return MemoryUtils.calculate_morton_code(sector_x, sector_y)
    
    @staticmethod
    def morton_to_sector(morton_code: int) -> Tuple[int, int]:
        """Convert Morton code back to sector coordinates"""
        def deinterleave(n):
            n = (n & 0x55555555) * 2
            n = (n & 0x33333333) * 4
            n = (n & 0x0F0F0F0F) * 16
            n = (n & 0x00FF00FF) * 256
            n = (n & 0x0000FFFF) * 65536
            return n >> 1
        
        x = deinterleave(morton_code >> 1)
        y = deinterleave(morton_code)
        return (x, y)
    
    @staticmethod
    def is_valid_memory_address(addr: int, max_addr: int = 0xFFFFFFFF) -> bool:
        """Check if a memory address is valid"""
        return 0 <= addr <= max_addr