"""Configuration Management Module.

This module handles the persistent storage of application settings using a JSON file.
It implements the Singleton pattern to ensure a unified state across the application.
"""

import json
import os
import sys
import threading
from typing import Any, Dict, List, Optional

def get_app_path():
    """Returns the base path for the application."""
    if getattr(sys, 'frozen', False):
        # If the app is bundled by PyInstaller, sys._MEIPASS is the temp folder
        # but we want our config next to the actual EXE.
        return os.path.dirname(sys.executable)
    # If running from source, it's the project root (one level up from src)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- PATH CONSTANTS ---
PROJECT_ROOT = get_app_path()

CONFIG_FILE_PATH = os.path.join(PROJECT_ROOT, "rss_config.json")
DEBUG_FILE = os.path.join(PROJECT_ROOT, "debug_start.txt")
TRACE_FILE = os.path.join(PROJECT_ROOT, "debug_trace.txt")
ERROR_FILE = os.path.join(PROJECT_ROOT, "error.log")

class ConfigManager:
    """Singleton class for managing application configuration.
    
    Attributes:
        _instance: The singleton instance.
        _lock: Thread lock for safe file operations.
        data: The current configuration dictionary.
    """
    _instance: Optional['ConfigManager'] = None
    _lock: threading.Lock = threading.Lock()
    
    CONFIG_FILE: str = CONFIG_FILE_PATH
    DEFAULT_CONFIG: Dict[str, Any] = {
        "manual_mode": False,
        "manual_base": 0,
        "manual_max": 8,
        "manual_profile": "Closest",
        "autostart": False,
        "games_list": [
            "cs2.exe", "dota2.exe", "valorant.exe", "valorant-win64-shipping.exe",
            "r5apex.exe", "cod.exe", "mw2.exe", "pubg.exe", "rainbowsix.exe",
            "gta5.exe", "fortniteclient-win64-shipping.exe", "overwatch.exe"
        ]
    }

    def __new__(cls) -> 'ConfigManager':
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ConfigManager, cls).__new__(cls)
                cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Loads configuration from the disk."""
        self.data = self.DEFAULT_CONFIG.copy()
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    loaded_data = json.load(f)
                    # Merge defaults to ensure all keys exist
                    for key, value in loaded_data.items():
                        self.data[key] = value
            except (json.JSONDecodeError, IOError) as e:
                print(f"[ConfigManager] Load error: {e}")

    def get(self, key: str) -> Any:
        """Retrieves a configuration value.
        
        Args:
            key: The configuration key.
            
        Returns:
            The value associated with the key, or the default value if not found.
        """
        return self.data.get(key, self.DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any) -> None:
        """Sets a configuration value and saves to disk.
        
        Args:
            key: The configuration key.
            value: The value to set.
        """
        self.data[key] = value
        self.save()

    def add_game(self, game_exe: str) -> bool:
        """Adds a game to the monitoring list.

        Args:
            game_exe: The executable name of the game (e.g., 'game.exe').

        Returns:
            True if added, False if already exists.
        """
        games = self.data.get("games_list", [])
        if game_exe not in games:
            games.append(game_exe)
            self.set("games_list", games)
            return True
        return False

    def remove_game(self, game_exe: str) -> bool:
        """Removes a game from the monitoring list.

        Args:
            game_exe: The executable name to remove.

        Returns:
            True if removed, False if not found.
        """
        games = self.data.get("games_list", [])
        if game_exe in games:
            games.remove(game_exe)
            self.set("games_list", games)
            return True
        return False

    def save(self) -> None:
        """Persists the current configuration to disk."""
        try:
            with self._lock:
                with open(self.CONFIG_FILE, 'w') as f:
                    json.dump(self.data, f, indent=4)
        except IOError as e:
            print(f"[ConfigManager] Save error: {e}")