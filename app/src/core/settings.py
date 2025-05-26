"""
Модуль для работы с настройками приложения
"""

import os
import json
from typing import Dict, Any


class Settings:
    def __init__(self):
        self.settings_file = os.path.join(os.path.expanduser("~"), ".ftp_client_settings.json")
        self.default_settings = {
            'default_local_dir': os.path.expanduser("~/Downloads"),
            'buffer_size': 8192,
            'auto_reconnect': True,
            'reconnect_attempts': 3,
            'cache_ttl': 30,
            'show_hidden_files': False,
            'confirm_delete': True,
            'confirm_overwrite': True,
            'dark_mode': False,
            'sort_folders_first': True,
            'date_format': "%Y-%m-%d %H:%M"
        }
        self.current_settings = self.default_settings.copy()
        self.load_settings()

    def load_settings(self) -> None:
        """Загрузка настроек из файла"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    saved_settings = json.load(f)
                    self.current_settings.update(saved_settings)
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")

    def save_settings(self) -> bool:
        """Сохранение настроек в файл"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.current_settings, f)
            return True
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Получение значения настройки"""
        return self.current_settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Установка значения настройки"""
        self.current_settings[key] = value

    def update(self, settings: Dict[str, Any]) -> None:
        """Обновление нескольких настроек"""
        self.current_settings.update(settings)

    def reset(self) -> None:
        """Сброс настроек на значения по умолчанию"""
        self.current_settings = self.default_settings.copy()
        self.save_settings() 