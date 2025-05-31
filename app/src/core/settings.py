import os
import json
from typing import Dict, Any


class Settings:
    def __init__(self):
        self.settings_file = os.path.join(
            os.path.expanduser("~"), ".ftp_client_settings.json")
        self.default_settings = {
            'default_local_dir': os.path.expanduser("~"),
            'show_hidden_files': False,
            'sort_folders_first': True,
            'confirm_delete': True,
            'confirm_overwrite': True,
            'buffer_size': 8192,
            'encoding': 'utf-8',
            'date_format': '%Y-%m-%d %H:%M:%S',
            'theme': 'default',
            'auto_reconnect': True,
            'reconnect_attempts': 3,
            'cache_ttl': 30
        }
        self.current_settings = self.load_settings()

    def load_settings(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    saved_settings = json.load(f)
                    settings = self.default_settings.copy()
                    settings.update(saved_settings)
                    return settings
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")
        return self.default_settings.copy()

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.current_settings, f, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.current_settings.get(key, default)

    def set(self, key: str, value: Any):
        self.current_settings[key] = value

    def update(self, settings: Dict[str, Any]):
        self.current_settings.update(settings)

    def reset(self):
        self.current_settings = self.default_settings.copy()
        self.save_settings() 