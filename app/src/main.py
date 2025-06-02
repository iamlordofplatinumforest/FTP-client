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
import sys
import threading

from src.core.ftp_client import FTPClient
from src.core.settings import Settings
from src.gui.widgets import FileListView, ConnectionPanel, SearchPanel, PathPanel, StatusBar
from src.gui.dialogs import QuickConnectDialog, HistoryDialog, BookmarksDialog, SettingsDialog, AboutDialog
from src.gui.connection_stats import ConnectionStatsPanel
from src.utils.crypto import Crypto
from src.utils.helpers import filter_hidden_files, sort_items
from src.gui.styles import setup_styles


def debug_log(message: str):
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


class Application(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("FTP Client")
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        self.geometry(f"{screen_width}x{screen_height}+0+0")

        if sys.platform == 'darwin':
            self.attributes('-fullscreen', True)
        elif sys.platform == 'win32':
            self.state('zoomed')
        else:  # Linux
            self.attributes('-zoomed', True)

        self.settings = Settings()
        self.ftp_client = FTPClient()
        self.crypto = Crypto()

        self.connection_history_file = os.path.join(
            os.path.expanduser("~"), ".ftp_client_history.json")
        self.bookmarks_file = os.path.join(
            os.path.expanduser("~"), ".ftp_client_bookmarks.json")

        self.connection_history = self._load_connection_history()
        self.bookmarks = self._load_bookmarks()

        setup_styles()

        self._create_menu()
        self._create_main_interface()
        self._setup_bindings()

        self.update_queue = Queue()
        self.is_updating = False
        self.start_update_handler()

    def _create_menu(self):
        menubar = tk.Menu(self)
        connection_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Подключение", menu=connection_menu)
        connection_menu.add_command(label="Быстрое подключение", 
                                  command=self._show_quick_connect,
                                  accelerator="⌘Q" if sys.platform == 'darwin' else "Ctrl+Q")
        connection_menu.add_command(label="История подключений", 
                                  command=self._show_connection_history,
                                  accelerator="⌘H" if sys.platform == 'darwin' else "Ctrl+H")
        connection_menu.add_command(label="Закладки", 
                                  command=self._show_bookmarks)
        connection_menu.add_command(label="Добавить в закладки", 
                                  command=self._add_bookmark,
                                  accelerator="⌘B" if sys.platform == 'darwin' else "Ctrl+B")
        connection_menu.add_separator()
        connection_menu.add_command(label="Отключиться", 
                                  command=self._disconnect,
                                  state="disabled")
        self.connection_menu = connection_menu

        operations_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Операции", menu=operations_menu)
        operations_menu.add_command(label="Создать папку", 
                                  command=self._create_folder,
                                  accelerator="⌘N" if sys.platform == 'darwin' else "Ctrl+N")
        operations_menu.add_command(label="Загрузить файлы", 
                                  command=self._upload_files,
                                  accelerator="⌘U" if sys.platform == 'darwin' else "Ctrl+U")
        operations_menu.add_command(label="Скачать файлы", 
                                  command=self._download_files,
                                  accelerator="⌘D" if sys.platform == 'darwin' else "Ctrl+D")
        operations_menu.add_separator()
        operations_menu.add_command(label="Обновить списки", 
                                  command=self._refresh_lists,
                                  accelerator="F5 / ⌘R" if sys.platform == 'darwin' else "F5 / Ctrl+R")

        settings_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        settings_menu.add_command(label="Параметры", 
                                command=self._show_settings,
                                accelerator="⌘," if sys.platform == 'darwin' else "Ctrl+,")

        help_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", 
                            command=self._show_about)

        self['menu'] = menubar

    def _create_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        local_frame = ttk.LabelFrame(toolbar, text="Локальные")
        local_frame.pack(side=tk.LEFT, padx=5)

        remote_frame = ttk.LabelFrame(toolbar, text="Удаленные")
        remote_frame.pack(side=tk.LEFT, padx=5)

        common_frame = ttk.LabelFrame(toolbar, text="Общие")
        common_frame.pack(side=tk.LEFT, padx=5)

        ttk.Button(local_frame, text="↑ Наверх", 
                  command=self._navigate_up_local).pack(side=tk.LEFT, padx=2)

        ttk.Button(remote_frame, text="↑ Наверх", 
                  command=self._navigate_up_remote).pack(side=tk.LEFT, padx=2)

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
        self.connection_panel = ConnectionPanel(self, self._connect)
        self.connection_panel.pack(fill=tk.X, padx=5, pady=5)

        self.stats_panel = ConnectionStatsPanel(self)
        self.stats_panel.pack(fill=tk.X, padx=5, pady=2)

        self.search_panel = SearchPanel(self, self._on_search)
        self.search_panel.pack(fill=tk.X, padx=5, pady=2)

        self._create_toolbar()

        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        local_frame = ttk.LabelFrame(main_frame, text="Локальные файлы")
        local_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.local_path = PathPanel(local_frame, self._change_local_directory)
        self.local_path.pack(fill=tk.X, padx=5, pady=2)
        
        self.local_files = FileListView(local_frame)
        self.local_files.pack(fill=tk.BOTH, expand=True)

        remote_frame = ttk.LabelFrame(main_frame, text="Удаленные файлы")
        remote_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        self.remote_path = PathPanel(remote_frame)
        self.remote_path.pack(fill=tk.X, padx=5, pady=2)
        
        self.remote_files = FileListView(remote_frame)
        self.remote_files.pack(fill=tk.BOTH, expand=True)

        self.status_bar = StatusBar(self)
        self.status_bar.pack(fill=tk.X, padx=5, pady=5)

        self._refresh_local_list()

    def _setup_bindings(self):
        # Двойной клик
        self.local_files.bind("<Double-1>", self._on_local_double_click)
        self.remote_files.bind("<Double-1>", self._on_remote_double_click)
        
        # Горячие клавиши для всего приложения
        self.bind_all("<F5>", lambda e: self._refresh_lists())
        self.bind_all("<Escape>", lambda e: self._toggle_fullscreen())
        
        # Навигация
        self.bind_all("<BackSpace>", lambda e: self._navigate_up())
        self.bind_all("<Alt-Left>", lambda e: self._navigate_up())
        self.bind_all("<Alt-Up>", lambda e: self._navigate_up())
        
        # Используем Command на macOS и Control на других системах
        if sys.platform == 'darwin':
            # На macOS Command = Meta
            self.bind_all("<Meta-q>", lambda e: self._show_quick_connect())
            self.bind_all("<Meta-r>", lambda e: self._refresh_lists())
            self.bind_all("<Meta-u>", lambda e: self._upload_files())
            self.bind_all("<Meta-d>", lambda e: self._download_files())
            self.bind_all("<Meta-n>", lambda e: self._create_folder())
            self.bind_all("<Meta-b>", lambda e: self._add_bookmark())
            self.bind_all("<Meta-h>", lambda e: self._show_connection_history())
            self.bind_all("<Meta-comma>", lambda e: self._show_settings())
            
            # Дополнительные клавиши для macOS
            self.bind_all("<Command-BackSpace>", lambda e: self._navigate_up())
            self.bind_all("<Command-Up>", lambda e: self._navigate_up())
            self.bind_all("<Command-Left>", lambda e: self._navigate_up())
            
            # Дублируем с Command для надежности
            self.bind_all("<Command-q>", lambda e: self._show_quick_connect())
            self.bind_all("<Command-r>", lambda e: self._refresh_lists())
            self.bind_all("<Command-u>", lambda e: self._upload_files())
            self.bind_all("<Command-d>", lambda e: self._download_files())
            self.bind_all("<Command-n>", lambda e: self._create_folder())
            self.bind_all("<Command-b>", lambda e: self._add_bookmark())
            self.bind_all("<Command-h>", lambda e: self._show_connection_history())
            self.bind_all("<Command-comma>", lambda e: self._show_settings())
        else:
            self.bind_all("<Control-q>", lambda e: self._show_quick_connect())
            self.bind_all("<Control-r>", lambda e: self._refresh_lists())
            self.bind_all("<Control-u>", lambda e: self._upload_files())
            self.bind_all("<Control-d>", lambda e: self._download_files())
            self.bind_all("<Control-n>", lambda e: self._create_folder())
            self.bind_all("<Control-b>", lambda e: self._add_bookmark())
            self.bind_all("<Control-h>", lambda e: self._show_connection_history())
            self.bind_all("<Control-comma>", lambda e: self._show_settings())
        
        # Контекстное меню
        self.local_files.bind("<Button-3>", self._show_local_menu)
        self.remote_files.bind("<Button-3>", self._show_remote_menu)
        
        # Создаем контекстные меню
        self._create_context_menus()

    def _create_context_menus(self):
        """Создание контекстных меню"""
        # Локальное контекстное меню
        self.local_context_menu = tk.Menu(self, tearoff=0)
        self.local_context_menu.add_command(label="Открыть", command=self._open_local_file)
        self.local_context_menu.add_separator()
        self.local_context_menu.add_command(label="Копировать", command=lambda: self._copy_files('local'))
        self.local_context_menu.add_command(label="Вставить", command=lambda: self._paste_files('local'))
        self.local_context_menu.add_separator()
        self.local_context_menu.add_command(label="Создать папку", command=self._create_local_dir)
        self.local_context_menu.add_command(label="Переименовать", command=self._rename_local)
        self.local_context_menu.add_command(label="Удалить", command=self._delete_local)
        self.local_context_menu.add_separator()
        self.local_context_menu.add_command(label="Загрузить на сервер", command=self._upload_files)
        
        # Удаленное контекстное меню
        self.remote_context_menu = tk.Menu(self, tearoff=0)
        self.remote_context_menu.add_command(label="Скачать", command=self._download_files)
        self.remote_context_menu.add_separator()
        self.remote_context_menu.add_command(label="Копировать", command=lambda: self._copy_files('remote'))
        self.remote_context_menu.add_command(label="Вставить", command=lambda: self._paste_files('remote'))
        self.remote_context_menu.add_separator()
        self.remote_context_menu.add_command(label="Создать папку", command=self._create_remote_dir)
        self.remote_context_menu.add_command(label="Переименовать", command=self._rename_remote)
        self.remote_context_menu.add_command(label="Удалить", command=self._delete_remote)

    def _show_local_menu(self, event):
        """Показ локального контекстного меню"""
        item = self.local_files.identify_row(event.y)
        if item:
            # Снимаем текущее выделение, если не зажат Ctrl/Command
            if not (event.state & 0x0004):  # 0x0004 это Control на Windows/Linux
                self.local_files.selection_clear(0, tk.END)
            # Выделяем элемент под курсором
            self.local_files.selection_add(item)
            # Показываем меню
            self.local_context_menu.post(event.x_root, event.y_root)
        return "break"

    def _show_remote_menu(self, event):
        """Показ удаленного контекстного меню"""
        if not self.ftp_client.ftp:
            return
            
        item = self.remote_files.identify_row(event.y)
        if item:
            # Снимаем текущее выделение, если не зажат Ctrl/Command
            if not (event.state & 0x0004):  # 0x0004 это Control на Windows/Linux
                self.remote_files.selection_clear(0, tk.END)
            # Выделяем элемент под курсором
            self.remote_files.selection_add(item)
            # Показываем меню
            self.remote_context_menu.post(event.x_root, event.y_root)
        return "break"

    def _copy_files(self, source):
        """Копирование файлов в буфер обмена"""
        self.clipboard_source = source
        self.clipboard_files = []
        
        if source == 'local':
            selected = self.local_files.selection()
            for item_id in selected:
                values = self.local_files.item(item_id)['values']
                self.clipboard_files.append(values[0])
        else:
            selected = self.remote_files.selection()
            for item_id in selected:
                values = self.remote_files.item(item_id)['values']
                self.clipboard_files.append(values[0])
                
        self.status_bar.set_status(f"Скопировано элементов: {len(self.clipboard_files)}")

    def _paste_files(self, target):
        """Вставка файлов из буфера обмена"""
        if not hasattr(self, 'clipboard_files') or not self.clipboard_files:
            return
            
        if self.clipboard_source == target:
            # Копирование в ту же панель - создаем копии файлов
            if target == 'local':
                for filename in self.clipboard_files:
                    src_path = os.path.join(self.settings.get('default_local_dir'), filename)
                    base, ext = os.path.splitext(filename)
                    new_name = f"{base} - копия{ext}"
                    dst_path = os.path.join(self.settings.get('default_local_dir'), new_name)
                    
                    if os.path.isdir(src_path):
                        import shutil
                        shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
                        
                self._refresh_local_list()
                
            else:  # remote
                if not self.ftp_client.ftp:
                    return
                    
                for filename in self.clipboard_files:
                    base, ext = os.path.splitext(filename)
                    new_name = f"{base} - копия{ext}"
                    self.ftp_client.copy_file(filename, new_name)
                    
                self._refresh_remote_list()
                
        else:
            # Копирование между панелями
            if self.clipboard_source == 'local':
                self._upload_files()
            else:
                self._download_files()
                
        self.status_bar.set_status("Вставка завершена")

    def _open_local_file(self):
        """Открытие локального файла"""
        selected = self.local_files.selection()
        if not selected:
            return
            
        values = self.local_files.item(selected[0])['values']
        filename = str(values[0])
        path = os.path.join(self.settings.get('default_local_dir'), filename)
        
        try:
            import subprocess
            if sys.platform == 'darwin':
                subprocess.run(['open', path])
            elif sys.platform == 'win32':
                os.startfile(path)
            else:
                subprocess.run(['xdg-open', path])
        except Exception as e:
            self.status_bar.set_status(f"Ошибка открытия файла: {str(e)}", error=True)

    def _rename_local(self):
        """Переименование локального файла"""
        selected = self.local_files.selection()
        if not selected:
            return
            
        values = self.local_files.item(selected[0])['values']
        old_name = str(values[0])
        
        new_name = simpledialog.askstring("Переименовать", 
                                        "Введите новое имя:",
                                        initialvalue=old_name)
        if not new_name or new_name == old_name:
            return
            
        try:
            old_path = os.path.join(self.settings.get('default_local_dir'), old_name)
            new_path = os.path.join(self.settings.get('default_local_dir'), new_name)
            
            if os.path.exists(new_path):
                if not messagebox.askyesno("Подтверждение", 
                                         f"Файл {new_name} уже существует. Перезаписать?"):
                    return
            
            os.rename(old_path, new_path)
            self._refresh_local_list()
            self.status_bar.set_status(f"Файл переименован: {old_name} -> {new_name}")
        except Exception as e:
            self.status_bar.set_status(f"Ошибка переименования: {str(e)}", error=True)
            messagebox.showerror("Ошибка", f"Не удалось переименовать файл: {str(e)}")

    def _create_local_dir(self):
        """Создание локальной папки"""
        dirname = simpledialog.askstring("Создать папку", "Введите имя папки:")
        if not dirname:
            return
            
        try:
            path = os.path.join(self.settings.get('default_local_dir'), dirname)
            os.makedirs(path)
            self._refresh_local_list()
            self.status_bar.set_status(f"Создана папка: {dirname}")
        except Exception as e:
            self.status_bar.set_status(f"Ошибка создания папки: {str(e)}", error=True)
            messagebox.showerror("Ошибка", f"Не удалось создать папку: {str(e)}")

    def _rename_remote(self):
        """Переименование удаленного файла"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return
            
        selected = self.remote_files.selection()
        if not selected:
            return
            
        values = self.remote_files.item(selected[0])['values']
        old_name = str(values[0])
        
        new_name = simpledialog.askstring("Переименовать", 
                                        "Введите новое имя:",
                                        initialvalue=old_name)
        if not new_name or new_name == old_name:
            return
            
        try:
            self.ftp_client.ftp.rename(old_name, new_name)
            self._refresh_remote_list()
            self.status_bar.set_status(f"Файл переименован: {old_name} -> {new_name}")
        except Exception as e:
            self.status_bar.set_status(f"Ошибка переименования: {str(e)}", error=True)
            messagebox.showerror("Ошибка", f"Не удалось переименовать файл: {str(e)}")

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
            self.status_bar.set_status(f"Ошибка создания папки: {str(e)}", error=True)
            messagebox.showerror("Ошибка", f"Не удалось создать папку: {str(e)}")

    def start_update_handler(self):
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
        self.update_queue.put(update_func)

    def _load_connection_history(self) -> List[Dict]:
        try:
            if os.path.exists(self.connection_history_file):
                with open(self.connection_history_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки истории: {e}")
        return []

    def _save_connection_history(self):
        try:
            with open(self.connection_history_file, 'w') as f:
                json.dump(self.connection_history, f)
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")

    def _load_bookmarks(self) -> List[Dict]:
        try:
            if os.path.exists(self.bookmarks_file):
                with open(self.bookmarks_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки закладок: {e}")
        return []

    def _save_bookmarks(self):
        try:
            with open(self.bookmarks_file, 'w') as f:
                json.dump(self.bookmarks, f)
        except Exception as e:
            print(f"Ошибка сохранения закладок: {e}")

    def _add_to_history(self, host: str, port: int, user: str):
        connection = {
            'host': host,
            'port': port,
            'user': user,
            'timestamp': datetime.now().isoformat()
        }

        self.connection_history = [
            c for c in self.connection_history 
            if not (c['host'] == host and c['port'] == port and c['user'] == user)
        ]

        self.connection_history.insert(0, connection)

        self.connection_history = self.connection_history[:10]
        self._save_connection_history()

    def _connect(self, host: str, port: int, user: str, password: str):
        if host is None and port is None and user is None and password is None:
            self._disconnect()
            return

        # Проверка пустых полей
        if not host:
            messagebox.showerror("Ошибка", "Поле 'Сервер' не может быть пустым")
            return
            
        if not port:
            messagebox.showerror("Ошибка", "Поле 'Порт' не может быть пустым")
            return
            
        if not user:
            messagebox.showerror("Ошибка", "Поле 'Пользователь' не может быть пустым")
            return
            
        if not password:
            messagebox.showerror("Ошибка", "Поле 'Пароль' не может быть пустым")
            return

        # Проверка корректности порта
        try:
            port = int(port)
            if port < 1 or port > 65535:
                messagebox.showerror("Ошибка", "Порт должен быть числом от 1 до 65535")
                return
        except ValueError:
            messagebox.showerror("Ошибка", "Порт должен быть числом")
            return

        try:
            # Сначала отключаемся, если есть активное подключение
            if self.ftp_client.ftp:
                self._disconnect()

            success, message = self.ftp_client.connect(host, port, user, password)
            if success:
                self.status_bar.set_status("Подключено к серверу")
                self.connection_panel.set_connected_state(True)
                self.connection_menu.entryconfig("Отключиться", state="normal")
                self._add_to_history(host, port, user)
                self._refresh_remote_list()

                self.stats_panel.start_monitoring(host, port)
                self.ftp_client.start_connection_monitor(self._on_connection_lost)
            else:
                error_msg = "Ошибка подключения"
                if "Connection refused" in message:
                    error_msg = "Не удалось подключиться к серверу. Проверьте адрес и порт."
                elif "Login incorrect" in message:
                    error_msg = "Неверное имя пользователя или пароль"
                elif "getaddrinfo failed" in message or "[Errno 8]" in message:
                    error_msg = "Не удалось найти сервер. Проверьте правильность введенного адреса и подключение к интернету."
                elif "Network is unreachable" in message:
                    error_msg = "Сеть недоступна. Проверьте подключение к интернету."
                elif "Connection timed out" in message:
                    error_msg = "Превышено время ожидания подключения"
                elif "nodename nor servname provided" in message:
                    error_msg = "Не удалось найти сервер. Проверьте правильность введенного адреса."
                elif "'NoneType' object has no attribute 'sendall'" in message:
                    error_msg = "Ошибка подключения. Пожалуйста, попробуйте еще раз."
                else:
                    error_msg = f"Ошибка подключения: {message}"
                
                messagebox.showerror("Ошибка", error_msg)
                self.status_bar.set_status(error_msg, error=True)
                
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                error_msg = "Превышено время ожидания подключения"
            elif "connection refused" in error_msg.lower():
                error_msg = "Не удалось подключиться к серверу. Проверьте адрес и порт."
            elif "network is unreachable" in error_msg.lower():
                error_msg = "Сеть недоступна. Проверьте подключение к интернету."
            elif "[errno 8]" in error_msg.lower() or "nodename nor servname provided" in error_msg.lower():
                error_msg = "Не удалось найти сервер. Проверьте правильность введенного адреса и подключение к интернету."
            elif "'nonetype' object has no attribute 'sendall'" in error_msg.lower():
                error_msg = "Ошибка подключения. Пожалуйста, попробуйте еще раз."
            
            messagebox.showerror("Ошибка", error_msg)
            self.status_bar.set_status(error_msg, error=True)

    def _disconnect(self):
        debug_log("\nDEBUG: Начало отключения от сервера")
        
        try:
            debug_log("DEBUG: Останавливаем мониторинг")
            self.stats_panel.stop_monitoring()
            
            debug_log("DEBUG: Вызываем disconnect у FTP клиента")
            self.ftp_client.disconnect()
            
            debug_log("DEBUG: Обновляем состояние панели подключения")
            self.connection_panel.set_connected_state(False)
            
            debug_log("DEBUG: Деактивируем пункт меню Отключиться")
            self.connection_menu.entryconfig("Отключиться", state="disabled")
            
            debug_log("DEBUG: Очищаем список удаленных файлов")
            self.remote_files.delete(*self.remote_files.get_children())
            
            debug_log("DEBUG: Очищаем путь")
            self.remote_path.set_path("")
            
            debug_log("DEBUG: Обновляем статус")
            self.status_bar.set_status("Отключено от сервера")
            
            debug_log("DEBUG: Отключение завершено успешно")
        except Exception as e:
            debug_log(f"DEBUG: Ошибка при отключении: {str(e)}")
            self.status_bar.set_status(f"Ошибка при отключении: {str(e)}", error=True)

    def _on_connection_lost(self):
        self.schedule_update(lambda: [
            self.status_bar.set_status("Связь с сервером потеряна", error=True),
            messagebox.showwarning("Соединение", "Связь с сервером потеряна"),
            self._disconnect()
        ])

    def _refresh_lists(self):
        self._refresh_local_list()
        self._refresh_remote_list()

    def _refresh_local_list(self):
        try:
            items = []
            current_dir = self.settings.get('default_local_dir')
            for item in os.listdir(current_dir):
                try:
                    path = os.path.join(current_dir, item)
                    stat = os.stat(path)
                    is_dir = os.path.isdir(path)

                    if is_dir:
                        try:
                            size = f"{len(os.listdir(path))} элем."
                        except:
                            size = "Нет доступа"
                    else:
                        size = humanize.naturalsize(stat.st_size)

                    modified = datetime.fromtimestamp(stat.st_mtime).strftime(
                        self.settings.get('date_format', "%Y-%m-%d %H:%M")
                    )

                    items.append({
                        'name': item,
                        'size': size,
                        'type': "Папка" if is_dir else "Файл",
                        'modified': modified
                    })
                except Exception as e:
                    items.append({
                        'name': item,
                        'size': "Ошибка",
                        'type': "Неизвестно",
                        'modified': ""
                    })

            items = filter_hidden_files(items, self.settings.get('show_hidden_files'))
            items = sort_items(items, self.settings.get('sort_folders_first'))

            items = [(item['name'], item['size'], item['type'], item['modified']) for item in items]
            
            self.local_files.set_items(items)
            self.local_path.set_path(current_dir)
        except Exception as e:
            self.status_bar.set_status(f"Ошибка чтения локальной директории: {e}", error=True)

    def _refresh_remote_list(self):
        if not self.ftp_client.ftp:
            return
            
        try:
            items = self.ftp_client.list_files()
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
            items = [
                (item['name'], item['size'], item['type'], item['modified'])
                for item in dict_items
            ]
            self.remote_files.set_items(items)
            self.remote_path.set_path(self.ftp_client.get_current_directory())
        except Exception as e:
            self.status_bar.set_status(f"Ошибка чтения удаленной директории: {e}", error=True)

    def _on_search(self, text: str, scope: str, case_sensitive: bool, search_in_folders: bool):
        if not text:
            self._refresh_lists()
            return

        def matches_search(name: str) -> bool:
            if not case_sensitive:
                return text.lower() in name.lower()
            return text in name

        if scope in ["local", "both"]:
            try:
                items = []
                current_dir = self.settings.get('default_local_dir')
                for item in os.listdir(current_dir):
                    try:
                        path = os.path.join(current_dir, item)
                        is_dir = os.path.isdir(path)

                        if matches_search(item) or (is_dir and search_in_folders):
                            stat = os.stat(path)

                            if is_dir:
                                try:
                                    size = f"{len(os.listdir(path))} элем."
                                except:
                                    size = "Нет доступа"
                            else:
                                size = humanize.naturalsize(stat.st_size)
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

                items = filter_hidden_files(items, self.settings.get('show_hidden_files'))
                items = sort_items(items, self.settings.get('sort_folders_first'))

                items = [(item['name'], item['size'], item['type'], item['modified']) 
                        for item in items]
                
                self.local_files.set_items(items)
            except Exception as e:
                self.status_bar.set_status(f"Ошибка поиска в локальных файлах: {e}", error=True)

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

                filtered_items = filter_hidden_files(filtered_items, self.settings.get('show_hidden_files'))
                filtered_items = sort_items(filtered_items, self.settings.get('sort_folders_first'))

                filtered_items = [(item['name'], item['size'], item['type'], item['modified']) 
                                for item in filtered_items]
                
                self.remote_files.set_items(filtered_items)
            except Exception as e:
                self.status_bar.set_status(f"Ошибка поиска в удаленных файлах: {e}", error=True)

        total_found = len(self.local_files.get_children()) + len(self.remote_files.get_children())
        self.status_bar.set_status(f"Найдено элементов: {total_found}")

    def _show_quick_connect(self):
        QuickConnectDialog(self, self._connect)

    def _show_connection_history(self):
        HistoryDialog(self, self.connection_history, self._connect_from_history)

    def _connect_from_history(self, values):
        host, port, user, _ = values
        self.connection_panel.entries["host"].delete(0, tk.END)
        self.connection_panel.entries["host"].insert(0, host)
        
        self.connection_panel.entries["port"].delete(0, tk.END)
        self.connection_panel.entries["port"].insert(0, str(port))
        
        self.connection_panel.entries["user"].delete(0, tk.END)
        self.connection_panel.entries["user"].insert(0, user)
        
        self._connect(host, port, user, "")

    def _show_bookmarks(self):
        BookmarksDialog(self, self.bookmarks, 
                  self._connect_from_bookmark,
                  self._delete_bookmark)

    def _connect_from_bookmark(self, values):
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

        password = self.crypto.decrypt(bookmark.get('password', ''))
        self.connection_panel.password_entry.delete(0, tk.END)
        self.connection_panel.password_entry.insert(0, password)
        
        self._connect(host, port, user, password)

    def _add_bookmark(self):
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return
        
        name = simpledialog.askstring("Закладка", "Введите название закладки:")
        if name:
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
        if messagebox.askyesno("Подтверждение", f"Удалить закладку '{name}'?"):
            self.bookmarks = [b for b in self.bookmarks if b['name'] != name]
            self._save_bookmarks()
            return True
        return False

    def _show_settings(self):
        settings_window = tk.Toplevel(self)
        settings_window.title("Настройки")
        settings_window.geometry("600x500")
        settings_window.transient(self)
        settings_window.grab_set()

        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="Общие")

        dir_frame = ttk.LabelFrame(general_frame, text="Директории")
        dir_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(dir_frame, text="Локальная директория:").pack(anchor="w", padx=5, pady=2)
        local_dir_frame = ttk.Frame(dir_frame)
        local_dir_frame.pack(fill=tk.X, padx=5, pady=2)
        
        local_dir_entry = ttk.Entry(local_dir_frame)
        local_dir_entry.insert(0, self.settings.get('default_local_dir'))
        local_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def choose_directory():
            directory = filedialog.askdirectory(initialdir=local_dir_entry.get())
            if directory:
                local_dir_entry.delete(0, tk.END)
                local_dir_entry.insert(0, directory)
                
        ttk.Button(local_dir_frame, text="Обзор", 
                  command=choose_directory).pack(side=tk.LEFT, padx=2)

        connection_frame = ttk.LabelFrame(general_frame, text="Подключение")
        connection_frame.pack(fill=tk.X, padx=5, pady=5)

        auto_reconnect_var = tk.BooleanVar(value=self.settings.get('auto_reconnect', True))
        ttk.Checkbutton(connection_frame, text="Автоматическое переподключение",
                       variable=auto_reconnect_var).pack(anchor="w", padx=5, pady=2)

        reconnect_frame = ttk.Frame(connection_frame)
        reconnect_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(reconnect_frame, text="Количество попыток:").pack(side=tk.LEFT)
        reconnect_attempts = ttk.Spinbox(reconnect_frame, from_=1, to=10, width=5)
        reconnect_attempts.set(self.settings.get('reconnect_attempts', 3))
        reconnect_attempts.pack(side=tk.LEFT, padx=5)

        interface_frame = ttk.LabelFrame(general_frame, text="Интерфейс")
        interface_frame.pack(fill=tk.X, padx=5, pady=5)

        sort_folders_var = tk.BooleanVar(value=self.settings.get('sort_folders_first', True))
        ttk.Checkbutton(interface_frame, text="Показывать папки первыми",
                       variable=sort_folders_var).pack(anchor="w", padx=5, pady=2)

        show_hidden_var = tk.BooleanVar(value=self.settings.get('show_hidden_files', False))
        ttk.Checkbutton(interface_frame, text="Показывать скрытые файлы",
                       variable=show_hidden_var).pack(anchor="w", padx=5, pady=2)

        confirm_frame = ttk.Frame(notebook)
        notebook.add(confirm_frame, text="Подтверждения")

        confirm_delete_var = tk.BooleanVar(value=self.settings.get('confirm_delete', True))
        ttk.Checkbutton(confirm_frame, text="Подтверждать удаление",
                       variable=confirm_delete_var).pack(anchor="w", padx=5, pady=2)

        confirm_overwrite_var = tk.BooleanVar(value=self.settings.get('confirm_overwrite', True))
        ttk.Checkbutton(confirm_frame, text="Подтверждать перезапись",
                       variable=confirm_overwrite_var).pack(anchor="w", padx=5, pady=2)

        performance_frame = ttk.Frame(notebook)
        notebook.add(performance_frame, text="Производительность")

        ttk.Label(performance_frame, text="Размер буфера (байт):").pack(anchor="w", padx=5, pady=2)
        buffer_size = ttk.Entry(performance_frame)
        buffer_size.insert(0, str(self.settings.get('buffer_size', 8192)))
        buffer_size.pack(anchor="w", padx=5, pady=2)

        ttk.Label(performance_frame, text="Время жизни кэша (сек):").pack(anchor="w", padx=5, pady=2)
        cache_ttl = ttk.Entry(performance_frame)
        cache_ttl.insert(0, str(self.settings.get('cache_ttl', 30)))
        cache_ttl.pack(anchor="w", padx=5, pady=2)

        btn_frame = ttk.Frame(settings_window)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        def save_settings():
            try:
                new_settings = {
                    'default_local_dir': local_dir_entry.get(),
                    'buffer_size': int(buffer_size.get()),
                    'auto_reconnect': auto_reconnect_var.get(),
                    'reconnect_attempts': int(reconnect_attempts.get()),
                    'cache_ttl': int(cache_ttl.get()),
                    'show_hidden_files': show_hidden_var.get(),
                    'confirm_delete': confirm_delete_var.get(),
                    'confirm_overwrite': confirm_overwrite_var.get(),
                    'sort_folders_first': sort_folders_var.get(),
                    'date_format': self.settings.get('date_format', "%Y-%m-%d %H:%M")
                }
                self._save_settings(new_settings)
                settings_window.destroy()
            except ValueError as e:
                messagebox.showerror("Ошибка", "Проверьте правильность введенных числовых значений")

        ttk.Button(btn_frame, text="Сохранить", 
                  command=save_settings).pack(side=tk.RIGHT, padx=5)

        ttk.Button(btn_frame, text="Отмена",
                  command=settings_window.destroy).pack(side=tk.RIGHT, padx=5)

    def _save_settings(self, new_settings: Dict):
        self.settings.update(new_settings)
        self.settings.save_settings()
        self._refresh_lists()

    def _show_about(self):
        AboutDialog(self)

    def _create_folder(self):
        dialog = tk.Toplevel(self)
        dialog.title("Создать папку")
        dialog.geometry("400x330")
        dialog.transient(self)
        dialog.grab_set()

        dialog.geometry("+%d+%d" % (
            self.winfo_rootx() + self.winfo_width()//2 - 200,
            self.winfo_rooty() + self.winfo_height()//2 - 125
        ))

        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.LabelFrame(main_frame, text="Введите имя папки", padding="10")
        input_frame.pack(fill=tk.X, padx=5, pady=(0, 15))

        name_entry = ttk.Entry(input_frame, width=40)
        name_entry.pack(fill=tk.X, padx=5, pady=5)
        name_entry.focus()

        radio_frame = ttk.LabelFrame(main_frame, text="Выберите место создания", padding="10")
        radio_frame.pack(fill=tk.X, padx=5, pady=(0, 15))

        location = tk.StringVar(value="local")

        ttk.Radiobutton(radio_frame, text="Локально", 
                       variable=location, value="local").pack(anchor=tk.W, padx=5, pady=2)
        remote_radio = ttk.Radiobutton(radio_frame, text="На сервере", 
                                     variable=location, value="remote")
        remote_radio.pack(anchor=tk.W, padx=5, pady=2)
        
        both_radio = ttk.Radiobutton(radio_frame, text="В обоих местах", 
                                   variable=location, value="both")
        both_radio.pack(anchor=tk.W, padx=5, pady=2)

        if not self.ftp_client.ftp:
            remote_radio.configure(state="disabled")
            both_radio.configure(state="disabled")

        def create():
            dirname = name_entry.get().strip()
            if not dirname:
                messagebox.showwarning("Ошибка", "Введите имя папки")
                return

            loc = location.get()
            if loc in ("local", "both"):
                try:
                    path = os.path.join(self.settings.get('default_local_dir'), dirname)
                    os.makedirs(path, exist_ok=True)
                    self._refresh_local_list()
                    self.status_bar.set_status(f"Создана локальная папка: {dirname}")
                except Exception as e:
                    self.status_bar.set_status(f"Ошибка создания локальной папки: {e}", error=True)

            if loc in ("remote", "both") and self.ftp_client.ftp:
                try:
                    self.ftp_client.ftp.mkd(dirname)
                    self._refresh_remote_list()
                    self.status_bar.set_status(f"Создана удаленная папка: {dirname}")
                except Exception as e:
                    self.status_bar.set_status(f"Ошибка создания удаленной папки: {e}", error=True)

            dialog.destroy()

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        center_frame = ttk.Frame(btn_frame)
        center_frame.pack(anchor=tk.CENTER)
        
        ttk.Button(center_frame, text="Создать", 
                  command=create, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(center_frame, text="Отмена",
                  command=dialog.destroy, width=15).pack(side=tk.LEFT, padx=5)

    def _upload_files(self):
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

                if not is_dir:
                    try:
                        self.ftp_client.ftp.size(filename)
                        if self.settings.get('confirm_overwrite', True):
                            if not messagebox.askyesno("Подтверждение", 
                                                     f"Файл {filename} уже существует. Перезаписать?"):
                                continue
                    except:
                        pass

                if is_dir:
                    initial_remote_dir = self.ftp_client.ftp.pwd()
                    
                    try:
                        try:
                            self.ftp_client.ftp.mkd(filename)
                        except:
                            pass  # Папка может уже существовать
                        self.ftp_client.ftp.cwd(filename)

                        for root, dirs, files in os.walk(local_path):
                            rel_path = os.path.relpath(root, local_path)
                            
                            if rel_path != '.':
                                remote_path_parts = rel_path.split(os.sep)
                                for part in remote_path_parts:
                                    try:
                                        self.ftp_client.ftp.mkd(part)
                                    except:
                                        pass
                                    self.ftp_client.ftp.cwd(part)

                            for file in files:
                                local_file = os.path.join(root, file)
                                try:
                                    self.ftp_client.ftp.size(file)
                                    if self.settings.get('confirm_overwrite', True):
                                        if not messagebox.askyesno("Подтверждение", 
                                                                 f"Файл {file} уже существует. Перезаписать?"):
                                            continue
                                except:
                                    pass

                                with open(local_file, 'rb') as f:
                                    self.ftp_client.ftp.storbinary(f'STOR {file}', f)
                                    
                                progress = (i / total) * 100
                                self.status_bar.set_progress(progress)
                                self.status_bar.set_status(f"Загружен файл: {file}")

                            if rel_path != '.':
                                for _ in remote_path_parts:
                                    self.ftp_client.ftp.cwd('..')

                        self.ftp_client.ftp.cwd(initial_remote_dir)
                        
                    except Exception as e:
                        self.ftp_client.ftp.cwd(initial_remote_dir)
                        raise e
                        
                else:
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
                if os.path.exists(local_path):
                    if self.settings.get('confirm_overwrite', True):
                        if not messagebox.askyesno("Подтверждение", 
                                                 f"Файл {filename} уже существует. Перезаписать?"):
                            continue

                if is_dir:
                    os.makedirs(local_path, exist_ok=True)
                    current_remote = self.ftp_client.ftp.pwd()
                    try:
                        self.ftp_client.ftp.cwd(filename)
                        for item in self.ftp_client.list_files():
                            name, _, type_, _ = item
                            if type_ == "Файл":
                                local_file = os.path.join(local_path, name)
                                with open(local_file, 'wb') as f:
                                    self.ftp_client.ftp.retrbinary(f'RETR {name}', f.write)
                    finally:
                        self.ftp_client.ftp.cwd(current_remote)
                else:
                    with open(local_path, 'wb') as f:
                        self.ftp_client.ftp.retrbinary(f'RETR {filename}', f.write)

                progress = (i / total) * 100
                self.status_bar.set_progress(progress)
                self.status_bar.set_status(f"Скачано {i}/{total}: {filename}")

            self._refresh_local_list()
            self.status_bar.set_status("Скачивание завершено")
            self.status_bar.set_progress(100)

        except Exception as e:
            self.status_bar.set_status(f"Ошибка скачивания: {str(e)}", error=True)

    def _delete_selected(self):
        """Обработчик удаления выбранных элементов"""
        if self.local_files.focus():
            self._delete_local()
        elif self.remote_files.focus() and self.ftp_client.ftp:
            self._delete_remote()
        return "break"  # Предотвращаем дальнейшую обработку события

    def _on_local_double_click(self, event):
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
                new_path = os.path.join(self.settings.get('default_local_dir'), filename)
                if os.path.exists(new_path) and os.path.isdir(new_path):
                    self.settings.set('default_local_dir', new_path)
                    self._refresh_local_list()
                    self.status_bar.set_status(f"Текущая локальная директория: {new_path}")
            except Exception as e:
                self.status_bar.set_status(f"Ошибка перехода в папку: {str(e)}", error=True)
        else:
            try:
                import subprocess
                import sys
                path = os.path.join(self.settings.get('default_local_dir'), filename)
                if sys.platform == 'darwin':
                    subprocess.run(['open', path])
                elif sys.platform == 'win32':
                    os.startfile(path)
                else:
                    subprocess.run(['xdg-open', path])
            except Exception as e:
                self.status_bar.set_status(f"Ошибка открытия файла: {str(e)}", error=True)

    def _on_remote_double_click(self, event):
        if not self.ftp_client.ftp:
            return

        item = self.remote_files.identify('item', event.x, event.y)
        if not item:
            return

        values = self.remote_files.item(item)['values']
        if not values:
            return

        filename = str(values[0])
        is_dir = values[2] == "Папка"

        if is_dir:
            try:
                self.ftp_client.ftp.cwd(filename)
                self._refresh_remote_list()
            except Exception as e:
                self.status_bar.set_status(f"Ошибка перехода в папку: {e}", error=True)

    def _toggle_fullscreen(self, event=None):
        if sys.platform == 'darwin':
            is_fullscreen = self.attributes('-fullscreen')
            self.attributes('-fullscreen', not is_fullscreen)
        elif sys.platform == 'win32':
            is_zoomed = self.state() == 'zoomed'
            self.state('normal' if is_zoomed else 'zoomed')
        else:
            is_zoomed = self.attributes('-zoomed')
            self.attributes('-zoomed', not is_zoomed)

    def _change_local_directory(self, path: str):
        self.settings.set('default_local_dir', path)
        self.settings.save_settings()
        self._refresh_local_list()

    def _navigate_up_local(self):
        current_dir = self.settings.get('default_local_dir')
        parent_dir = os.path.dirname(current_dir)
        if os.path.exists(parent_dir) and parent_dir != current_dir:
            self.settings.set('default_local_dir', parent_dir)
            self._refresh_local_list()
            self.status_bar.set_status(f"Текущая локальная директория: {parent_dir}")

    def _navigate_up_remote(self):
        if self.ftp_client.ftp:
            try:
                self.ftp_client.ftp.cwd('..')
                current_dir = self.ftp_client.ftp.pwd()
                self._refresh_remote_list()
                self.status_bar.set_status(f"Текущая удаленная директория: {current_dir}")
            except Exception as e:
                self.status_bar.set_status(f"Ошибка перехода: {str(e)}", error=True)

    def _navigate_up(self):
        if self.local_files.focus():
            self._navigate_up_local()
        elif self.remote_files.focus() and self.ftp_client.ftp:
            self._navigate_up_remote()

    def _on_drag_start(self, event):
        """Начало перетаскивания"""
        tree = event.widget
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            self._drag_data = {
                'source': tree,
                'item': item,
                'start_x': event.x,
                'start_y': event.y
            }

    def _on_drag_motion(self, event):
        """Процесс перетаскивания"""
        if hasattr(self, '_drag_data'):
            # Можно добавить визуальный эффект перетаскивания, если нужно
            pass

    def _on_drag_end(self, event):
        """Окончание перетаскивания"""
        if not hasattr(self, '_drag_data'):
            return

        source = self._drag_data['source']
        target = event.widget

        # Если перетаскивание между разными списками
        if source != target:
            if source == self.local_files and target == self.remote_files:
                self._upload_selected()
            elif source == self.remote_files and target == self.local_files:
                self._download_selected()

        del self._drag_data

    def _upload_selected(self):
        """Загрузка выбранных файлов на сервер"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.local_files.selection()
        if not selected:
            return

        def upload_thread():
            try:
                total = len(selected)
                for i, item_id in enumerate(selected, 1):
                    values = self.local_files.item(item_id)['values']
                    filename = str(values[0])
                    is_dir = values[2] == "Папка"
                    local_path = os.path.join(self.settings.get('default_local_dir'), filename)

                    # Проверяем существование файла на сервере
                    try:
                        if is_dir:
                            self.ftp_client.ftp.cwd(filename)
                            self.ftp_client.ftp.cwd('..')
                        else:
                            self.ftp_client.ftp.size(filename)
                            
                        if self.settings.get('confirm_overwrite', True):
                            confirm_event = threading.Event()
                            self.schedule_update(lambda: [
                                setattr(confirm_event, 'result',
                                       messagebox.askyesno("Подтверждение",
                                                         f"Файл {filename} уже существует. Перезаписать?"))
                            ])
                            confirm_event.wait()
                            if not confirm_event.result:
                                continue
                    except:
                        pass

                    # Обновляем прогресс
                    progress = (i - 1) / total * 100
                    self.schedule_update(lambda p=progress, f=filename: [
                        self.status_bar.set_progress(p),
                        self.status_bar.set_status(f"Загрузка {i}/{total}: {f}")
                    ])

                    if is_dir:
                        success, message = self.ftp_client.upload_folder(local_path, filename)
                    else:
                        success, message = self.ftp_client.upload_file(local_path, filename)

                    if not success:
                        self.schedule_update(lambda: [
                            messagebox.showerror("Ошибка", f"Ошибка загрузки {filename}: {message}"),
                            self.status_bar.set_status(f"Ошибка загрузки: {message}", error=True)
                        ])
                        return

                self.schedule_update(lambda: [
                    self._refresh_remote_list(),
                    self.status_bar.set_status("Загрузка завершена"),
                    self.status_bar.set_progress(100)
                ])

            except Exception as e:
                self.schedule_update(lambda: [
                    messagebox.showerror("Ошибка", f"Ошибка загрузки: {str(e)}"),
                    self.status_bar.set_status(f"Ошибка загрузки: {str(e)}", error=True)
                ])

        Thread(target=upload_thread, daemon=True).start()

    def _download_selected(self):
        """Скачивание выбранных файлов с сервера"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_files.selection()
        if not selected:
            return

        def download_thread():
            try:
                total = len(selected)
                for i, item_id in enumerate(selected, 1):
                    values = self.remote_files.item(item_id)['values']
                    filename = str(values[0])
                    is_dir = values[2] == "Папка"
                    local_path = os.path.join(self.settings.get('default_local_dir'), filename)

                    # Проверяем существование файла локально
                    if os.path.exists(local_path):
                        if self.settings.get('confirm_overwrite', True):
                            confirm_event = threading.Event()
                            self.schedule_update(lambda: [
                                setattr(confirm_event, 'result',
                                       messagebox.askyesno("Подтверждение",
                                                         f"Файл {filename} уже существует. Перезаписать?"))
                            ])
                            confirm_event.wait()
                            if not confirm_event.result:
                                continue

                    # Обновляем прогресс
                    progress = (i - 1) / total * 100
                    self.schedule_update(lambda p=progress, f=filename: [
                        self.status_bar.set_progress(p),
                        self.status_bar.set_status(f"Скачивание {i}/{total}: {f}")
                    ])

                    if is_dir:
                        os.makedirs(local_path, exist_ok=True)
                        current_remote = self.ftp_client.ftp.pwd()
                        try:
                            self.ftp_client.ftp.cwd(filename)
                            for item in self.ftp_client.list_files():
                                name, _, type_, _ = item
                                if type_ == "Файл":
                                    local_file = os.path.join(local_path, name)
                                    with open(local_file, 'wb') as f:
                                        self.ftp_client.ftp.retrbinary(f'RETR {name}', f.write)
                        finally:
                            self.ftp_client.ftp.cwd(current_remote)
                    else:
                        success, message = self.ftp_client.download_file(filename, local_path)
                        if not success:
                            self.schedule_update(lambda: [
                                messagebox.showerror("Ошибка", f"Ошибка скачивания {filename}: {message}"),
                                self.status_bar.set_status(f"Ошибка скачивания: {message}", error=True)
                            ])
                            return

                self.schedule_update(lambda: [
                    self._refresh_local_list(),
                    self.status_bar.set_status("Скачивание завершено"),
                    self.status_bar.set_progress(100)
                ])

            except Exception as e:
                self.schedule_update(lambda: [
                    messagebox.showerror("Ошибка", f"Ошибка скачивания: {str(e)}"),
                    self.status_bar.set_status(f"Ошибка скачивания: {str(e)}", error=True)
                ])

        Thread(target=download_thread, daemon=True).start()

    def _delete_local(self):
        """Удаление локального файла"""
        selected = self.local_files.selection()
        if not selected:
            return
            
        if self.settings.get('confirm_delete', True):
            if not messagebox.askyesno("Подтверждение", 
                                     f"Удалить {len(selected)} выбранных элементов?"):
                return
        
        try:
            for item_id in selected:
                values = self.local_files.item(item_id)['values']
                filename = str(values[0])
                path = os.path.join(self.settings.get('default_local_dir'), filename)
                
                if os.path.isdir(path):
                    import shutil
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            
            self._refresh_local_list()
            self.status_bar.set_status("Удаление завершено")
        except Exception as e:
            self.status_bar.set_status(f"Ошибка удаления: {str(e)}", error=True)
            messagebox.showerror("Ошибка", f"Не удалось удалить файл(ы): {str(e)}")

    def _delete_remote(self):
        """Удаление удаленного файла"""
        if not self.ftp_client.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_files.selection()
        if not selected:
            return

        if self.settings.get('confirm_delete', True):
            if not messagebox.askyesno("Подтверждение", 
                                     f"Удалить {len(selected)} выбранных элементов?"):
                return

        try:
            for item_id in selected:
                values = self.remote_files.item(item_id)['values']
                filename = str(values[0])
                is_dir = values[2] == "Папка"
                
                if is_dir:
                    self.ftp_client.delete_directory_recursive(filename)
                else:
                    self.ftp_client.ftp.delete(filename)

            self._refresh_remote_list()
            self.status_bar.set_status("Удаление завершено")
        except Exception as e:
            self.status_bar.set_status(f"Ошибка удаления: {str(e)}", error=True)
            messagebox.showerror("Ошибка", f"Не удалось удалить файл(ы): {str(e)}")

    def _on_closing(self):
        """Обработчик закрытия окна"""
        if not messagebox.askyesno("Подтверждение", "Вы действительно хотите выйти из программы?"):
            return
            
        debug_log("\nDEBUG: Начало закрытия приложения")
        
        try:
            debug_log("DEBUG: Останавливаем мониторинг статистики")
            self.stats_panel.stop_monitoring()
            
            debug_log("DEBUG: Отключаемся от FTP сервера")
            self.ftp_client.disconnect()
            
            debug_log("DEBUG: Сохраняем настройки")
            self.settings.save_settings()
            
            debug_log("DEBUG: Закрытие приложения завершено")
        except Exception as e:
            debug_log(f"DEBUG: Ошибка при закрытии приложения: {str(e)}")
        finally:
            self.quit()


if __name__ == "__main__":
    app = Application()
    app.mainloop()