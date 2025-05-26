"""
Вспомогательные функции
"""

import os
import humanize
from typing import List, Tuple
from datetime import datetime


def get_file_info(path: str) -> Tuple[str, str, str, str]:
    """Получение информации о файле"""
    try:
        stat = os.stat(path)
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        
        if is_dir:
            try:
                size = f"{len(os.listdir(path))} элем."
            except:
                size = "Нет доступа"
        else:
            size = humanize.naturalsize(stat.st_size)
        
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        file_type = "Папка" if is_dir else "Файл"
        
        return name, size, file_type, modified
    except:
        return os.path.basename(path), "Ошибка", "Неизвестно", ""


def list_directory(path: str) -> List[Tuple[str, str, str, str]]:
    """Получение списка файлов в директории"""
    items = []
    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            items.append(get_file_info(item_path))
    except Exception as e:
        print(f"Ошибка чтения директории {path}: {e}")
    return items


def filter_hidden_files(items: List[Tuple[str, str, str, str]], 
                       show_hidden: bool = False) -> List[Tuple[str, str, str, str]]:
    """Фильтрация скрытых файлов"""
    if not show_hidden:
        return [item for item in items if not item[0].startswith('.')]
    return items


def sort_items(items: List[Tuple[str, str, str, str]], 
              folders_first: bool = True) -> List[Tuple[str, str, str, str]]:
    """Сортировка элементов"""
    if folders_first:
        folders = [item for item in items if item[2] == "Папка"]
        files = [item for item in items if item[2] == "Файл"]
        
        folders.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())
        
        return folders + files
    else:
        return sorted(items, key=lambda x: x[0].lower()) 