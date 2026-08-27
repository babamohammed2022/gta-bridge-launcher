#!/usr/bin/env python3
"""
GTA Memory Monitor - Console-based memory pool monitor
Displays memory info while GTA SA is running
"""

import os
import sys
import time
import psutil
import subprocess
from pathlib import Path


def get_gta_process():
    """Find GTA SA process"""
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and 'gta_sa' in proc.info['name'].lower():
            return proc
    return None


def calculate_memory_pools(total_mb):
    """Calculate memory pools based on total memory (delegates to pool_planner)"""
    from managers.pool_planner import recommended_pools
    from utils.system_utils import SystemUtils
    pools = recommended_pools(vram_mb=SystemUtils.get_top2007_auto_vram(), ram_mb=total_mb)
    return {
        'streaming': pools['streaming'],
        'textures': pools['textures'],
        'models': pools['models'],
        'max_colors': 1000,
        'max_models': 50000
    }


def print_header():
    """Print header"""
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 70)
    print(" GTA SA Memory Pool Monitor - Running with Extended Memory")
    print("=" * 70)
    print()


def print_status(proc):
    """Print current status"""
    if not proc:
        print("Game not running...")
        return
    
    try:
        mem_info = proc.memory_info()
        mem_mb = mem_info.rss / (1024 * 1024)
        vram_mb = 4096  # Assume 4GB VRAM
        
        pools = calculate_memory_pools(mem_mb)
        
        print(f"Process ID: {proc.pid}")
        print(f"Memory Usage: {mem_mb:.1f} MB")
        print(f"VRAM: {vram_mb} MB")
        print()
        print("Memory Pools:")
        print(f"  Streaming: {pools['streaming']} MB")
        print(f"  Textures:  {pools['textures']} MB")
        print(f"  Models:    {pools['models']} MB")
        print()
        print("Extended Limits:")
        print(f"  Max Colors: {pools['max_colors']}")
        print(f"  Max Models: {pools['max_models']}")
        print()
        print("-" * 70)
        print("Press Ctrl+C to exit")
        
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        print("Game process terminated")


def main():
    """Main entry point"""
    game_path = "E:/games/gtasa_skygfx_plus"
    game_exe = Path(game_path) / "gta_sa.exe"
    
    if not game_exe.exists():
        print(f"Game executable not found: {game_exe}")
        sys.exit(1)
    
    print_header()
    
    # Launch game
    print("Launching GTA SA...")
    proc = subprocess.Popen([str(game_exe)], cwd=game_path)
    print(f"Game launched with PID: {proc.pid}")
    print("Waiting for game to initialize...")
    time.sleep(3)  # Wait for game to start
    print()
    
    # Convert to psutil process
    try:
        psutil_proc = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        print("Process not found")
        sys.exit(1)
    
    try:
        while True:
            # Check if process is still running
            if proc.poll() is not None:
                print("Game exited")
                break
            
            print_header()
            print_status(psutil_proc)
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nExiting...")
        proc.terminate()


if __name__ == '__main__':
    main()