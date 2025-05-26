"""
Утилиты для шифрования данных
"""

import base64
from typing import Optional


class Crypto:
    def __init__(self, key: str = 'my_secret_key'):
        self._key = key

    def encrypt(self, text: str) -> str:
        """Шифрование текста"""
        if not text:
            return ""
        try:
            # Простое XOR шифрование
            encrypted = ''.join(chr(ord(c) ^ ord(k)) 
                              for c, k in zip(text, self._key * (len(text) // len(self._key) + 1)))
            # Конвертируем в base64 для безопасного хранения
            return base64.b64encode(encrypted.encode()).decode()
        except:
            return ""

    def decrypt(self, encrypted: str) -> str:
        """Расшифровка текста"""
        if not encrypted:
            return ""
        try:
            # Декодируем из base64
            decoded = base64.b64decode(encrypted.encode()).decode()
            # Применяем XOR для расшифровки
            return ''.join(chr(ord(c) ^ ord(k)) 
                         for c, k in zip(decoded, self._key * (len(decoded) // len(self._key) + 1)))
        except:
            return "" 