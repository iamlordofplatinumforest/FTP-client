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


class FTPClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced FTP Client")
        self.root.geometry("1400x750")

        # Ключ для шифрования (в реальном приложении должен храниться безопасно)
        self._key = 'my_secret_key'

        # Добавляем очередь обновлений и флаг обновления
        self.update_queue = Queue()
        self.is_updating = False
        
        # Настройки по умолчанию
        self.settings = {
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
        
        self.load_settings()  # Загружаем сохраненные настройки

        self.ftp = None
        self.ftp_lock = Lock()
        self.current_remote_dir = "/"
        self.current_local_dir = self.settings['default_local_dir']

        self.remote_cache = {}
        self.local_cache = {}
        self.task_queue = Queue()
        self.running = True
        self.worker_thread = None

        self.connection_history_file = os.path.join(os.path.expanduser("~"), ".ftp_client_history.json")
        self.bookmarks_file = os.path.join(os.path.expanduser("~"), ".ftp_client_bookmarks.json")
        self.connection_history = self.load_connection_history()
        self.bookmarks = self.load_bookmarks()
        self.current_sort_column = None
        self.sort_reverse = False

        self.create_widgets()
        self.setup_bindings()
        self.start_worker()

        self.ensure_local_dir()
        self.refresh_local_list()
        self.monitor_running = False

        self.create_connection_indicator()
        self.create_search_bar()
        self.load_saved_data()

        # Запускаем обработчик обновлений
        self.start_update_handler()

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
            self.root.after(100, update_handler)
        
        self.root.after(100, update_handler)

    def schedule_update(self, update_func):
        """Планирование обновления интерфейса"""
        self.update_queue.put(update_func)

    def create_connection_indicator(self):
        self.status_canvas = tk.Canvas(self.root, width=20, height=20, highlightthickness=0)
        self.status_canvas.pack(side=tk.RIGHT, padx=5)
        self.status_indicator = self.status_canvas.create_oval(2, 2, 18, 18, fill="red")

    def update_status_indicator(self, connected):
        color = "green" if connected else "red"
        self.status_canvas.itemconfig(self.status_indicator, fill=color)

    def ensure_local_dir(self):
        if not os.path.exists(self.current_local_dir):
            os.makedirs(self.current_local_dir, exist_ok=True)
            self.update_status(f"Создана директория: {self.current_local_dir}")

    def create_widgets(self):
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        style.configure("Treeview.Heading", font=('Helvetica', 10, 'bold'))

        self.create_connection_panel()

        self.create_status_panel()

        self.create_file_panels()

        self.create_progress_bar()

        self.create_toolbar()

    def create_connection_panel(self):
        frame = ttk.LabelFrame(self.root, text="Подключение")
        frame.pack(fill=tk.X, padx=5, pady=5)

        entries = [
            ("Сервер:", "host_entry", "localhost"),
            ("Порт:", "port_entry", "21"),
            ("Пользователь:", "user_entry", "user"),
        ]

        for i, (label, attr, default) in enumerate(entries):
            ttk.Label(frame, text=label).grid(row=i, column=0, padx=5, pady=2, sticky="e")
            entry = ttk.Entry(frame)
            entry.insert(0, default)
            entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
            setattr(self, attr, entry)

        # Создаем фрейм для пароля и кнопки показа
        pwd_frame = ttk.Frame(frame)
        pwd_frame.grid(row=3, column=1, padx=5, pady=2, sticky="ew")
        
        ttk.Label(frame, text="Пароль:").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        
        # Поле для пароля
        self.password_entry = ttk.Entry(pwd_frame, show="*")
        self.password_entry.insert(0, "pass")
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Переменная для отслеживания состояния показа пароля
        self.show_password = tk.BooleanVar(value=False)
        
        # Кнопка показа/скрытия пароля
        self.toggle_pwd_btn = ttk.Button(pwd_frame, text="👁", width=3,
                                       command=self.toggle_password_visibility)
        self.toggle_pwd_btn.pack(side=tk.LEFT, padx=(2, 0))

        self.connect_btn = ttk.Button(frame, text="Подключиться", command=self.connect)
        self.connect_btn.grid(row=4, column=0, columnspan=2, pady=5)

    def create_status_panel(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.X, padx=5, pady=2)

        self.local_path_var = tk.StringVar(value=f"Локальная: {self.current_local_dir}")
        self.remote_path_var = tk.StringVar(value="Удалённая: не подключено")

        ttk.Label(frame, textvariable=self.local_path_var, anchor="w").pack(side="left", fill="x", expand=True)
        ttk.Label(frame, textvariable=self.remote_path_var, anchor="w").pack(side="right", fill="x", expand=True)

    def create_file_panels(self):
        """Панели для отображения файлов"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Локальные файлы
        local_frame = ttk.LabelFrame(main_frame, text="Локальные файлы")
        local_frame.pack(side="left", fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.local_tree = self.create_treeview(local_frame)

        # Удаленные файлы
        remote_frame = ttk.LabelFrame(main_frame, text="Удаленные файлы")
        remote_frame.pack(side="right", fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.remote_tree = self.create_treeview(remote_frame)

    def create_treeview(self, parent):
        """Создание Treeview с настройками"""
        tree = ttk.Treeview(parent, columns=("name", "size", "type", "modified"), show="headings",
                            selectmode="extended")

        columns = [
            ("name", "Имя", 300),
            ("size", "Размер", 100),
            ("type", "Тип", 100),
            ("modified", "Изменён", 150)
        ]

        for col_id, heading, width in columns:
            tree.heading(col_id, text=heading)
            tree.column(col_id, width=width, anchor="w" if col_id == "name" else "center")

        scroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill=tk.BOTH, expand=True)
        return tree

    def create_progress_bar(self):
        """Прогресс-бар для операций"""
        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, padx=5, pady=2)
        self.progress_label = ttk.Label(self.root, text="Готов")
        self.progress_label.pack(fill=tk.X, padx=5)

    def create_toolbar(self):
        """Панель инструментов с кнопками"""
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        buttons = [
            ("↑ Наверх", self.navigate_up),
            ("↻ Обновить", self.refresh_lists),
            ("✚ Папка", self.create_remote_dir),
            ("↑ Загрузить", self.upload_files),
            ("↓ Скачать", self.download_files),
            ("✕ Удалить", self.delete_selected),
            ("📋 История", self.show_connection_history),
            ("⭐ Закладки", self.show_bookmarks),
            ("➕ В закладки", self.add_bookmark),
            ("⚙ Настройки", self.show_settings)
        ]

        for text, command in buttons:
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=2)

    def setup_bindings(self):
        """Настройка обработчиков событий"""
        self.local_tree.bind("<Double-1>", self.on_local_double_click)
        self.remote_tree.bind("<Double-1>", self.on_remote_double_click)
        self.root.bind("<F5>", lambda e: self.refresh_lists())
        self.root.bind("<Delete>", lambda e: self.delete_selected())
        self.setup_context_menus()

    def setup_context_menus(self):
        """Настройка контекстных меню"""
        # Локальное меню
        self.local_menu = tk.Menu(self.root, tearoff=0)
        self.local_menu.add_command(label="Открыть", command=self.open_local_file)
        self.local_menu.add_command(label="Переименовать", command=self.rename_local)
        self.local_menu.add_command(label="Удалить", command=self.delete_local)
        self.local_menu.add_separator()
        self.local_menu.add_command(label="Создать папку", command=self.create_local_dir)
        self.local_tree.bind("<Button-3>", self.show_local_menu)

        # Удаленное меню
        self.remote_menu = tk.Menu(self.root, tearoff=0)
        self.remote_menu.add_command(label="Скачать", command=self.download_files)
        self.remote_menu.add_command(label="Переименовать", command=self.rename_remote)
        self.remote_menu.add_command(label="Удалить", command=self.delete_remote)
        self.remote_menu.add_separator()
        self.remote_menu.add_command(label="Создать папку", command=self.create_remote_dir)
        self.remote_tree.bind("<Button-3>", self.show_remote_menu)

    def start_worker(self):
        """Запуск фонового потока"""

        def worker():
            while self.running:
                task = self.task_queue.get()
                if task is None: break
                try:
                    task()
                except Exception as e:
                    self.update_status(f"Ошибка: {e}", error=True)
                self.task_queue.task_done()

        self.worker_thread = Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def start_connection_monitor(self):
        """Запуск мониторинга соединения с адаптивным интервалом"""
        
        def monitor():
            check_interval = 30  # Начальный интервал
            consecutive_failures = 0
            max_interval = 120   # Максимальный интервал
            min_interval = 10    # Минимальный интервал
            
            while self.monitor_running:
                try:
                    with self.ftp_lock:
                        if self.ftp:
                            start_time = time.time()
                            self.ftp.voidcmd('NOOP')
                            response_time = time.time() - start_time
                            
                            # Адаптивная настройка интервала на основе времени отклика
                            if response_time < 0.1:  # Хороший отклик
                                check_interval = min(check_interval * 1.5, max_interval)
                            else:  # Медленный отклик
                                check_interval = max(check_interval * 0.75, min_interval)
                                
                            consecutive_failures = 0
                            self.root.after(0, self.update_status_indicator, True)
                            
                except:
                    consecutive_failures += 1
                    check_interval = max(check_interval * 0.5, min_interval)
                    
                    if consecutive_failures >= 3:
                        self.root.after(0, self.handle_connection_loss)
                        break
                        
                time.sleep(check_interval)

        Thread(target=monitor, daemon=True).start()

    def connect(self):
        """Обновленный метод подключения с поддержкой SSL/TLS"""
        host = self.host_entry.get()
        port = int(self.port_entry.get())
        user = self.user_entry.get()
        password = self.password_entry.get()
        use_tls = True  # Можно добавить чекбокс в интерфейс

        def connect_task():
            try:
                # Проверка доступности сервера
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                sock.close()
                if result != 0:
                    error_msg = f"Сервер {host}:{port} недоступен"
                    self.root.after(0, lambda msg=error_msg: messagebox.showerror("Ошибка", msg))
                    return

                # Подключение FTP
                with self.ftp_lock:
                    if self.ftp:
                        self.ftp.quit()
                    self.ftp = FTP()
                    self.ftp.connect(host, port, timeout=10)
                    self.ftp.login(user=user, passwd=password)
                    self.monitor_running = True
                    self.start_connection_monitor()

                    # Добавляем подключение в историю
                    self.add_to_history(host, port, user)

                    self.root.after(0, lambda: [
                        self.update_status_indicator(True),
                        self.connect_btn.config(text="Отключиться", command=self.disconnect),
                        self.refresh_remote_list()
                    ])
            except Exception as e:
                error_msg = str(e)  # Сохраняем сообщение об ошибке в переменную
                self.root.after(0, lambda msg=error_msg: [  # Передаем сообщение как параметр лямбды
                    messagebox.showerror("Ошибка", f"Ошибка подключения: {msg}"),
                    self.update_status_indicator(False)
                ])

        self.task_queue.put(connect_task)

    def upload_files(self):
        """Загрузка выбранных локальных файлов на сервер"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.local_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файлы для загрузки")
            return

        def upload_task():
            total = len(selected)
            success = 0
            errors = []

            for i, item_id in enumerate(selected):
                values = self.local_tree.item(item_id)['values']
                filename = values[0]
                is_folder = values[2] == "Папка"
                filepath = os.path.join(self.current_local_dir, filename)

                try:
                    if is_folder:
                        with self.ftp_lock:
                            self.upload_folder(filepath, filename)
                        continue

                    file_size = os.path.getsize(filepath)
                    buffer_size = self._get_optimal_buffer_size(file_size)
                    bytes_sent = 0

                    with self.ftp_lock:
                        with open(filepath, 'rb') as f:
                            def callback(block):
                                nonlocal bytes_sent
                                bytes_sent += len(block)
                                progress = ((i + (bytes_sent / file_size)) / total) * 100
                                self.schedule_update(lambda: [
                                    self.progress.config(value=progress),
                                    self.progress_label.config(text=f"Загрузка {filename}: {bytes_sent}/{file_size} байт")
                                ])
                                return block  # Важно вернуть блок данных!

                            try:
                                self.ftp.storbinary(f'STOR {filename}', f, buffer_size, callback)
                                
                                # Проверяем размер загруженного файла
                                uploaded_size = self.ftp.size(filename)
                                if uploaded_size != file_size:
                                    raise Exception(f"Ошибка загрузки: размер файла не совпадает (локальный: {file_size}, загружено: {uploaded_size})")
                                
                                success += 1
                                self.schedule_update(lambda f=filename: 
                                    self.progress_label.config(text=f"Загружен файл: {f}"))
                            except Exception as e:
                                # В случае ошибки пытаемся удалить частично загруженный файл
                                try:
                                    self.ftp.delete(filename)
                                except:
                                    pass
                                raise e

                except Exception as ex:
                    errors.append(f"{filename}: {str(ex)}")
                    self.schedule_update(lambda f=filename, e=ex:
                        self.update_status(f"Ошибка загрузки {f}: {e}", error=True))

            # Обновляем список файлов только если были успешные загрузки
            if success > 0:
                self.schedule_update(self.refresh_remote_list)

            self.schedule_update(lambda: [
                self.progress.config(value=100),
                messagebox.showinfo("Готово", 
                    f"Успешно загружено {success}/{total} файлов" +
                    (f"\nОшибки:\n" + "\n".join(errors) if errors else ""))
            ])

        self.task_queue.put(upload_task)

    def upload_folder(self, local_path, remote_folder):
        """Рекурсивная загрузка папки на сервер"""
        try:
            self.ftp.mkd(remote_folder)
        except:
            pass  # Папка может уже существовать
        
        # Сохраняем текущую удаленную директорию
        current_remote = self.ftp.pwd()
        
        try:
            # Переходим в созданную папку
            self.ftp.cwd(remote_folder)
            
            # Загружаем содержимое папки
            for item in os.listdir(local_path):
                local_item_path = os.path.join(local_path, item)
                
                if os.path.isfile(local_item_path):
                    # Загружаем файл
                    file_size = os.path.getsize(local_item_path)
                    buffer_size = self._get_optimal_buffer_size(file_size)
                    bytes_sent = 0

                    with open(local_item_path, 'rb') as f:
                        def callback(block):
                            nonlocal bytes_sent
                            bytes_sent += len(block)
                            return block  # Важно вернуть блок данных!

                        self.ftp.storbinary(f'STOR {item}', f, buffer_size, callback)
                        
                        # Проверяем размер загруженного файла
                        uploaded_size = self.ftp.size(item)
                        if uploaded_size != file_size:
                            raise Exception(f"Ошибка загрузки: размер файла не совпадает (локальный: {file_size}, загружено: {uploaded_size})")

                elif os.path.isdir(local_item_path):
                    # Рекурсивно загружаем вложенную папку
                    self.upload_folder(local_item_path, item)
        finally:
            # Всегда возвращаемся в исходную директорию
            self.ftp.cwd(current_remote)

    def handle_connection_loss(self):
        """Обработка потери соединения"""
        self.update_status_indicator(False)
        messagebox.showwarning("Соединение", "Связь с сервером потеряна")
        self.disconnect()

    def disconnect(self):
        """Модифицированный метод отключения"""
        self.monitor_running = False

        def disconnect_task():
            with self.ftp_lock:
                if self.ftp:
                    try:
                        self.ftp.quit()
                    except:
                        pass
                    finally:
                        self.ftp = None
                        # Очищаем удаленное дерево
                        self.schedule_update(lambda: [
                            self.remote_tree.delete(*self.remote_tree.get_children()),
                            self.remote_path_var.set("Удалённая: не подключено"),
                            self.connect_btn.config(text="Подключиться", command=self.connect),
                            self.update_status_indicator(False)
                        ])

        self.task_queue.put(disconnect_task)

    def refresh_lists(self):
        """Обновление списков файлов"""
        self.refresh_local_list()
        if self.ftp: self.refresh_remote_list()

    def refresh_local_list(self):
        """Обновление локальных файлов"""

        def refresh_task():
            try:
                items = []
                for item in os.listdir(self.current_local_dir):
                    path = os.path.join(self.current_local_dir, item)
                    stat = os.stat(path)
                    size = humanize.naturalsize(stat.st_size) if os.path.isfile(path) else ""
                    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    items.append((item, size, "Папка" if os.path.isdir(path) else "Файл", modified))

                # Применяем сортировку и фильтрацию
                items = self.filter_hidden_files(items)
                items = self.sort_items(items)

                def update_gui():
                    self.local_tree.delete(*self.local_tree.get_children())
                    for item in items:
                        self.local_tree.insert("", tk.END, values=item)
                    self.local_path_var.set(f"Локальная: {self.current_local_dir}")

                self.root.after(0, update_gui)
            except Exception as e:
                def show_error():
                    messagebox.showerror("Ошибка", f"Ошибка обновления: {str(e)}")
                self.root.after(0, show_error)

        self.task_queue.put(refresh_task)

    def refresh_remote_list(self):
        """Обновление удаленных файлов с использованием кэша"""
        def refresh_task():
            try:
                with self.ftp_lock:
                    if not self.ftp:
                        return

                    cached_list = self.get_cached_remote_list()
                    if cached_list:
                        self.schedule_update(lambda: self.update_remote_tree(cached_list))
                        return

                    files = []
                    self.ftp.retrlines('LIST', files.append)
                    parsed = []
                    for line in files:
                        parts = line.split()
                        if len(parts) < 9: continue
                        name = ' '.join(parts[8:])
                        size = humanize.naturalsize(int(parts[4])) if parts[0].startswith('-') else ""
                        file_type = "Папка" if parts[0].startswith('d') else "Файл"
                        modified = ' '.join(parts[5:8])
                        
                        parsed.append((name, size, file_type, modified))
                    
                    # Сохраняем в кэш
                    self.remote_cache[self.ftp.pwd()] = (time.time(), parsed)
                    
                    # Планируем обновление интерфейса
                    self.schedule_update(lambda: self.update_remote_tree(parsed))

            except Exception as e:
                error_msg = str(e)
                self.schedule_update(lambda: [
                    messagebox.showerror("Ошибка", f"Ошибка обновления: {error_msg}"),
                    self.update_status(f"Ошибка: {error_msg}", error=True)
                ])

        self.task_queue.put(refresh_task)

    def update_remote_tree(self, items):
        """Обновление удаленного дерева файлов"""
        try:
            self.remote_tree.delete(*self.remote_tree.get_children())
            for item in items:
                self.remote_tree.insert("", tk.END, values=item)
            
            # Безопасное обновление пути
            if self.ftp:
                try:
                    with self.ftp_lock:
                        current_path = self.ftp.pwd()
                    self.remote_path_var.set(f"Удалённая: {current_path}")
                except:
                    self.remote_path_var.set("Удалённая: Ошибка получения пути")
            else:
                self.remote_path_var.set("Удалённая: не подключено")
        except Exception as e:
            self.update_status(f"Ошибка обновления интерфейса: {str(e)}", error=True)

    def download_files(self):
        """Скачивание файлов"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файлы для скачивания")
            return

        def download_task():
            total = len(selected)
            success = 0
            errors = []

            for i, item_id in enumerate(selected):
                filename = self.remote_tree.item(item_id, 'values')[0]
                dest = os.path.join(self.current_local_dir, filename)
                
                try:
                    # Получаем размер файла для оптимизации буфера
                    with self.ftp_lock:
                        try:
                            file_size = self.ftp.size(filename)
                        except:
                            file_size = 1024 * 1024  # Если не удалось получить размер, предполагаем 1MB

                    buffer_size = self._get_optimal_buffer_size(file_size)

                    with self.ftp_lock, open(dest, 'wb') as f:
                        bytes_received = 0
                        
                        def callback(data):
                            nonlocal bytes_received
                            f.write(data)
                            bytes_received += len(data)
                            progress = ((i + (bytes_received / file_size)) / total) * 100
                            self.schedule_update(lambda: self.progress.config(value=progress))

                        self.ftp.retrbinary(f"RETR {filename}", callback, buffer_size)
                    success += 1
                    self.schedule_update(lambda f=filename: 
                        self.progress_label.config(text=f"Скачан файл: {f}"))
                except Exception as ex:
                    if os.path.exists(dest):
                        try:
                            os.remove(dest)  # Удаляем частично скачанный файл
                        except:
                            pass
                    errors.append(f"{filename}: {str(ex)}")
                    self.schedule_update(lambda f=filename, e=ex:
                        self.update_status(f"Ошибка скачивания {f}: {e}", error=True))

            self.schedule_update(lambda: [
                self.progress.config(value=100),
                self.refresh_local_list(),
                messagebox.showinfo("Готово", 
                    f"Успешно скачано {success}/{total} файлов" +
                    (f"\nОшибки:\n" + "\n".join(errors) if errors else ""))
            ])

        self.task_queue.put(download_task)

    def delete_selected(self):
        """Удаление файлов"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_tree.selection()
        if not selected: return

        if not messagebox.askyesno("Подтверждение", f"Удалить {len(selected)} файлов?"): return

        def delete_task():
            total = len(selected)
            success = 0
            errors = []
            
            try:
                for i, item_id in enumerate(selected):
                    if not self.ftp:
                        raise Exception("Соединение потеряно")
                    
                    filename = self.remote_tree.item(item_id, 'values')[0]
                    try:
                        with self.ftp_lock:
                            is_dir = False
                            try:
                                self.ftp.cwd(filename)
                                self.ftp.cwd('..')
                                is_dir = True
                            except:
                                pass

                            if is_dir:
                                self.ftp.rmd(filename)
                            else:
                                self.ftp.delete(filename)
                            success += 1
                    except Exception as e:
                        errors.append(f"{filename}: {str(e)}")
                        
                # Обновляем список файлов только если были успешные удаления
                if success > 0:
                    try:
                        with self.ftp_lock:
                            files = []
                            self.ftp.retrlines('LIST', files.append)
                            parsed = []
                            for line in files:
                                parts = line.split()
                                if len(parts) < 9: continue
                                name = ' '.join(parts[8:])
                                size = humanize.naturalsize(int(parts[4])) if parts[0].startswith('-') else ""
                                file_type = "Папка" if parts[0].startswith('d') else "Файл"
                                modified = ' '.join(parts[5:8])
                                parsed.append((name, size, file_type, modified))
                            
                            self.schedule_update(lambda: self.update_remote_tree(parsed))
                    except Exception as e:
                        errors.append(f"Ошибка обновления списка: {str(e)}")
                
                # Показываем результат операции
                self.schedule_update(lambda: [
                    self.progress.config(value=100),
                    messagebox.showinfo("Готово", 
                        f"Удалено {success}/{total} файлов" +
                        (f"\nОшибки:\n" + "\n".join(errors) if errors else "")),
                ])
                
            except Exception as e:
                self.schedule_update(lambda: [
                    messagebox.showerror("Ошибка", f"Критическая ошибка: {str(e)}"),
                    self.update_status("Ошибка удаления файлов", error=True)
                ])

        self.task_queue.put(delete_task)

    def create_remote_dir(self):
        """Создание папки на сервере"""
        if not self.ftp: return
        dirname = simpledialog.askstring("Создать папку", "Введите имя папки:")
        if not dirname: return

        def create_task():
            try:
                self.ftp.mkd(dirname)
                self.root.after(0, lambda: [
                    self.refresh_remote_list(),
                    messagebox.showinfo("Успех", f"Папка '{dirname}' создана")
                ])
            except Exception as e:
                error_msg = str(e)  # Сохраняем сообщение об ошибке в переменную
                self.root.after(0, lambda msg=error_msg: [  # Передаем сообщение как параметр лямбды
                    messagebox.showerror("Ошибка", f"Ошибка создания: {msg}"),
                    self.update_status(f"Ошибка: {msg}", error=True)
                ])

        self.task_queue.put(create_task)

    def update_status(self, message, error=False):
        """Обновление статуса"""
        self.progress_label.config(
            text=message,
            foreground="red" if error else "black"
        )

    def navigate_up(self):
        if self.ftp:
            self.task_queue.put(lambda: [
                self.ftp.cwd('..'),
                self.refresh_remote_list()
            ])

    def on_local_double_click(self, event):
        item = self.local_tree.selection()[0]
        name = self.local_tree.item(item, 'values')[0]
        path = os.path.join(self.current_local_dir, name)
        if os.path.isdir(path):
            self.current_local_dir = path
            self.refresh_local_list()

    def on_remote_double_click(self, event):
        item = self.remote_tree.selection()[0]
        name = self.remote_tree.item(item, 'values')[0]
        self.task_queue.put(lambda: [
            self.ftp.cwd(name),
            self.refresh_remote_list()
        ])

    def show_local_menu(self, event):
        item = self.local_tree.identify_row(event.y)
        if item:
            self.local_tree.selection_set(item)
            self.local_menu.post(event.x_root, event.y_root)

    def show_remote_menu(self, event):
        item = self.remote_tree.identify_row(event.y)
        if item:
            self.remote_tree.selection_set(item)
            self.remote_menu.post(event.x_root, event.y_root)

    def __del__(self):
        self.running = False
        self.task_queue.put(None)
        if self.ftp:
            try:
                self.ftp.quit()
            except:
                pass

    def sync_folders(self):
        """Синхронизация локальной и удаленной директорий"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Синхронизация")
        dialog.geometry("400x170")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Делаем окно модальным и располагаем по центру
        dialog.geometry("+%d+%d" % (
            self.root.winfo_rootx() + self.root.winfo_width()//2 - 200,
            self.root.winfo_rooty() + self.root.winfo_height()//2 - 75
        ))

        ttk.Label(dialog, text="Выберите направление синхронизации:",
                 wraplength=380, justify="center").pack(pady=10)

        self.sync_cancelled = False
        
        def start_sync(direction):
            dialog.destroy()
            self.do_sync(direction)
            
        def cancel():
            self.sync_cancelled = True
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        # Кнопка 1 - заполняет по ширине
        ttk.Button(btn_frame, text="1. Локальные → Удаленные",
                   command=lambda: start_sync("to_remote")).pack(fill=tk.X, padx=5, pady=2)

        # Кнопка 2 - заполняет по ширине
        ttk.Button(btn_frame, text="2. Удаленные → Локальные",
                   command=lambda: start_sync("to_local")).pack(fill=tk.X, padx=5, pady=2)

        # Кнопка Отмена - заполняет по ширине
        ttk.Button(btn_frame, text="Отмена",
                   command=cancel).pack(fill=tk.X, padx=5, pady=2)

    def do_sync(self, direction):
        """Выполнение синхронизации"""
        def sync_task():
            try:
                if direction == "to_remote":  # Локальная → Удаленная
                    self.sync_to_remote()
                else:  # Удаленная → Локальная
                    self.sync_to_local()
            except Exception as e:
                self.root.after(0, lambda: [
                    messagebox.showerror("Ошибка", f"Ошибка синхронизации: {str(e)}"),
                    self.update_status(f"Ошибка синхронизации", error=True)
                ])

        self.task_queue.put(sync_task)

    def sync_to_remote(self):
        """Синхронизация с локальной на удаленную с использованием пула потоков"""
        local_items = self.get_local_files()
        total_items = len(local_items)
        processed = 0
        errors = []

        def sync_item(item_data):
            item, index = item_data
            name, _, type_, _ = item
            local_path = os.path.join(self.current_local_dir, name)
            
            try:
                if type_ == "Папка":
                    with self.ftp_lock:
                        try:
                            self.ftp.mkd(name)
                        except error_perm:
                            pass  # Папка может уже существовать

                        current_remote = self.ftp.pwd()
                        self.ftp.cwd(name)
                        
                        # Собираем все файлы в папке для параллельной обработки
                        folder_items = []
                        for root, dirs, files in os.walk(local_path):
                            rel_path = os.path.relpath(root, local_path)
                            for file in files:
                                folder_items.append((rel_path, file))
                        
                        # Параллельно загружаем файлы
                        with ThreadPoolExecutor(max_workers=5) as inner_executor:
                            futures = []
                            for rel_path, file in folder_items:
                                futures.append(inner_executor.submit(
                                    self._upload_file_in_folder,
                                    current_remote, name, rel_path, file,
                                    os.path.join(root, file)
                                ))
                            
                            # Собираем ошибки
                            for future in as_completed(futures):
                                error = future.result()
                                if error:
                                    errors.append(error)
                        
                        self.ftp.cwd(current_remote)
                else:
                    # Загружаем файл
                    file_size = os.path.getsize(local_path)
                    buffer_size = self._get_optimal_buffer_size(file_size)
                    
                    with self.ftp_lock, open(local_path, 'rb') as f:
                        self.ftp.storbinary(f'STOR {name}', f, buffer_size)
                
                return True, name
            except Exception as e:
                return False, f"{name}: {str(e)}"

        def _upload_file_in_folder(self, base_remote, base_folder, rel_path, filename, filepath):
            try:
                with self.ftp_lock:
                    # Переходим в нужную директорию
                    self.ftp.cwd(f"{base_remote}/{base_folder}")
                    if rel_path != '.':
                        for part in rel_path.split(os.sep):
                            try:
                                self.ftp.mkd(part)
                            except error_perm:
                                pass
                            self.ftp.cwd(part)
                    
                    # Загружаем файл
                    file_size = os.path.getsize(filepath)
                    buffer_size = self._get_optimal_buffer_size(file_size)
                    with open(filepath, 'rb') as f:
                        self.ftp.storbinary(f'STOR {filename}', f, buffer_size)
                    return None
            except Exception as e:
                return f"{os.path.join(rel_path, filename)}: {str(e)}"
            finally:
                # Возвращаемся в исходную директорию
                with self.ftp_lock:
                    self.ftp.cwd(base_remote)

        def _get_optimal_buffer_size(self, file_size):
            """Определение оптимального размера буфера на основе размера файла"""
            if file_size < 1024 * 1024:  # < 1MB
                return 8192
            elif file_size < 10 * 1024 * 1024:  # < 10MB
                return 32768
            else:  # >= 10MB
                return 65536

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i, item in enumerate(local_items):
                if self.sync_cancelled:
                    self.update_status("Синхронизация отменена")
                    return
                futures.append(executor.submit(sync_item, (item, i)))
            
            for future in as_completed(futures):
                if self.sync_cancelled:
                    self.update_status("Синхронизация отменена")
                    return
                
                result, data = future.result()
                processed += 1
                
                if result:
                    self.root.after(0, lambda n=data, p=processed, t=total_items: [
                        self.progress_label.config(text=f"Синхронизация {p}/{t}: {n}"),
                        self.progress.config(value=(p/t) * 100)
                    ])
                else:
                    errors.append(data)

        if not self.sync_cancelled:
            self.root.after(0, lambda: [
                self.progress.config(value=100),
                messagebox.showinfo("Готово", 
                    f"Синхронизация завершена\nОбработано: {processed}/{total_items}" +
                    (f"\nОшибки:\n" + "\n".join(errors) if errors else "")),
                self.refresh_remote_list()
            ])

    def sync_to_local(self):
        """Синхронизация с удаленной на локальную с использованием пула потоков"""
        remote_items = self.get_remote_files()
        total_items = len(remote_items)
        processed = 0
        errors = []

        def sync_item(item_data):
            item, index = item_data
            name, _, type_, _ = item
            local_path = os.path.join(self.current_local_dir, name)
            
            try:
                if type_ == "Папка":
                    os.makedirs(local_path, exist_ok=True)
                    
                    with self.ftp_lock:
                        try:
                            current_remote = self.ftp.pwd()
                            self.ftp.cwd(name)
                            
                            # Получаем список всех файлов в папке
                            folder_items = []
                            self.ftp.retrlines('LIST', folder_items.append)
                            
                            # Парсим и собираем информацию о файлах
                            files_to_download = []
                            for item_info in folder_items:
                                parts = item_info.split()
                                if len(parts) < 9:
                                    continue

                                item_name = ' '.join(parts[8:])
                                is_dir = parts[0].startswith('d')
                                
                                if not is_dir:
                                    files_to_download.append((item_name, local_path))
                                else:
                                    subdir_path = os.path.join(local_path, item_name)
                                    os.makedirs(subdir_path, exist_ok=True)
                            
                            # Возвращаемся в исходную директорию
                            self.ftp.cwd(current_remote)
                            
                            # Параллельно скачиваем файлы
                            with ThreadPoolExecutor(max_workers=5) as inner_executor:
                                futures = []
                                for file_name, file_path in files_to_download:
                                    futures.append(inner_executor.submit(
                                        self._download_file_in_folder,
                                        current_remote, name, file_name, file_path
                                    ))
                                
                                # Собираем ошибки
                                for future in as_completed(futures):
                                    error = future.result()
                                    if error:
                                        errors.append(error)
                        except Exception as e:
                            errors.append(f"{name}: {str(e)}")
                            if 'current_remote' in locals():
                                try:
                                    self.ftp.cwd(current_remote)
                                except:
                                    pass
                else:
                    # Скачиваем файл
                    with self.ftp_lock:
                        try:
                            file_size = self.ftp.size(name)
                        except:
                            file_size = 1024 * 1024  # Предполагаем 1MB если не удалось получить размер
                    
                        buffer_size = self._get_optimal_buffer_size(file_size)
                        
                        try:
                            with self.ftp_lock, open(local_path, 'wb') as f:
                                self.ftp.retrbinary(f'RETR {name}', f.write, buffer_size)
                        except Exception as e:
                            if os.path.exists(local_path):
                                try:
                                    os.remove(local_path)
                                except:
                                    pass
                            raise e
                    
                    return True, name
            except Exception as e:
                return False, f"{name}: {str(e)}"

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i, item in enumerate(remote_items):
                if self.sync_cancelled:
                    self.update_status("Синхронизация отменена")
                    return
                futures.append(executor.submit(sync_item, (item, i)))
            
            for future in as_completed(futures):
                if self.sync_cancelled:
                    self.update_status("Синхронизация отменена")
                    return
                
                result, data = future.result()
                processed += 1
                
                if result:
                    self.root.after(0, lambda n=data, p=processed, t=total_items: [
                        self.progress_label.config(text=f"Синхронизация {p}/{t}: {n}"),
                        self.progress.config(value=(p/t) * 100)
                    ])
                else:
                    errors.append(data)

        if not self.sync_cancelled:
            self.root.after(0, lambda: [
                self.progress.config(value=100),
                messagebox.showinfo("Готово", 
                    f"Синхронизация завершена\nОбработано: {processed}/{total_items}" +
                    (f"\nОшибки:\n" + "\n".join(errors) if errors else "")),
                self.refresh_local_list()
            ])

    def show_settings(self):
        """Окно настроек приложения"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Настройки")
        settings_window.geometry("600x500")
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Создаем notebook для вкладок
        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Вкладка общих настроек
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="Общие")

        # Локальная директория по умолчанию
        dir_frame = ttk.LabelFrame(general_frame, text="Директории")
        dir_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(dir_frame, text="Локальная директория:").pack(anchor="w", padx=5, pady=2)
        local_dir_frame = ttk.Frame(dir_frame)
        local_dir_frame.pack(fill=tk.X, padx=5, pady=2)
        
        local_dir_entry = ttk.Entry(local_dir_frame)
        local_dir_entry.insert(0, self.settings['default_local_dir'])
        local_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(local_dir_frame, text="Обзор", 
                  command=lambda: self.choose_directory(local_dir_entry)).pack(side=tk.LEFT, padx=2)

        # Настройки подключения
        connection_frame = ttk.LabelFrame(general_frame, text="Подключение")
        connection_frame.pack(fill=tk.X, padx=5, pady=5)

        auto_reconnect_var = tk.BooleanVar(value=self.settings['auto_reconnect'])
        ttk.Checkbutton(connection_frame, text="Автоматическое переподключение",
                       variable=auto_reconnect_var).pack(anchor="w", padx=5, pady=2)

        reconnect_frame = ttk.Frame(connection_frame)
        reconnect_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(reconnect_frame, text="Количество попыток:").pack(side=tk.LEFT)
        reconnect_attempts = ttk.Spinbox(reconnect_frame, from_=1, to=10, width=5)
        reconnect_attempts.set(self.settings['reconnect_attempts'])
        reconnect_attempts.pack(side=tk.LEFT, padx=5)

        # Настройки интерфейса
        interface_frame = ttk.LabelFrame(general_frame, text="Интерфейс")
        interface_frame.pack(fill=tk.X, padx=5, pady=5)

        sort_folders_var = tk.BooleanVar(value=self.settings['sort_folders_first'])
        ttk.Checkbutton(interface_frame, text="Показывать папки первыми",
                       variable=sort_folders_var).pack(anchor="w", padx=5, pady=2)

        show_hidden_var = tk.BooleanVar(value=self.settings['show_hidden_files'])
        ttk.Checkbutton(interface_frame, text="Показывать скрытые файлы",
                       variable=show_hidden_var).pack(anchor="w", padx=5, pady=2)

        # Вкладка подтверждений
        confirm_frame = ttk.Frame(notebook)
        notebook.add(confirm_frame, text="Подтверждения")

        confirm_delete_var = tk.BooleanVar(value=self.settings['confirm_delete'])
        ttk.Checkbutton(confirm_frame, text="Подтверждать удаление",
                       variable=confirm_delete_var).pack(anchor="w", padx=5, pady=2)

        confirm_overwrite_var = tk.BooleanVar(value=self.settings['confirm_overwrite'])
        ttk.Checkbutton(confirm_frame, text="Подтверждать перезапись",
                       variable=confirm_overwrite_var).pack(anchor="w", padx=5, pady=2)

        # Вкладка производительности
        performance_frame = ttk.Frame(notebook)
        notebook.add(performance_frame, text="Производительность")

        ttk.Label(performance_frame, text="Размер буфера (байт):").pack(anchor="w", padx=5, pady=2)
        buffer_size = ttk.Entry(performance_frame)
        buffer_size.insert(0, str(self.settings['buffer_size']))
        buffer_size.pack(anchor="w", padx=5, pady=2)

        ttk.Label(performance_frame, text="Время жизни кэша (сек):").pack(anchor="w", padx=5, pady=2)
        cache_ttl = ttk.Entry(performance_frame)
        cache_ttl.insert(0, str(self.settings['cache_ttl']))
        cache_ttl.pack(anchor="w", padx=5, pady=2)

        # Кнопки
        btn_frame = ttk.Frame(settings_window)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Сохранить", command=lambda: self.save_settings({
            'default_local_dir': local_dir_entry.get(),
            'buffer_size': int(buffer_size.get()),
            'auto_reconnect': auto_reconnect_var.get(),
            'reconnect_attempts': int(reconnect_attempts.get()),
            'cache_ttl': int(cache_ttl.get()),
            'show_hidden_files': show_hidden_var.get(),
            'confirm_delete': confirm_delete_var.get(),
            'confirm_overwrite': confirm_overwrite_var.get(),
            'sort_folders_first': sort_folders_var.get(),
            'date_format': self.settings['date_format']
        }, settings_window)).pack(side=tk.RIGHT, padx=5)

        ttk.Button(btn_frame, text="Отмена",
                  command=settings_window.destroy).pack(side=tk.RIGHT, padx=5)

    def choose_directory(self, entry):
        """Выбор директории через диалог"""
        directory = filedialog.askdirectory(initialdir=entry.get())
        if directory:
            entry.delete(0, tk.END)
            entry.insert(0, directory)

    def save_settings(self, new_settings, window):
        """Сохранение настроек"""
        try:
            self.settings.update(new_settings)
            with open(os.path.join(os.path.expanduser("~"), ".ftp_client_settings.json"), 'w') as f:
                json.dump(self.settings, f)
            
            # Применяем некоторые настройки сразу
            self.current_local_dir = self.settings['default_local_dir']
            
            # Обновляем интерфейс
            self.refresh_lists()
            
            messagebox.showinfo("Успех", "Настройки сохранены")
            window.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {str(e)}")

    def load_settings(self):
        """Загрузка настроек"""
        try:
            settings_file = os.path.join(os.path.expanduser("~"), ".ftp_client_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    saved_settings = json.load(f)
                    self.settings.update(saved_settings)
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")

    def get_cached_remote_list(self):
        """Получение кэшированного списка удаленных файлов"""
        current_path = self.ftp.pwd()
        current_time = time.time()
        
        if (current_path in self.remote_cache and 
            current_time - self.remote_cache[current_path][0] < self.settings['cache_ttl']):
            return self.remote_cache[current_path][1]
            
        return None

    def create_search_bar(self):
        """Создание улучшенной панели поиска"""
        search_frame = ttk.LabelFrame(self.root, text="Поиск файлов")
        search_frame.pack(fill=tk.X, padx=5, pady=2)

        # Поле ввода для поиска
        input_frame = ttk.Frame(search_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=2)

        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_change)
        
        self.search_entry = ttk.Entry(input_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Кнопка очистки поиска
        ttk.Button(input_frame, text="✕", width=3,
                  command=self.clear_search).pack(side=tk.LEFT, padx=2)

        # Опции поиска
        options_frame = ttk.Frame(search_frame)
        options_frame.pack(fill=tk.X, padx=5, pady=2)

        # Переключатели области поиска
        self.search_scope = tk.StringVar(value="both")
        ttk.Radiobutton(options_frame, text="Локальные", 
                       variable=self.search_scope, 
                       value="local",
                       command=self.on_search_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(options_frame, text="Удаленные", 
                       variable=self.search_scope, 
                       value="remote",
                       command=self.on_search_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(options_frame, text="Везде", 
                       variable=self.search_scope, 
                       value="both",
                       command=self.on_search_change).pack(side=tk.LEFT, padx=5)

        # Дополнительные опции поиска
        self.case_sensitive = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Учитывать регистр",
                       variable=self.case_sensitive,
                       command=self.on_search_change).pack(side=tk.LEFT, padx=5)

        self.search_in_folders = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Искать в папках",
                       variable=self.search_in_folders,
                       command=self.on_search_change).pack(side=tk.LEFT, padx=5)

    def clear_search(self):
        """Очистка поиска"""
        self.search_var.set("")
        self.refresh_lists()

    def filter_items(self, items, search_text):
        """Фильтрация элементов по критериям поиска"""
        filtered = []
        if not search_text:
            return items

        for item in items:
            name = item[0]
            is_folder = item[2] == "Папка"

            # Проверяем соответствие поисковому запросу
            if not self.case_sensitive.get():
                name = name.lower()
                search_text = search_text.lower()

            # Всегда ищем и в файлах, и в папках
            if search_text in name:
                filtered.append(item)
            # Если это папка и опция поиска в папках включена,
            # добавляем её даже если она не соответствует поиску
            elif is_folder and self.search_in_folders.get():
                filtered.append(item)

        return filtered

    def get_local_files(self):
        """Получение списка локальных файлов"""
        items = []
        try:
            for item in os.listdir(self.current_local_dir):
                path = os.path.join(self.current_local_dir, item)
                try:
                    stat = os.stat(path)
                    is_dir = os.path.isdir(path)
                    # Для файлов показываем размер, для папок - количество элементов внутри
                    if is_dir:
                        try:
                            size = f"{len(os.listdir(path))} элем."
                        except:
                            size = "Нет доступа"
                    else:
                        size = humanize.naturalsize(stat.st_size)
                    
                    # Преобразуем время в локальное
                    local_time = datetime.fromtimestamp(stat.st_mtime)
                    modified = local_time.strftime(self.settings['date_format'])
                    
                    items.append((item, size, "Папка" if is_dir else "Файл", modified))
                except Exception as e:
                    # Если не удалось получить информацию о файле, все равно добавляем его
                    items.append((item, "Ошибка", "Неизвестно", ""))
        except Exception as e:
            self.update_status(f"Ошибка чтения локальной директории: {e}", error=True)
        return items

    def parse_ftp_time(self, time_str):
        """Парсинг времени из FTP-листинга"""
        try:
            # Текущий год
            current_year = datetime.now().year
            
            # Разбираем строку времени
            months = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }
            
            parts = time_str.split()
            if len(parts) != 3:
                return time_str
                
            month = months.get(parts[0], 1)
            day = int(parts[1])
            
            # Парсим время или год
            if ':' in parts[2]:  # Если указано время
                hour, minute = map(int, parts[2].split(':'))
                # Для файлов с временем используем текущий год
                year = current_year
                # Если получившаяся дата в будущем, используем прошлый год
                dt = datetime(year, month, day, hour, minute)
                if dt > datetime.now():
                    dt = datetime(year - 1, month, day, hour, minute)
            else:  # Если указан год
                year = int(parts[2])
                dt = datetime(year, month, day)
            
            # Преобразуем в локальное время
            return dt.strftime(self.settings['date_format'])
        except Exception:
            return time_str

    def get_remote_files(self):
        """Получение списка удаленных файлов"""
        items = []
        if not self.ftp:
            return items

        try:
            with self.ftp_lock:
                files = []
                self.ftp.retrlines('LIST', files.append)
                
                # Сначала собираем базовую информацию
                for line in files:
                    try:
                        parts = line.split()
                        if len(parts) < 9:
                            continue
                        name = ' '.join(parts[8:])
                        is_dir = parts[0].startswith('d')
                        
                        # Для файлов показываем размер
                        if not is_dir:
                            try:
                                size = humanize.naturalsize(int(parts[4]))
                            except:
                                size = parts[4]
                        else:
                            # Для папок подсчитываем количество элементов
                            try:
                                current_dir = self.ftp.pwd()
                                self.ftp.cwd(name)
                                dir_files = []
                                self.ftp.retrlines('LIST', dir_files.append)
                                size = f"{len(dir_files)} элем."
                                self.ftp.cwd(current_dir)
                            except:
                                size = "Нет доступа"
                        
                        # Парсим время модификации
                        time_str = ' '.join(parts[5:8])
                        modified = self.parse_ftp_time(time_str)
                        
                        items.append((name, size, "Папка" if is_dir else "Файл", modified))
                    except Exception as e:
                        # Если не удалось разобрать строку, пропускаем её
                        continue
        except Exception as e:
            self.update_status(f"Ошибка чтения удаленной директории: {e}", error=True)
        return items

    def on_search_change(self, *args):
        """Обработка изменения в поле поиска"""
        search_text = self.search_var.get()
        scope = self.search_scope.get()

        # Обновляем локальное дерево
        if scope in ["local", "both"]:
            items = self.get_local_files()
            filtered_items = self.filter_items(items, search_text)
            self.local_tree.delete(*self.local_tree.get_children())
            for item in filtered_items:
                self.local_tree.insert("", tk.END, values=item)

        # Обновляем удаленное дерево
        if scope in ["remote", "both"] and self.ftp:
            items = self.get_remote_files()
            filtered_items = self.filter_items(items, search_text)
            self.remote_tree.delete(*self.remote_tree.get_children())
            for item in filtered_items:
                self.remote_tree.insert("", tk.END, values=item)

        # Обновляем статус
        total_found = len(self.local_tree.get_children()) + len(self.remote_tree.get_children())
        if search_text:
            self.update_status(f"Найдено элементов: {total_found}")
        else:
            self.update_status("Готов")

    def setup_sorting(self):
        """Настройка сортировки по колонкам"""
        for tree in (self.local_tree, self.remote_tree):
            for col in ("name", "size", "type", "modified"):
                tree.heading(col, command=lambda c=col: self.sort_tree_column(tree, c))

    def sort_tree_column(self, tree, col):
        """Сортировка дерева по колонке"""
        items = [(tree.set(item, col), item) for item in tree.get_children('')]
        
        # Определяем направление сортировки
        if self.current_sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
        self.current_sort_column = col
        
        # Сортируем элементы
        items.sort(reverse=self.sort_reverse)
        for index, (_, item) in enumerate(items):
            tree.move(item, '', index)

    def load_connection_history(self) -> List[Dict]:
        """Загрузка истории подключений"""
        try:
            if os.path.exists(self.connection_history_file):
                with open(self.connection_history_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки истории: {e}")
        return []

    def save_connection_history(self):
        """Сохранение истории подключений"""
        try:
            with open(self.connection_history_file, 'w') as f:
                json.dump(self.connection_history, f)
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")

    def add_to_history(self, host: str, port: int, user: str):
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
        self.save_connection_history()

    def show_connection_history(self):
        """Показ окна истории подключений"""
        history_window = tk.Toplevel(self.root)
        history_window.title("История подключений")
        history_window.geometry("800x300")

        tree = ttk.Treeview(history_window, columns=("host", "port", "user", "date"), show="headings")
        tree.heading("host", text="Сервер")
        tree.heading("port", text="Порт")
        tree.heading("user", text="Пользователь")
        tree.heading("date", text="Дата")

        # Устанавливаем ширину колонок
        tree.column("host", width=250)
        tree.column("port", width=100)
        tree.column("user", width=200)
        tree.column("date", width=200)

        for conn in self.connection_history:
            date = datetime.fromisoformat(conn['timestamp']).strftime("%Y-%m-%d %H:%M")
            tree.insert("", tk.END, values=(
                conn['host'],
                conn['port'],
                conn['user'],
                date
            ))

        tree.bind("<Double-1>", lambda e: self.connect_from_history(tree))
        tree.pack(fill=tk.BOTH, expand=True)

    def connect_from_history(self, tree):
        """Подключение из истории"""
        selected = tree.selection()
        if not selected:
            return
            
        item = tree.item(selected[0])
        values = item['values']
        
        self.host_entry.delete(0, tk.END)
        self.host_entry.insert(0, values[0])
        
        self.port_entry.delete(0, tk.END)
        self.port_entry.insert(0, values[1])
        
        self.user_entry.delete(0, tk.END)
        self.user_entry.insert(0, values[2])
        
        self.connect()

    def setup_drag_and_drop(self):
        """Настройка drag-and-drop"""
        self.local_tree.bind("<ButtonPress-1>", self.on_drag_start)
        self.local_tree.bind("<B1-Motion>", self.on_drag_motion)
        self.local_tree.bind("<ButtonRelease-1>", self.on_drag_end)
        
        self.remote_tree.bind("<ButtonPress-1>", self.on_drag_start)
        self.remote_tree.bind("<B1-Motion>", self.on_drag_motion)
        self.remote_tree.bind("<ButtonRelease-1>", self.on_drag_end)

    def on_drag_start(self, event):
        """Начало перетаскивания"""
        tree = event.widget
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            self._drag_data = {'item': item, 'source': tree}

    def on_drag_motion(self, event):
        """Процесс перетаскивания"""
        pass  # Можно добавить визуальные эффекты

    def on_drag_end(self, event):
        """Окончание перетаскивания"""
        if hasattr(self, '_drag_data'):
            target = event.widget
            if target != self._drag_data['source']:
                # Перетаскивание между деревьями
                if target == self.remote_tree:
                    self.upload_files()
                else:
                    self.download_files()
            del self._drag_data

    def load_bookmarks(self) -> List[Dict]:
        """Загрузка закладок"""
        try:
            if os.path.exists(self.bookmarks_file):
                with open(self.bookmarks_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки закладок: {e}")
        return []

    def save_bookmarks(self):
        """Сохранение закладок"""
        try:
            with open(self.bookmarks_file, 'w') as f:
                json.dump(self.bookmarks, f)
        except Exception as e:
            print(f"Ошибка сохранения закладок: {e}")

    def _encrypt_password(self, password):
        """Простое шифрование пароля"""
        if not password:
            return ""
        try:
            # Простое XOR шифрование
            encrypted = ''.join(chr(ord(c) ^ ord(k)) for c, k in zip(password, self._key * (len(password) // len(self._key) + 1)))
            # Конвертируем в base64 для безопасного хранения
            return base64.b64encode(encrypted.encode()).decode()
        except:
            return ""

    def _decrypt_password(self, encrypted_password):
        """Расшифровка пароля"""
        if not encrypted_password:
            return ""
        try:
            # Декодируем из base64
            decoded = base64.b64decode(encrypted_password.encode()).decode()
            # Применяем XOR для расшифровки
            return ''.join(chr(ord(c) ^ ord(k)) for c, k in zip(decoded, self._key * (len(decoded) // len(self._key) + 1)))
        except:
            return ""

    def add_bookmark(self):
        """Добавление текущего сервера в закладки"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return
        
        name = simpledialog.askstring("Закладка", "Введите название закладки:")
        if name:
            # Шифруем пароль перед сохранением
            encrypted_password = self._encrypt_password(self.password_entry.get())
            
            bookmark = {
                'name': name,
                'host': self.host_entry.get(),
                'port': int(self.port_entry.get()),
                'user': self.user_entry.get(),
                'password': encrypted_password
            }
            self.bookmarks.append(bookmark)
            self.save_bookmarks()
            messagebox.showinfo("Успех", "Закладка добавлена")

    def show_bookmarks(self):
        """Показ окна закладок"""
        bookmarks_window = tk.Toplevel(self.root)
        bookmarks_window.title("Закладки")
        bookmarks_window.geometry("800x300")

        tree = ttk.Treeview(bookmarks_window, columns=("name", "host", "port", "user"), show="headings")
        tree.heading("name", text="Название")
        tree.heading("host", text="Сервер")
        tree.heading("port", text="Порт")
        tree.heading("user", text="Пользователь")

        # Устанавливаем ширину колонок
        tree.column("name", width=200)
        tree.column("host", width=250)
        tree.column("port", width=100)
        tree.column("user", width=200)

        for bookmark in self.bookmarks:
            tree.insert("", tk.END, values=(
                bookmark['name'],
                bookmark['host'],
                bookmark['port'],
                bookmark['user']
            ))

        # Добавляем кнопки управления закладками
        btn_frame = ttk.Frame(bookmarks_window)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Подключиться", 
                   command=lambda: self.connect_from_bookmark(tree)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Удалить", 
                   command=lambda: self.delete_bookmark(tree)).pack(side=tk.LEFT, padx=2)

        tree.pack(fill=tk.BOTH, expand=True)

    def connect_from_bookmark(self, tree):
        """Подключение из закладки"""
        selected = tree.selection()
        if not selected:
            return
            
        item = tree.item(selected[0])
        name = item['values'][0]  # Получаем название закладки
        
        # Ищем закладку по названию
        bookmark = next((b for b in self.bookmarks if b['name'] == name), None)
        if not bookmark:
            messagebox.showerror("Ошибка", "Закладка не найдена")
            return
        
        # Заполняем поля подключения
        self.host_entry.delete(0, tk.END)
        self.host_entry.insert(0, bookmark['host'])
        
        self.port_entry.delete(0, tk.END)
        self.port_entry.insert(0, str(bookmark['port']))
        
        self.user_entry.delete(0, tk.END)
        self.user_entry.insert(0, bookmark['user'])
        
        # Расшифровываем и устанавливаем пароль
        decrypted_password = self._decrypt_password(bookmark.get('password', ''))
        self.password_entry.delete(0, tk.END)
        self.password_entry.insert(0, decrypted_password)
        
        self.connect()

    def delete_bookmark(self, tree):
        """Удаление закладки"""
        selected = tree.selection()
        if not selected:
            return
            
        item = tree.item(selected[0])
        name = item['values'][0]
        
        if messagebox.askyesno("Подтверждение", f"Удалить закладку '{name}'?"):
            self.bookmarks = [b for b in self.bookmarks if b['name'] != name]
            self.save_bookmarks()
            tree.delete(selected)

    def load_saved_data(self):
        # Реализация загрузки сохраненных данных
        pass

    def toggle_password_visibility(self):
        """Переключение видимости пароля"""
        if self.show_password.get():
            self.password_entry.configure(show="*")
            self.show_password.set(False)
        else:
            self.password_entry.configure(show="")
            self.show_password.set(True)

    def create_local_dir(self):
        """Создание локальной папки"""
        dirname = simpledialog.askstring("Создать папку", "Введите имя папки:")
        if dirname:
            try:
                new_dir = os.path.join(self.current_local_dir, dirname)
                os.makedirs(new_dir, exist_ok=True)
                self.refresh_local_list()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать папку: {str(e)}")

    def open_local_file(self):
        """Открытие локального файла"""
        selected = self.local_tree.selection()
        if selected:
            filename = self.local_tree.item(selected[0], 'values')[0]
            full_path = os.path.join(self.current_local_dir, filename)
            if os.path.isfile(full_path):
                try:
                    import subprocess
                    import sys
                    if sys.platform == 'darwin':  # macOS
                        subprocess.run(['open', full_path])
                    elif sys.platform == 'win32':  # Windows
                        os.startfile(full_path)
                    else:  # Linux
                        subprocess.run(['xdg-open', full_path])
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось открыть файл: {str(e)}")

    def rename_local(self):
        """Переименование локального файла"""
        selected = self.local_tree.selection()
        if selected:
            old_name = self.local_tree.item(selected[0], 'values')[0]
            new_name = simpledialog.askstring(
                "Переименование",
                "Введите новое имя:",
                initialvalue=old_name
            )
            if new_name and new_name != old_name:
                try:
                    src = os.path.join(self.current_local_dir, old_name)
                    dst = os.path.join(self.current_local_dir, new_name)
                    os.rename(src, dst)
                    self.refresh_local_list()
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Ошибка переименования: {str(e)}")

    def delete_local(self):
        """Удаление локального файла"""
        selected = self.local_tree.selection()
        if selected:
            filename = self.local_tree.item(selected[0], 'values')[0]
            path = os.path.join(self.current_local_dir, filename)

            if not self.settings['confirm_delete'] or \
               messagebox.askyesno("Подтверждение", f"Удалить {filename}?"):
                try:
                    if os.path.isdir(path):
                        os.rmdir(path)
                    else:
                        os.remove(path)
                    self.refresh_local_list()
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось удалить: {str(e)}")

    def rename_remote(self):
        """Переименование файла/папки на сервере"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файл для переименования")
            return

        old_name = self.remote_tree.item(selected[0], 'values')[0]
        new_name = simpledialog.askstring(
            "Переименование",
            "Введите новое имя:",
            initialvalue=old_name
        )

        if new_name and new_name != old_name:
            try:
                self.ftp.rename(old_name, new_name)
                self.refresh_remote_list()
                messagebox.showinfo("Успех", "Файл успешно переименован")
            except error_perm as e:
                messagebox.showerror("Ошибка",
                                   f"Нет прав на переименование: {str(e)}")
            except Exception as e:
                messagebox.showerror("Ошибка",
                                   f"Ошибка переименования: {str(e)}")

    def delete_remote(self):
        """Удаление файла/папки на сервере"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файл для удаления")
            return

        filename = self.remote_tree.item(selected[0], 'values')[0]

        if not self.settings['confirm_delete'] or \
           messagebox.askyesno("Подтверждение", f"Удалить {filename}?"):
            try:
                # Проверяем, это файл или директория
                is_dir = False
                try:
                    self.ftp.cwd(filename)
                    is_dir = True
                    self.ftp.cwd('..')
                except:
                    pass

                if is_dir:
                    self.ftp.rmd(filename)
                else:
                    self.ftp.delete(filename)

                self.refresh_remote_list()
                messagebox.showinfo("Успех", "Файл успешно удален")

            except error_perm as e:
                messagebox.showerror("Ошибка", f"Нет прав на удаление: {str(e)}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка удаления: {str(e)}")

    def change_local_directory(self):
        """Изменение локальной директории"""
        new_dir = filedialog.askdirectory(initialdir=self.current_local_dir)
        if new_dir:
            self.current_local_dir = new_dir
            self.local_path_var.set(f"Локальная: {self.current_local_dir}")
            self.refresh_local_list()

    def sort_items(self, items):
        """Сортировка элементов с учетом настроек"""
        if self.settings['sort_folders_first']:
            # Разделяем папки и файлы
            folders = [item for item in items if item[2] == "Папка"]
            files = [item for item in items if item[2] == "Файл"]
            
            # Сортируем каждую группу отдельно
            folders.sort(key=lambda x: x[0].lower())  # Сортировка папок по имени
            files.sort(key=lambda x: x[0].lower())    # Сортировка файлов по имени
            
            # Объединяем списки
            return folders + files
        else:
            # Просто сортируем все элементы по имени
            return sorted(items, key=lambda x: x[0].lower())

    def filter_hidden_files(self, items):
        """Фильтрация скрытых файлов"""
        if not self.settings['show_hidden_files']:
            return [item for item in items if not item[0].startswith('.')]
        return items

    def _get_optimal_buffer_size(self, file_size):
        """Определение оптимального размера буфера на основе размера файла"""
        if file_size < 1024 * 1024:  # < 1MB
            return 8192
        elif file_size < 10 * 1024 * 1024:  # < 10MB
            return 32768
        else:  # >= 10MB
            return 65536

    def _download_file_in_folder(self, base_remote, base_folder, filename, local_path):
        """Скачивание файла из папки на FTP-сервере"""
        try:
            with self.ftp_lock:
                try:
                    # Переходим в нужную директорию
                    current_dir = self.ftp.pwd()
                    self.ftp.cwd(f"{base_remote}/{base_folder}")
                except Exception as e:
                    return f"Ошибка доступа к директории {base_folder}: {str(e)}"

                try:
                    # Пытаемся получить размер файла
                    try:
                        file_size = self.ftp.size(filename)
                    except:
                        file_size = 1024 * 1024  # По умолчанию 1MB если не удалось получить размер

                    buffer_size = self._get_optimal_buffer_size(file_size)
                    
                    # Создаем все необходимые директории
                    os.makedirs(os.path.dirname(os.path.join(local_path, filename)), exist_ok=True)
                    
                    # Скачиваем файл
                    with open(os.path.join(local_path, filename), 'wb') as f:
                        self.ftp.retrbinary(f'RETR {filename}', f.write, buffer_size)
                    
                    # Возвращаемся в исходную директорию
                    self.ftp.cwd(current_dir)
                    return None
                except Exception as e:
                    # В случае ошибки возвращаемся в исходную директорию
                    self.ftp.cwd(current_dir)
                    return f"Ошибка скачивания файла {filename}: {str(e)}"
        except Exception as e:
            return f"Критическая ошибка при скачивании {filename}: {str(e)}"

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPClientApp(root)
    root.mainloop()