"""
Главный файл приложения FTP клиента
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from ftplib import FTP, FTP_TLS, error_perm
import os
import socket
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from datetime import datetime
import time
import humanize
import json
import re
from typing import Dict, List, Tuple
import base64

from src.core.ftp_client import FTPClient
from src.core.settings import Settings
from src.gui.widgets import FileListView, ConnectionPanel, SearchPanel, PathPanel, StatusBar
from src.gui.dialogs import QuickConnectDialog, HistoryDialog, BookmarksDialog, SettingsDialog, AboutDialog
from src.utils.crypto import Crypto
from src.utils.helpers import filter_hidden_files, sort_items
from src.gui.styles import setup_styles


class Application(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("FTP Client")
        self.geometry("1400x750")

        # Инициализация компонентов
        self.settings = Settings()
        self.ftp_client = FTPClient()
        self.crypto = Crypto()
        
        # Файлы для хранения данных
        self.connection_history_file = os.path.join(
            os.path.expanduser("~"), ".ftp_client_history.json")
        self.bookmarks_file = os.path.join(
            os.path.expanduser("~"), ".ftp_client_bookmarks.json")
        
        # Загрузка данных
        self.connection_history = self._load_connection_history()
        self.bookmarks = self._load_bookmarks()

        # Настройка стилей
        setup_styles()

        # Создание интерфейса
        self._create_menu()
        self._create_main_interface()
        self._setup_bindings()

        # Инициализация очереди обновлений
        self.update_queue = Queue()
        self.is_updating = False
        self.start_update_handler()

    def _create_menu(self):
        """Создание главного меню"""
        menubar = tk.Menu(self)
        
        # Меню подключения
        connection_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Подключение", menu=connection_menu)
        connection_menu.add_command(label="Быстрое подключение", 
                                  command=self._show_quick_connect)
        connection_menu.add_command(label="История подключений", 
                                  command=self._show_connection_history)
        connection_menu.add_command(label="Закладки", 
                                  command=self._show_bookmarks)
        connection_menu.add_command(label="Добавить в закладки", 
                                  command=self._add_bookmark)
        connection_menu.add_separator()
        connection_menu.add_command(label="Отключиться", 
                                  command=self._disconnect,
                                  state="disabled")
        self.connection_menu = connection_menu

        # Меню операций
        operations_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Операции", menu=operations_menu)
        operations_menu.add_command(label="Создать папку", 
                                  command=self._create_folder)
        operations_menu.add_command(label="Загрузить файлы", 
                                  command=self._upload_files)
        operations_menu.add_command(label="Скачать файлы", 
                                  command=self._download_files)
        operations_menu.add_separator()
        operations_menu.add_command(label="Обновить списки", 
                                  command=self._refresh_lists)

        # Меню настройки
        settings_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        settings_menu.add_command(label="Параметры", 
                                command=self._show_settings)

        # Меню справка
        help_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", 
                            command=self._show_about)

        self['menu'] = menubar

    def _create_toolbar(self):
        """Создание панели инструментов с кнопками"""
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        # Создаем фреймы для группировки кнопок
        local_frame = ttk.LabelFrame(toolbar, text="Локальные")
        local_frame.pack(side=tk.LEFT, padx=5)

        remote_frame = ttk.LabelFrame(toolbar, text="Удаленные")
        remote_frame.pack(side=tk.LEFT, padx=5)

        common_frame = ttk.LabelFrame(toolbar, text="Общие")
        common_frame.pack(side=tk.LEFT, padx=5)

        # Кнопки для локальных операций
        ttk.Button(local_frame, text="↑ Наверх", 
                  command=self._navigate_up_local).pack(side=tk.LEFT, padx=2)

        # Кнопки для удаленных операций
        ttk.Button(remote_frame, text="↑ Наверх", 
                  command=self._navigate_up_remote).pack(side=tk.LEFT, padx=2)

        # Общие кнопки
        buttons = [
            ("↻ Обновить", self._refresh_lists),
            ("✚ Папка", self._create_folder),
            ("↑ Загрузить", self._upload_files),
            ("↓ Скачать", self._download_files),
            ("✕ Удалить", self._delete_selected)
        ]

        for text, command in buttons:
            ttk.Button(common_frame, text=text, command=command).pack(side=tk.LEFT, padx=2)

    def _create_main_interface(self):
        """Создание основного интерфейса"""
        # Панель подключения
        self.connection_panel = ConnectionPanel(self, self._connect)
        self.connection_panel.pack(fill=tk.X, padx=5, pady=5)

        # Панель поиска
        self.search_panel = SearchPanel(self, self._on_search)
        self.search_panel.pack(fill=tk.X, padx=5, pady=2)

        # Панель инструментов
        self._create_toolbar()

        # Основной контейнер для списков файлов
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Локальные файлы
        local_frame = ttk.LabelFrame(main_frame, text="Локальные файлы")
        local_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.local_path = PathPanel(local_frame, self._change_local_directory)
        self.local_path.pack(fill=tk.X, padx=5, pady=2)
        
        self.local_files = FileListView(local_frame)
        self.local_files.pack(fill=tk.BOTH, expand=True)

        # Удаленные файлы
        remote_frame = ttk.LabelFrame(main_frame, text="Удаленные файлы")
        remote_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        self.remote_path = PathPanel(remote_frame)
        self.remote_path.pack(fill=tk.X, padx=5, pady=2)
        
        self.remote_files = FileListView(remote_frame)
        self.remote_files.pack(fill=tk.BOTH, expand=True)

        # Статус бар
        self.status_bar = StatusBar(self)
        self.status_bar.pack(fill=tk.X, padx=5, pady=5)

        # Обновляем списки файлов
        self._refresh_local_list()

    def _setup_bindings(self):
        """Настройка обработчиков событий"""
        self.local_files.bind("<Double-1>", self._on_local_double_click)
        self.remote_files.bind("<Double-1>", self._on_remote_double_click)
        self.bind("<F5>", lambda e: self._refresh_lists())
        self.bind("<Delete>", lambda e: self._delete_selected())
        self._setup_context_menus()

    def _setup_context_menus(self):
        """Настройка контекстных меню"""
        # Локальное меню
        self.local_menu = tk.Menu(self, tearoff=0)
        self.local_menu.add_command(label="Открыть", command=self._open_local_file)
        self.local_menu.add_command(label="Переименовать", command=self._rename_local)
        self.local_menu.add_command(label="Удалить", command=self._delete_local)
        self.local_menu.add_separator()
        self.local_menu.add_command(label="Создать папку", command=self._create_local_dir)
        self.local_files.bind("<Button-3>", self._show_local_menu)

        # Удаленное меню
        self.remote_menu = tk.Menu(self, tearoff=0)
        self.remote_menu.add_command(label="Скачать", command=self._download_files)
        self.remote_menu.add_command(label="Переименовать", command=self._rename_remote)
        self.remote_menu.add_command(label="Удалить", command=self._delete_remote)
        self.remote_menu.add_separator()
        self.remote_menu.add_command(label="Создать папку", command=self._create_remote_dir)
        self.remote_files.bind("<Button-3>", self._show_remote_menu)

    def start_update_handler(self):
        """Запуск обработчика обновлений интерфейса"""
        def update_handler():
            if not self.is_updating and not self.update_queue.empty():
                self.is_updating = True
                try:
                    while not self.update_queue.empty():
                        update_func = self.update_queue.get_nowait()
                        if update_func:
                            update_func()
                finally:
                    self.is_updating = False
            self.after(100, update_handler)
        
        self.after(100, update_handler)

    def schedule_update(self, update_func):
        """Планирование обновления интерфейса"""
        self.update_queue.put(update_func)

    def _load_connection_history(self) -> List[Dict]:
        """Загрузка истории подключений"""
        try:
            if os.path.exists(self.connection_history_file):
                with open(self.connection_history_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки истории: {e}")
        return []

    def _save_connection_history(self):
        """Сохранение истории подключений"""
        try:
            with open(self.connection_history_file, 'w') as f:
                json.dump(self.connection_history, f)
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")

    def _load_bookmarks(self) -> List[Dict]:
        """Загрузка закладок"""
        try:
            if os.path.exists(self.bookmarks_file):
                with open(self.bookmarks_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки закладок: {e}")
        return []

    def _save_bookmarks(self):
        """Сохранение закладок"""
        try:
            with open(self.bookmarks_file, 'w') as f:
                json.dump(self.bookmarks, f)
        except Exception as e:
            print(f"Ошибка сохранения закладок: {e}")

    def _add_to_history(self, host: str, port: int, user: str):
        """Добавление подключения в историю"""
        connection = {
            'host': host,
            'port': port,
            'user': user,
            'timestamp': datetime.now().isoformat()
        }
        
        # Удаляем дубликаты
        self.connection_history = [
            c for c in self.connection_history 
            if not (c['host'] == host and c['port'] == port and c['user'] == user)
        ]
        
        # Добавляем новое подключение в начало списка
        self.connection_history.insert(0, connection)
        
        # Ограничиваем размер истории
        self.connection_history = self.connection_history[:10]
        self._save_connection_history()

    def _connect(self, host: str, port: int, user: str, password: str):
        """Подключение к серверу"""
        success, message = self.ftp_client.connect(host, port, user, password)
        if success:
            self.status_bar.set_status("Подключено к серверу")
            self.connection_panel.set_connected_state(True)
            self.connection_menu.entryconfig("Отключиться", state="normal")
            self._add_to_history(host, port, user)
            self._refresh_remote_list()
            
            # Запускаем мониторинг соединения
            self.ftp_client.start_connection_monitor(self._on_connection_lost)
        else:
            self.status_bar.set_status(f"Ошибка подключения: {message}", error=True)

    def _disconnect(self):
        """Отключение от сервера"""
        self.ftp_client.disconnect()
        self.connection_panel.set_connected_state(False)
        self.connection_menu.entryconfig("Отключиться", state="disabled")
        self.remote_files.set_items([])
        self.remote_path.set_path("")
        self.status_bar.set_status("Отключено от сервера")

    def _on_connection_lost(self):
        """Обработка потери соединения"""
        self.schedule_update(lambda: [
            self.status_bar.set_status("Связь с сервером потеряна", error=True),
            messagebox.showwarning("Соединение", "Связь с сервером потеряна"),
            self._disconnect()
        ])

    def _refresh_lists(self):
        """Обновление списков файлов"""
        self._refresh_local_list()
        self._refresh_remote_list()

    def _refresh_local_list(self):
        """Обновление списка локальных файлов"""
        try:
            items = []
            current_dir = self.settings.get('default_local_dir')
            for item in os.listdir(current_dir):
                try:
                    path = os.path.join(current_dir, item)
                    stat = os.stat(path)
                    is_dir = os.path.isdir(path)
                    
                    # Для файлов показываем размер, для папок - количество элементов
                    if is_dir:
                        try:
                            size = f"{len(os.listdir(path))} элем."
                        except:
                            size = "Нет доступа"
                    else:
                        size = humanize.naturalsize(stat.st_size)
                    
                    # Преобразуем время в локальное
                    modified = datetime.fromtimestamp(stat.st_mtime).strftime(
                        self.settings.get('date_format', "%Y-%m-%d %H:%M")
                    )
                    
                    # Создаем словарь с информацией о файле
                    items.append({
                        'name': item,
                        'size': size,
                        'type': "Папка" if is_dir else "Файл",
                        'modified': modified
                    })
                except Exception as e:
                    # Если не удалось получить информацию о файле, добавляем с ошибкой
                    items.append({
                        'name': item,
                        'size': "Ошибка",
                        'type': "Неизвестно",
                        'modified': ""
                    })

            # Применяем фильтрацию и сортировку к словарям
            items = filter_hidden_files(items, self.settings.get('show_hidden_files'))
            items = sort_items(items, self.settings.get('sort_folders_first'))
            
            # Преобразуем обратно в кортежи для отображения
            items = [(item['name'], item['size'], item['type'], item['modified']) for item in items]
            
            self.local_files.set_items(items)
            self.local_path.set_path(current_dir)
        except Exception as e:
            self.status_bar.set_status(f"Ошибка чтения локальной директории: {e}", error=True)

    def _refresh_remote_list(self):
        """Обновление списка удаленных файлов"""
        if not self.ftp_client.ftp:
            return
            
        try:
            items = self.ftp_client.list_files()
            # Преобразуем кортежи в словари для фильтрации и сортировки
            dict_items = [
                {
                    'name': item[0],
                    'size': item[1],
                    'type': item[2],
                    'modified': item[3]
                }
                for item in items
            ]
            dict_items = filter_hidden_files(dict_items, self.settings.get('show_hidden_files'))
            dict_items = sort_items(dict_items, self.settings.get('sort_folders_first'))
            # Преобразуем обратно в кортежи для отображения
            items = [
                (item['name'], item['size'], item['type'], item['modified'])
                for item in dict_items
            ]
            self.remote_files.set_items(items)
            self.remote_path.set_path(self.ftp_client.get_current_directory())
        except Exception as e:
            self.status_bar.set_status(f"Ошибка чтения удаленной директории: {e}", error=True)

    def _on_search(self, text: str, scope: str, case_sensitive: bool, search_in_folders: bool):
        """Обработка поиска файлов"""
        if not text:  # Если поисковый запрос пустой, показываем все файлы
            self._refresh_lists()
            return

        # Функция для проверки соответствия имени файла поисковому запросу
        def matches_search(name: str) -> bool:
            if not case_sensitive:
                return text.lower() in name.lower()
            return text in name

        # Поиск в локальных файлах
        if scope in ["local", "both"]:
            try:
                items = []
                current_dir = self.settings.get('default_local_dir')
                for item in os.listdir(current_dir):
                    try:
                        path = os.path.join(current_dir, item)
                        is_dir = os.path.isdir(path)
                        
                        # Проверяем соответствие поисковому запросу
                        if matches_search(item) or (is_dir and search_in_folders):
                            stat = os.stat(path)
                            
                            # Получаем размер или количество элементов для папок
                            if is_dir:
                                try:
                                    size = f"{len(os.listdir(path))} элем."
                                except:
                                    size = "Нет доступа"
                            else:
                                size = humanize.naturalsize(stat.st_size)
                            
                            # Время модификации
                            modified = datetime.fromtimestamp(stat.st_mtime).strftime(
                                self.settings.get('date_format', "%Y-%m-%d %H:%M")
                            )
                            
                            items.append({
                                'name': item,
                                'size': size,
                                'type': "Папка" if is_dir else "Файл",
                                'modified': modified
                            })
                    except Exception:
                        continue

                # Применяем фильтрацию и сортировку
                items = filter_hidden_files(items, self.settings.get('show_hidden_files'))
                items = sort_items(items, self.settings.get('sort_folders_first'))
                
                # Преобразуем в кортежи для отображения
                items = [(item['name'], item['size'], item['type'], item['modified']) 
                        for item in items]
                
                self.local_files.set_items(items)
            except Exception as e:
                self.status_bar.set_status(f"Ошибка поиска в локальных файлах: {e}", error=True)

        # Поиск в удаленных файлах
        if scope in ["remote", "both"] and self.ftp_client.ftp:
            try:
                items = self.ftp_client.list_files()
                filtered_items = []
                
                for item in items:
                    name, size, type_, modified = item
                    is_dir = type_ == "Папка"
                    
                    if matches_search(name) or (is_dir and search_in_folders):
                        filtered_items.append({
                            'name': name,
                            'size': size,
                            'type': type_,
                            'modified': modified
                        })

                # Применяем фильтрацию и сортировку
                filtered_items = filter_hidden_files(filtered_items, self.settings.get('show_hidden_files'))
                filtered_items = sort_items(filtered_items, self.settings.get('sort_folders_first'))
                
                # Преобразуем в кортежи для отображения
                filtered_items = [(item['name'], item['size'], item['type'], item['modified']) 
                                for item in filtered_items]
                
                self.remote_files.set_items(filtered_items)
            except Exception as e:
                self.status_bar.set_status(f"Ошибка поиска в удаленных файлах: {e}", error=True)

        # Обновляем статус
        total_found = len(self.local_files.get_children()) + len(self.remote_files.get_children())
        self.status_bar.set_status(f"Найдено элементов: {total_found}")

    def _show_quick_connect(self):
        """Показ окна быстрого подключения"""
        QuickConnectDialog(self, self._connect)

    def _show_connection_history(self):
        """Показ истории подключений"""
        HistoryDialog(self, self.connection_history, self._connect_from_history)

    def _connect_from_history(self, values):
        """Подключение из истории"""
        host, port, user, _ = values
        self.connection_panel.entries["host"].delete(0, tk.END)
        self.connection_panel.entries["host"].insert(0, host)
        
        self.connection_panel.entries["port"].delete(0, tk.END)
        self.connection_panel.entries["port"].insert(0, str(port))
        
        self.connection_panel.entries["user"].delete(0, tk.END)
        self.connection_panel.entries["user"].insert(0, user)
        
        self._connect(host, port, user, "")  # Пароль нужно будет ввести заново

    def _show_bookmarks(self):
        """Показ закладок"""
        BookmarksDialog(self, self.bookmarks, 
                  self._connect_from_bookmark,
                  self._delete_bookmark)

    def _connect_from_bookmark(self, values):
        """Подключение из закладки"""
        name, host, port, user = values
        bookmark = next((b for b in self.bookmarks if b['name'] == name), None)
        if not bookmark:
            messagebox.showerror("Ошибка", "Закладка не найдена")
            return
        
        self.connection_panel.entries["host"].delete(0, tk.END)
        self.connection_panel.entries["host"].insert(0, host)
        
        self.connection_panel.entries["port"].delete(0, tk.END)
        self.connection_panel.entries["port"].insert(0, str(port))
        
        self.connection_panel.entries["user"].delete(0, tk.END)
        self.connection_panel.entries["user"].insert(0, user)
        
        # Расшифровываем и устанавливаем пароль
        password = self.crypto.decrypt(bookmark.get('password', ''))
        self.connection_panel.password_entry.delete(0, tk.END)
        self.connection_panel.password_entry.insert(0, password)
        
        self._connect(host, port, user, password)

    def _add_bookmark(self):
        """Добавление текущего сервера в закладки"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return
        
        name = simpledialog.askstring("Закладка", "Введите название закладки:")
        if name:
            # Шифруем пароль перед сохранением
            password = self.connection_panel.password_entry.get()
            encrypted_password = self.crypto.encrypt(password)
            
            bookmark = {
                'name': name,
                'host': self.connection_panel.entries["host"].get(),
                'port': int(self.connection_panel.entries["port"].get()),
                'user': self.connection_panel.entries["user"].get(),
                'password': encrypted_password
            }
            self.bookmarks.append(bookmark)
            self._save_bookmarks()
            messagebox.showinfo("Успех", "Закладка добавлена")

    def _delete_bookmark(self, name: str) -> bool:
        """Удаление закладки"""
        if messagebox.askyesno("Подтверждение", f"Удалить закладку '{name}'?"):
            self.bookmarks = [b for b in self.bookmarks if b['name'] != name]
            self._save_bookmarks()
            return True
        return False

    def _show_settings(self):
        """Показ окна настроек"""
        dialog = SettingsDialog(self, self.settings.current_settings, self._save_settings)
        self.wait_window(dialog)

    def _save_settings(self, new_settings: Dict):
        """Сохранение настроек"""
        self.settings.update(new_settings)
        self.settings.save_settings()
        self._refresh_lists()

    def _show_about(self):
        """Показ окна 'О программе'"""
        AboutDialog(self)

    def _create_folder(self):
        """Создание новой папки"""
        dirname = simpledialog.askstring("Создать папку", "Введите имя папки:")
        if not dirname:
            return

        # Создание локальной папки
        if self.local_files.focus():
            try:
                path = os.path.join(self.settings.get('default_local_dir'), dirname)
                os.makedirs(path, exist_ok=True)
                self._refresh_local_list()
                self.status_bar.set_status(f"Создана папка: {dirname}")
            except Exception as e:
                self.status_bar.set_status(f"Ошибка создания папки: {e}", error=True)

        # Создание удаленной папки
        elif self.remote_files.focus() and self.ftp_client.ftp:
            try:
                self.ftp_client.ftp.mkd(dirname)
                self._refresh_remote_list()
                self.status_bar.set_status(f"Создана папка: {dirname}")
            except Exception as e:
                self.status_bar.set_status(f"Ошибка создания папки: {e}", error=True)

    def _upload_files(self):
        """Загрузка файлов на сервер"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.local_files.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файлы для загрузки")
            return

        try:
            total = len(selected)
            for i, item_id in enumerate(selected, 1):
                values = self.local_files.item(item_id)['values']
                filename = values[0]
                is_dir = values[2] == "Папка"
                local_path = os.path.join(self.settings.get('default_local_dir'), filename)

                if is_dir:
                    # Сохраняем текущую удаленную директорию
                    initial_remote_dir = self.ftp_client.ftp.pwd()
                    
                    try:
                        # Создаем корневую папку на сервере
                        try:
                            self.ftp_client.ftp.mkd(filename)
                        except:
                            pass  # Папка может уже существовать
                        
                        # Переходим в созданную папку
                        self.ftp_client.ftp.cwd(filename)
                        
                        # Рекурсивно обходим все подпапки и файлы
                        for root, dirs, files in os.walk(local_path):
                            # Получаем относительный путь от корневой папки
                            rel_path = os.path.relpath(root, local_path)
                            
                            if rel_path != '.':
                                # Создаем структуру папок на сервере
                                remote_path_parts = rel_path.split(os.sep)
                                for part in remote_path_parts:
                                    try:
                                        self.ftp_client.ftp.mkd(part)
                                    except:
                                        pass  # Папка может уже существовать
                                    self.ftp_client.ftp.cwd(part)
                            
                            # Загружаем все файлы в текущей папке
                            for file in files:
                                local_file = os.path.join(root, file)
                                with open(local_file, 'rb') as f:
                                    self.ftp_client.ftp.storbinary(f'STOR {file}', f)
                                    
                                progress = (i / total) * 100
                                self.status_bar.set_progress(progress)
                                self.status_bar.set_status(f"Загружен файл: {file}")
                            
                            # Возвращаемся в родительскую папку, если мы не в корне
                            if rel_path != '.':
                                for _ in remote_path_parts:
                                    self.ftp_client.ftp.cwd('..')
                        
                        # Возвращаемся в исходную директорию
                        self.ftp_client.ftp.cwd(initial_remote_dir)
                        
                    except Exception as e:
                        # В случае ошибки возвращаемся в исходную директорию
                        self.ftp_client.ftp.cwd(initial_remote_dir)
                        raise e
                        
                else:
                    # Загружаем отдельный файл
                    with open(local_path, 'rb') as f:
                        self.ftp_client.ftp.storbinary(f'STOR {filename}', f)
                        progress = (i / total) * 100
                        self.status_bar.set_progress(progress)
                        self.status_bar.set_status(f"Загружен файл: {filename}")

            self._refresh_remote_list()
            self.status_bar.set_status("Загрузка завершена")
            self.status_bar.set_progress(100)

        except Exception as e:
            self.status_bar.set_status(f"Ошибка загрузки: {e}", error=True)
            messagebox.showerror("Ошибка", f"Ошибка загрузки: {str(e)}")

    def _download_files(self):
        """Скачивание файлов с сервера"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_files.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файлы для скачивания")
            return

        try:
            total = len(selected)
            for i, item_id in enumerate(selected, 1):
                values = self.remote_files.item(item_id)['values']
                filename = values[0]
                is_dir = values[2] == "Папка"
                local_path = os.path.join(self.settings.get('default_local_dir'), filename)

                if is_dir:
                    # Создаем локальную папку
                    os.makedirs(local_path, exist_ok=True)
                    
                    # Сохраняем текущую директорию
                    current_remote = self.ftp_client.ftp.pwd()
                    
                    try:
                        # Переходим в удаленную папку
                        self.ftp_client.ftp.cwd(filename)
                        
                        # Получаем список файлов
                        for item in self.ftp_client.list_files():
                            name, _, type_, _ = item
                            if type_ == "Файл":
                                # Скачиваем файл
                                local_file = os.path.join(local_path, name)
                                with open(local_file, 'wb') as f:
                                    self.ftp_client.ftp.retrbinary(f'RETR {name}', f.write)
                    finally:
                        # Возвращаемся в исходную директорию
                        self.ftp_client.ftp.cwd(current_remote)
                else:
                    # Скачиваем файл
                    with open(local_path, 'wb') as f:
                        self.ftp_client.ftp.retrbinary(f'RETR {filename}', f.write)

                progress = (i / total) * 100
                self.status_bar.set_progress(progress)
                self.status_bar.set_status(f"Скачано {i}/{total}: {filename}")

            self._refresh_local_list()
            self.status_bar.set_status("Скачивание завершено")
            self.status_bar.set_progress(100)

        except Exception as e:
            self.status_bar.set_status(f"Ошибка скачивания: {e}", error=True)

    def _delete_selected(self):
        """Удаление выбранных файлов"""
        # Удаление локальных файлов
        if self.local_files.focus():
            selected = self.local_files.selection()
            if not selected:
                return

            if not messagebox.askyesno("Подтверждение", 
                                     "Удалить {} выбранных элементов?".format(len(selected))):
                return

            try:
                for item_id in selected:
                    values = self.local_files.item(item_id)['values']
                    filename = str(values[0])  # Преобразуем в строку
                    path = os.path.join(self.settings.get('default_local_dir'), filename)
                    
                    if os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)

                self._refresh_local_list()
                self.status_bar.set_status("Удаление завершено")

            except Exception as e:
                self.status_bar.set_status("Ошибка удаления: {}".format(str(e)), error=True)

        # Удаление удаленных файлов
        elif self.remote_files.focus() and self.ftp_client.ftp:
            selected = self.remote_files.selection()
            if not selected:
                return

            if not messagebox.askyesno("Подтверждение", 
                                     "Удалить {} выбранных элементов?".format(len(selected))):
                return

            try:
                for item_id in selected:
                    values = self.remote_files.item(item_id)['values']
                    filename = str(values[0])  # Преобразуем в строку
                    is_dir = values[2] == "Папка"

                    if is_dir:
                        self.ftp_client.ftp.rmd(filename)
                    else:
                        self.ftp_client.ftp.delete(filename)

                self._refresh_remote_list()
                self.status_bar.set_status("Удаление завершено")

            except Exception as e:
                self.status_bar.set_status("Ошибка удаления: {}".format(str(e)), error=True)

    def _on_local_double_click(self, event):
        """Обработка двойного клика по локальному файлу"""
        item = self.local_files.identify('item', event.x, event.y)
        if not item:
            return

        values = self.local_files.item(item)['values']
        if not values:
            return

        filename = str(values[0])
        is_dir = values[2] == "Папка"

        if is_dir:
            try:
                # Формируем новый путь
                new_path = os.path.join(self.settings.get('default_local_dir'), filename)
                if os.path.exists(new_path) and os.path.isdir(new_path):
                    # Обновляем текущую директорию
                    self.settings.set('default_local_dir', new_path)
                    # Обновляем список файлов
                    self._refresh_local_list()
                    self.status_bar.set_status(f"Текущая локальная директория: {new_path}")
            except Exception as e:
                self.status_bar.set_status(f"Ошибка перехода в папку: {str(e)}", error=True)
        else:
            # Для файлов можно добавить открытие файла
            try:
                import subprocess
                import sys
                path = os.path.join(self.settings.get('default_local_dir'), filename)
                if sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', path])
                elif sys.platform == 'win32':  # Windows
                    os.startfile(path)
                else:  # Linux
                    subprocess.run(['xdg-open', path])
            except Exception as e:
                self.status_bar.set_status(f"Ошибка открытия файла: {str(e)}", error=True)

    def _on_remote_double_click(self, event):
        """Обработка двойного клика по удаленному файлу"""
        if not self.ftp_client.ftp:
            return

        item = self.remote_files.identify('item', event.x, event.y)
        if not item:
            return

        values = self.remote_files.item(item)['values']
        if not values:
            return

        filename = values[0]
        is_dir = values[2] == "Папка"

        if is_dir:
            try:
                # Переходим в выбранную директорию
                self.ftp_client.ftp.cwd(filename)
                # Обновляем список файлов
                self._refresh_remote_list()
            except Exception as e:
                self.status_bar.set_status(f"Ошибка перехода в папку: {e}", error=True)

    def _show_local_menu(self, event):
        """Показ локального контекстного меню"""
        item = self.local_files.identify_row(event.y)
        if item:
            self.local_files.selection_set(item)
            self.local_menu.post(event.x_root, event.y_root)

    def _show_remote_menu(self, event):
        """Показ удаленного контекстного меню"""
        item = self.remote_files.identify_row(event.y)
        if item:
            self.remote_files.selection_set(item)
            self.remote_menu.post(event.x_root, event.y_root)

    def _open_local_file(self):
        """Открытие локального файла"""
        # TODO: Реализовать открытие файла

    def _rename_local(self):
        """Переименование локального файла"""
        # TODO: Реализовать переименование

    def _delete_local(self):
        """Удаление локального файла"""
        # TODO: Реализовать удаление

    def _create_local_dir(self):
        """Создание локальной папки"""
        # TODO: Реализовать создание папки

    def _rename_remote(self):
        """Переименование удаленного файла"""
        # TODO: Реализовать переименование

    def _delete_remote(self):
        """Удаление удаленного файла"""
        # TODO: Реализовать удаление

    def _create_remote_dir(self):
        """Создание удаленной папки"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return
            
        dirname = simpledialog.askstring("Создать папку", "Введите имя папки:")
        if not dirname:
            return
            
        try:
            self.ftp_client.ftp.mkd(dirname)
            self._refresh_remote_list()
            self.status_bar.set_status(f"Создана папка: {dirname}")
        except Exception as e:
            self.status_bar.set_status(f"Ошибка создания папки: {e}", error=True)
            messagebox.showerror("Ошибка", f"Не удалось создать папку: {str(e)}")

    def _change_local_directory(self, path: str):
        """Изменение локальной директории"""
        self.settings.set('default_local_dir', path)
        self.settings.save_settings()
        self._refresh_local_list()

    def _navigate_up_local(self):
        """Переход на уровень выше в локальной файловой системе"""
        current_dir = self.settings.get('default_local_dir')
        parent_dir = os.path.dirname(current_dir)
        if os.path.exists(parent_dir) and parent_dir != current_dir:
            self.settings.set('default_local_dir', parent_dir)
            self._refresh_local_list()
            self.status_bar.set_status(f"Текущая локальная директория: {parent_dir}")

    def _navigate_up_remote(self):
        """Переход на уровень выше в удаленной файловой системе"""
        if self.ftp_client.ftp:
            try:
                self.ftp_client.ftp.cwd('..')
                current_dir = self.ftp_client.ftp.pwd()
                self._refresh_remote_list()
                self.status_bar.set_status(f"Текущая удаленная директория: {current_dir}")
            except Exception as e:
                self.status_bar.set_status(f"Ошибка перехода: {str(e)}", error=True)

    def _navigate_up(self):
        """Устаревший метод, оставлен для совместимости"""
        # Определяем, какой список в фокусе
        if self.local_files.focus():
            self._navigate_up_local()
        elif self.remote_files.focus() and self.ftp_client.ftp:
            self._navigate_up_remote()


if __name__ == "__main__":
    app = Application()
    app.mainloop()