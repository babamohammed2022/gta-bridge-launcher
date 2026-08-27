#!/usr/bin/env python3
"""
GTA Overlay - Displays memory pool info on top of GTA SA
"""

import os
import sys
import time
import psutil
import subprocess
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


class GTAOverlay:
    """Overlay window that displays memory info on top of GTA SA"""
    
    def __init__(self, game_path: str):
        self.game_path = Path(game_path)
        self.game_exe = self.game_path / 'gta_sa.exe'
        self.process = None
        
        if not GUI_AVAILABLE:
            print("Tkinter not available")
            return
        
        # Create overlay window
        self.root = tk.Tk()
        self.root.title("GTA SA Memory Info")
        self.root.overrideredirect(True)  # Remove window decorations
        self.root.attributes('-topmost', True)  # Stay on top
        self.root.attributes('-transparentcolor', 'white')  # Transparent background
        self.root.configure(bg='white')
        
        # Position at top-left of screen
        self.root.geometry("400x120+10+10")
        
        # Create info labels
        self.info_frame = ttk.Frame(self.root, padding=10)
        self.info_frame.pack(fill=tk.BOTH, expand=True)
        
        self.title_label = ttk.Label(self.info_frame, text="GTA SA Running", 
                                     font=('Segoe UI', 12, 'bold'))
        self.title_label.pack(anchor=tk.W)
        
        self.memory_label = ttk.Label(self.info_frame, text="Memory: --", 
                                      font=('Segoe UI', 10))
        self.memory_label.pack(anchor=tk.W, pady=(5, 0))
        
        self.pools_label = ttk.Label(self.info_frame, text="Pools: --", 
                                     font=('Segoe UI', 10))
        self.pools_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Start update loop
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
    
    def update_loop(self):
        """Continuously update memory info"""
        while True:
            try:
                if self.process and self.process.poll() is None:
                    # Get process memory
                    mem_info = self.process.memory_info()
                    mem_mb = mem_info.rss / (1024 * 1024)
                    
                    # Get process info
                    proc = psutil.Process(self.process.pid)
                    num_threads = proc.num_threads()
                    
                    # Update labels
                    self.root.after(0, lambda: self.memory_label.config(
                        text=f"Memory: {mem_mb:.1f} MB | Threads: {num_threads}"))
                    
                    # Calculate memory pools (approximate)
                    streaming = min(int(mem_mb * 0.3), 512)
                    textures = min(int(mem_mb * 0.4), 256)
                    models = min(int(mem_mb * 0.2), 128)
                    
                    self.root.after(0, lambda: self.pools_label.config(
                        text=f"Pools: Streaming={streaming}MB | Textures={textures}MB | Models={models}MB"))
                else:
                    self.root.after(0, lambda: self.title_label.config(text="GTA SA Not Running"))
            except Exception as e:
                pass
            
            time.sleep(0.5)
    
    def launch_game(self):
        """Launch GTA SA"""
        if not self.game_exe.exists():
            print(f"Game executable not found: {self.game_exe}")
            return False
        
        try:
            self.process = subprocess.Popen(
                [str(self.game_exe)],
                cwd=str(self.game_path),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            print(f"Game launched with PID: {self.process.pid}")
            return True
        except Exception as e:
            print(f"Failed to launch game: {e}")
            return False
    
    def run(self):
        """Run the overlay"""
        if not GUI_AVAILABLE:
            return
        
        # Launch game
        if not self.launch_game():
            return
        
        # Start GUI loop
        self.root.mainloop()


def main():
    """Main entry point"""
    game_path = "E:/games/gtasa_skygfx_plus"
    
    if not os.path.exists(game_path):
        print(f"Game path not found: {game_path}")
        sys.exit(1)
    
    overlay = GTAOverlay(game_path)
    overlay.run()


if __name__ == '__main__':
    main()