"""
Модуль для шифрования и дешифрования данных
"""

from cryptography.fernet import Fernet
import base64
import os
from typing import Optional


class Crypto:
    def __init__(self):
        self.key_file = os.path.join(
            os.path.expanduser("~"), ".ftp_client_key")
        self.key = self._load_or_generate_key()
        self.fernet = Fernet(self.key)

    def _load_or_generate_key(self) -> bytes:
        """Загрузка или генерация ключа шифрования"""
        try:
            if os.path.exists(self.key_file):
                with open(self.key_file, 'rb') as f:
                    return f.read()
        except Exception:
            pass

        # Генерируем новый ключ
        key = Fernet.generate_key()
        try:
            with open(self.key_file, 'wb') as f:
                f.write(key)
        except Exception as e:
            print(f"Ошибка сохранения ключа: {e}")
        return key

    def encrypt(self, data: str) -> str:
        """Шифрование строки"""
        if not data:
            return ""
        try:
            return self.fernet.encrypt(data.encode()).decode()
        except Exception as e:
            print(f"Ошибка шифрования: {e}")
            return ""

    def decrypt(self, encrypted_data: str) -> str:
        """Дешифрование строки"""
        if not encrypted_data:
            return ""
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            print(f"Ошибка дешифрования: {e}")
            return "" 