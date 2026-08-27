"""
Game Manager - Handles game operations and installations
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class GameManager:
    """Manages game installations and operations"""
    
    def __init__(self, game_path: str, db_path: str):
        self.game_path = Path(game_path)
        self.db_path = db_path
        self.installations_file = self.game_path / 'game_installations.json'
        self.installations = self._load_installations()
    
    def _load_installations(self) -> Dict[str, Any]:
        """Load game installations from file"""
        if self.installations_file.exists():
            with open(self.installations_file, 'r') as f:
                return json.load(f)
        return {'games': {}}
    
    def _save_installations(self) -> None:
        """Save game installations to file"""
        with open(self.installations_file, 'w') as f:
            json.dump(self.installations, f, indent=4)
    
    def add_game(self, game: str, path: str, version: str = None) -> bool:
        """Add a game installation"""
        game_path = Path(path)
        if not game_path.exists():
            return False
        
        self.installations['games'][game] = {
            'path': str(game_path),
            'version': version or 'unknown',
            'is_active': True
        }
        self._save_installations()
        return True
    
    def get_game_path(self, game: str) -> Optional[Path]:
        """Get the path to a game installation"""
        game_info = self.installations.get('games', {}).get(game)
        if game_info:
            return Path(game_info['path'])
        return None
    
    def is_game_installed(self, game: str) -> bool:
        """Check if a game is installed"""
        return game in self.installations.get('games', {})
    
    def get_executable_path(self, game: str) -> Optional[Path]:
        """Get the path to a game's executable"""
        game_path = self.get_game_path(game)
        if game_path:
            # Try common executable names
            for exe in ['gta_sa.exe', 'gta_vc.exe', 'gta3.exe']:
                exe_path = game_path / exe
                if exe_path.exists():
                    return exe_path
        return None
    
    def list_games(self) -> List[str]:
        """List all installed games"""
        return list(self.installations.get('games', {}).keys())
    
    def get_active_games(self) -> List[str]:
        """List all active games"""
        active = []
        for game, info in self.installations.get('games', {}).items():
            if info.get('is_active', True):
                active.append(game)
        return active