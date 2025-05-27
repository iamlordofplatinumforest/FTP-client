"""
Вспомогательные функции для работы с файлами и директориями
"""

import os
from datetime import datetime
from typing import List, Dict, Any
import humanize


def list_directory(path: str) -> List[Dict[str, Any]]:
    """
    Получение списка файлов и папок в директории
    
    Returns:
        List[Dict]: Список файлов и папок с их атрибутами
    """
    items = []
    try:
        for name in os.listdir(path):
            full_path = os.path.join(path, name)
            stat = os.stat(full_path)
            
            item = {
                'name': name,
                'path': full_path,
                'size': stat.st_size,
                'type': 'folder' if os.path.isdir(full_path) else 'file',
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'permissions': stat.st_mode
            }
            
            # Добавляем человекочитаемый размер
            if item['type'] == 'file':
                item['size_human'] = humanize.naturalsize(item['size'])
            else:
                item['size_human'] = ''
                
            items.append(item)
    except Exception as e:
        print(f"Ошибка чтения директории {path}: {e}")
        
    return items


def filter_hidden_files(items: List[Dict[str, Any]], show_hidden: bool = False) -> List[Dict[str, Any]]:
    """
    Фильтрация скрытых файлов и папок
    
    Args:
        items: Список файлов и папок
        show_hidden: Показывать ли скрытые файлы
        
    Returns:
        List[Dict]: Отфильтрованный список
    """
    if show_hidden:
        return items
        
    return [item for item in items if not item['name'].startswith('.')]


def sort_items(items: List[Dict[str, Any]], folders_first: bool = True) -> List[Dict[str, Any]]:
    """
    Сортировка списка файлов и папок
    
    Args:
        items: Список файлов и папок
        folders_first: Показывать ли папки первыми
        
    Returns:
        List[Dict]: Отсортированный список
    """
    if folders_first:
        # Сначала сортируем папки, потом файлы
        folders = sorted(
            [item for item in items if item['type'] == "Папка"],
            key=lambda x: x['name'].lower()
        )
        files = sorted(
            [item for item in items if item['type'] == "Файл"],
            key=lambda x: x['name'].lower()
        )
        return folders + files
    else:
        # Сортируем все элементы по имени
        return sorted(items, key=lambda x: x['name'].lower())


def format_size(size: int) -> str:
    """
    Форматирование размера файла
    
    Args:
        size: Размер в байтах
        
    Returns:
        str: Отформатированный размер
    """
    return humanize.naturalsize(size)


def format_date(date: datetime, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Форматирование даты
    
    Args:
        date: Дата
        format_str: Строка форматирования
        
    Returns:
        str: Отформатированная дата
    """
    return date.strftime(format_str)


def get_file_type(filename: str) -> str:
    """
    Определение типа файла по расширению
    
    Args:
        filename: Имя файла
        
    Returns:
        str: Тип файла
    """
    ext = os.path.splitext(filename)[1].lower()
    
    types = {
        '.txt': 'Текстовый файл',
        '.doc': 'Microsoft Word',
        '.docx': 'Microsoft Word',
        '.pdf': 'PDF документ',
        '.jpg': 'Изображение JPEG',
        '.jpeg': 'Изображение JPEG',
        '.png': 'Изображение PNG',
        '.gif': 'Изображение GIF',
        '.mp3': 'Аудио MP3',
        '.wav': 'Аудио WAV',
        '.mp4': 'Видео MP4',
        '.avi': 'Видео AVI',
        '.zip': 'Архив ZIP',
        '.rar': 'Архив RAR',
        '.py': 'Python скрипт',
        '.html': 'HTML файл',
        '.css': 'CSS файл',
        '.js': 'JavaScript файл'
    }
    
    return types.get(ext, 'Файл') 