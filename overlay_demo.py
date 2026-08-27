#!/usr/bin/env python3
"""
GTA Overlay Demo - Shows what the overlay would look like
This demonstrates the memory pool information display
"""

import os
import sys
import time
import psutil


def print_overlay_demo():
    """Print overlay demo"""
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # Get current process memory
    proc = psutil.Process()
    mem_info = proc.memory_info()
    mem_mb = mem_info.rss / (1024 * 1024)
    
    # Calculate pools
    streaming = min(int(mem_mb * 0.3), 512)
    textures = min(int(mem_mb * 0.4), 256)
    models = min(int(mem_mb * 0.2), 128)
    
    # Print overlay text (simulating what would appear on screen)
    print("\033[2J\033[H", end="")  # Clear screen and move to top-left
    
    print("=" * 70)
    print(" GTA SA Memory Pool Monitor - Running with Extended Memory")
    print("=" * 70)
    print()
    print(f"Process ID: {proc.pid}")
    print(f"Memory Usage: {mem_mb:.1f} MB")
    print(f"VRAM: 4096 MB")
    print()
    print("Memory Pools:")
    print(f"  Streaming: {streaming} MB")
    print(f"  Textures:  {textures} MB")
    print(f"  Models:    {models} MB")
    print()
    print("Extended Limits:")
    print(f"  Max Colors: 1000")
    print(f"  Max Models: 50000")
    print()
    print("-" * 70)
    print("Press Ctrl+C to exit")
    print()
    print("Note: This is a console overlay. For in-game overlay,")
    print("compile and use the memory_overlay.asi plugin.")


def main():
    """Main entry point"""
    print("GTA SA Memory Overlay Demo")
    print("=" * 70)
    print()
    print("This demo shows what the overlay would look like.")
    print("The actual overlay would appear on top of the GTA SA game window.")
    print()
    print("Press Enter to start the overlay demo...")
    input()
    
    try:
        while True:
            print_overlay_demo()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == '__main__':
    main()