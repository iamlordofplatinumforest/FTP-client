import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from ftplib import FTP, FTP_TLS, error_perm
import os
import socket
from threading import Thread, Lock
from queue import Queue
from datetime import datetime, time
import humanize
import json
import re
from typing import Dict, List, Tuple


class FTPClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced FTP Client")
        self.root.geometry("1100x750")

        self.ftp = None
        self.ftp_lock = Lock()
        self.current_remote_dir = "/"
        self.current_local_dir = os.path.expanduser("~/Downloads")

        self.remote_cache = {}
        self.local_cache = {}
        self.cache_ttl = 30
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
            ("Пароль:", "password_entry", "pass", "*")
        ]

        '''
        entries = [
            ("Сервер:", "host_entry", "ftp.gnu.org"),
            ("Пользователь:", "user_entry", "anonymous"),
            ("Пароль:", "password_entry", "user@example.com", "*")
        ]
        '''

        for i, (label, attr, default, *show) in enumerate(entries):
            ttk.Label(frame, text=label).grid(row=i, column=0, padx=5, pady=2, sticky="e")
            entry = ttk.Entry(frame)
            entry.insert(0, default)
            if show:
                entry.config(show=show[0])
            entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
            setattr(self, attr, entry)

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
            ("🔄 Синхр.", self.sync_folders),
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

    def connect(self):
        """Подключение к серверу"""
        host = self.host_entry.get()
        port = self.port_entry.get()
        user = self.user_entry.get()
        password = self.password_entry.get()
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный номер порта")
            return

        def connect_task():
            # Проверка доступности сервера
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                sock.close()
                if result != 0:
                    raise ConnectionError(f"Сервер {host}:{port} недоступен")
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
                return

            # Подключение FTP
            try:
                with self.ftp_lock:
                    if self.ftp:
                        self.ftp.quit()
                    self.ftp = FTP()
                    self.ftp.connect(host, port, timeout=10)
                    self.ftp.login(user=user, passwd=password)
                    self.monitor_running = True
                    self.start_connection_monitor()

                    self.root.after(0, lambda: [
                        self.update_status_indicator(True),
                        self.connect_btn.config(text="Отключиться", command=self.disconnect),
                        self.refresh_remote_list()
                    ])
            except Exception as e:
                self.root.after(0, lambda: [
                    messagebox.showerror("Ошибка", f"Ошибка подключения: {e}"),
                    self.update_status_indicator(False)
                ])

        self.task_queue.put(connect_task)

    def upload_files(self):
        """Загрузка файлов"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        files = filedialog.askopenfilenames(title="Выберите файлы для загрузки")
        if not files: return

        def upload_task():
            total = len(files)
            success = 0
            buffer_size = 8192  # Оптимальный размер буфера
            
            for i, filepath in enumerate(files):
                filename = os.path.basename(filepath)
                try:
                    self.root.after(0, lambda f=filename: [
                        self.progress_label.config(text=f"Загрузка {i + 1}/{total}: {f}"),
                        self.progress.config(value=(i / total) * 100)
                    ])
                    
                    # Буферизированное чтение файла
                    with open(filepath, 'rb') as f:
                        def callback(data):
                            f.seek(len(data), 1)
                            self.progress.config(
                                value=((i + (f.tell() / os.path.getsize(filepath))) / total) * 100
                            )
                        
                        self.ftp.storbinary(f"STOR {filename}", f, buffer_size, callback)
                    success += 1
                    
                except Exception as e:
                    self.root.after(0, lambda f=filename, eх=e: [
                        messagebox.showerror("Ошибка", f"Ошибка загрузки {f}: {eх}"),
                        self.update_status(f"Ошибка: {f}", error=True)
                    ])
                
            self.root.after(0, lambda: [
                self.progress.config(value=100),
                messagebox.showinfo("Готово", f"Успешно загружено {success}/{total} файлов"),
                self.refresh_remote_list()
            ])

        self.task_queue.put(upload_task)

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
            self.root.after(0, lambda: [
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

                self.root.after(0, lambda: (
                    self.local_tree.delete(*self.local_tree.get_children()),
                    [self.local_tree.insert("", tk.END, values=item) for item in items],
                    self.local_path_var.set(f"Локальная: {self.current_local_dir}")
                ))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка обновления: {e}"))

        self.task_queue.put(refresh_task)

    def refresh_remote_list(self):
        """Обновление удаленных файлов с использованием кэша"""
        
        def refresh_task():
            cached_list = self.get_cached_remote_list()
            if cached_list:
                self.root.after(0, lambda: (
                    self.remote_tree.delete(*self.remote_tree.get_children()),
                    [self.remote_tree.insert("", tk.END, values=item) for item in cached_list],
                    self.remote_path_var.set(f"Удалённая: {self.ftp.pwd()}")
                ))
                return

            with self.ftp_lock:
                try:
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
                    
                    self.root.after(0, lambda: (
                        self.remote_tree.delete(*self.remote_tree.get_children()),
                        [self.remote_tree.insert("", tk.END, values=item) for item in parsed],
                        self.remote_path_var.set(f"Удалённая: {self.ftp.pwd()}")
                    ))
                except Exception as e:
                    self.root.after(0, lambda: [
                        messagebox.showerror("Ошибка", f"Ошибка обновления: {e}"),
                        self.update_status(f"Ошибка: {e}", error=True)
                    ])

        self.task_queue.put(refresh_task)

    def download_files(self):
        """Скачивание файлов"""
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файлы для скачивания")
            return

        dest_dir = filedialog.askdirectory(title="Выберите папку для сохранения")
        if not dest_dir: return

        def download_task():
            total = len(selected)
            success = 0
            for i, item_id in enumerate(selected):
                filename = self.remote_tree.item(item_id, 'values')[0]
                dest = os.path.join(dest_dir, filename)
                try:
                    self.root.after(0, lambda f=filename: [
                        self.progress_label.config(text=f"Скачивание {i + 1}/{total}: {f}"),
                        self.progress.config(value=(i / total) * 100)
                    ])
                    with open(dest, 'wb') as f:
                        self.ftp.retrbinary(f"RETR {filename}", f.write)
                    success += 1
                except Exception as e:
                    self.root.after(0, lambda f=filename, eх=e: [
                        messagebox.showerror("Ошибка", f"Ошибка скачивания {f}: {eх}"),
                        self.update_status(f"Ошибка: {f}", error=True)
                    ])
            self.root.after(0, lambda: [
                self.progress.config(value=100),
                messagebox.showinfo("Готово", f"Успешно скачано {success}/{total} файлов"),
                self.refresh_local_list()
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
            for i, item_id in enumerate(selected):
                filename = self.remote_tree.item(item_id, 'values')[0]
                try:
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
                    self.root.after(0, lambda f=filename, eх=e: [
                        messagebox.showerror("Ошибка", f"Ошибка удаления {f}: {eх}"),
                        self.update_status(f"Ошибка: {f}", error=True)
                    ])
            self.root.after(0, lambda: [
                self.progress.config(value=100),
                messagebox.showinfo("Готово", f"Удалено {success}/{total} файлов"),
                self.refresh_remote_list()
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
                self.root.after(0, lambda: [
                    messagebox.showerror("Ошибка", f"Ошибка создания: {e}"),
                    self.update_status(f"Ошибка: {e}", error=True)
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

        answer = messagebox.askyesno("Синхронизация",
                                     "Выберите направление синхронизации:\n"
                                     "Да - Загрузить локальные файлы на сервер\n"
                                     "Нет - Скачать файлы с сервера",
                                     detail="В случае конфликта файлы будут перезаписаны!")

        def sync_task():
            try:
                if answer:  # Локальная → Удаленная
                    local_files = set(os.listdir(self.current_local_dir))
                    remote_files = set(self.ftp.nlst())

                    for file in local_files:
                        local_path = os.path.join(self.current_local_dir, file)
                        if os.path.isfile(local_path):
                            with open(local_path, 'rb') as f:
                                self.ftp.storbinary(f'STOR {file}', f)

                    self.root.after(0, lambda: [
                        messagebox.showinfo("Готово", "Локальные файлы загружены на сервер"),
                        self.refresh_remote_list()
                    ])

                else:  # Удаленная → Локальная
                    remote_files = self.ftp.nlst()
                    local_files = set(os.listdir(self.current_local_dir))

                    for file in remote_files:
                        remote_path = file
                        local_path = os.path.join(self.current_local_dir, file)

                        # Проверка, является ли элемент файлом
                        try:
                            with open(local_path, 'wb') as f:
                                self.ftp.retrbinary(f'RETR {file}', f.write)
                        except error_perm:  # Если это директория - пропускаем
                            continue

                    self.root.after(0, lambda: [
                        messagebox.showinfo("Готово", "Файлы с сервера скачаны"),
                        self.refresh_local_list()
                    ])

            except Exception as e:
                self.root.after(0, lambda: [
                    messagebox.showerror("Ошибка", f"Ошибка синхронизации: {str(e)}"),
                    self.update_status(f"Ошибка синхронизации", error=True)
                ])

        self.task_queue.put(sync_task)

    def show_settings(self):
        """Окно настроек приложения"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Настройки")
        settings_window.geometry("300x200")

        # Настройка локальной директории
        ttk.Label(settings_window, text="Локальная директория:").pack(pady=5)
        dir_frame = ttk.Frame(settings_window)
        dir_frame.pack(fill=tk.X, padx=5)

        self.local_dir_entry = ttk.Entry(dir_frame)
        self.local_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.local_dir_entry.insert(0, self.current_local_dir)

        ttk.Button(
            dir_frame,
            text="Изменить",
            command=self.change_local_directory
        ).pack(side=tk.RIGHT)

    def change_local_directory(self):
        """Изменение локальной директории"""
        new_dir = filedialog.askdirectory(initialdir=self.current_local_dir)
        if new_dir:
            self.current_local_dir = new_dir
            self.local_path_var.set(f"Локальная: {self.current_local_dir}")
            self.refresh_local_list()

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
                    os.startfile(full_path)
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

            if messagebox.askyesno("Подтверждение", f"Удалить {filename}?"):
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
                # Используем FTP команды RNFR и RNTO
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

        if not messagebox.askyesno("Подтверждение", f"Удалить {filename}?"):
            return

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

    def get_cached_remote_list(self):
        current_path = self.ftp.pwd()
        current_time = time.time()
        
        if (current_path in self.remote_cache and 
            current_time - self.remote_cache[current_path][0] < self.cache_ttl):
            return self.remote_cache[current_path][1]
            
        return None

    def create_search_bar(self):
        """Создание панели поиска"""
        search_frame = ttk.Frame(self.root)
        search_frame.pack(fill=tk.X, padx=5, pady=2)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def load_saved_data(self):
        # Реализация загрузки сохраненных данных
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPClientApp(root)
    root.mainloop()