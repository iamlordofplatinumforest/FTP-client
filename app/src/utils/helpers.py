import os
from datetime import datetime
from typing import List, Dict, Any
import humanize


def list_directory(path: str) -> List[Dict[str, Any]]:
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

            if item['type'] == 'file':
                item['size_human'] = humanize.naturalsize(item['size'])
            else:
                item['size_human'] = ''
                
            items.append(item)
    except Exception as e:
        print(f"Ошибка чтения директории {path}: {e}")
        
    return items


def filter_hidden_files(items: List[Dict[str, Any]], show_hidden: bool = False) -> List[Dict[str, Any]]:
    if show_hidden:
        return items
        
    return [item for item in items if not item['name'].startswith('.')]


def sort_items(items: List[Dict[str, Any]], folders_first: bool = True) -> List[Dict[str, Any]]:
    if folders_first:
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
        return sorted(items, key=lambda x: x['name'].lower())


def format_size(size: int) -> str:
    return humanize.naturalsize(size)


def format_date(date: datetime, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    return date.strftime(format_str)


def get_file_type(filename: str) -> str:
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