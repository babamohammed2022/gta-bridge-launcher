"""
Config Manager - Handles user preferences and game configurations
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """Manages configuration files for the launcher"""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.settings = self._load_settings()
        self.games_config = self._load_games_config()
    
    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from JSON file"""
        settings_file = self.config_path / 'settings.json'
        if settings_file.exists():
            with open(settings_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _load_games_config(self) -> Dict[str, Any]:
        """Load games configuration from JSON file"""
        games_file = self.config_path / 'games.json'
        if games_file.exists():
            with open(games_file, 'r') as f:
                return json.load(f)
        return {'games': {}}
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        keys = key.split('.')
        value = self.settings
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set_setting(self, key: str, value: Any) -> None:
        """Set a setting value"""
        keys = key.split('.')
        settings = self.settings
        for k in keys[:-1]:
            if k not in settings:
                settings[k] = {}
            settings = settings[k]
        settings[keys[-1]] = value
        self._save_settings()
    
    def _save_settings(self) -> None:
        """Save settings to file"""
        with open(self.config_path / 'settings.json', 'w') as f:
            json.dump(self.settings, f, indent=4)
    
    def get_game_config(self, game: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific game"""
        return self.games_config.get('games', {}).get(game)
    
    def get_game_executable(self, game: str) -> Optional[str]:
        """Get executable name for a game"""
        config = self.get_game_config(game)
        return config.get('executable') if config else None
    
    def get_game_limits(self, game: str) -> Dict[str, int]:
        """Get default limits for a game"""
        config = self.get_game_config(game)
        return config.get('default_limits', {}) if config else {}
    
    def get_limit_extenders(self, game: str) -> Dict[str, str]:
        """Get limit extender URLs for a game"""
        config = self.get_game_config(game)
        return config.get('limit_extenders', {}) if config else {}

    def set_game_path(self, game: str, path: str) -> None:
        """Persist install_path for a game into games.json"""
        g = self.games_config.setdefault('games', {}).setdefault(game, {'name': game})
        g['install_path'] = str(path)
        with open(self.config_path / 'games.json', 'w', encoding='utf-8') as f:
            json.dump(self.games_config, f, indent=4)

    def get_game_path(self, game: str) -> Optional[str]:
        """Retrieve persisted install_path for a game"""
        c = self.get_game_config(game)
        return c.get('install_path') if c else None