import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Optional, List, Tuple, Dict, Any
from datetime import datetime


class FileListView(ttk.Treeview):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, 
                        columns=("name", "size", "type", "modified"),
                        show="headings",
                        selectmode="extended",
                        **kwargs)

        self.heading("name", text="Имя")
        self.heading("size", text="Размер")
        self.heading("type", text="Тип")
        self.heading("modified", text="Изменён")
        
        self.column("name", width=300)
        self.column("size", width=100)
        self.column("type", width=100)
        self.column("modified", width=150)

        self.scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.yview)
        self.configure(yscrollcommand=self.scrollbar.set)

        self.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.current_sort = None
        self.reverse_sort = False

    def set_items(self, items: List[Any]) -> None:
        self.delete(*self.get_children())
        for item in items:
            if isinstance(item, dict):
                values = (
                    item['name'],
                    item.get('size_human', ''),
                    item['type'],
                    item['modified'].strftime('%Y-%m-%d %H:%M:%S') if isinstance(item['modified'], datetime) else item['modified']
                )
            else:
                values = item
            self.insert("", "end", values=values)

    def _sort_by_column(self, column: str) -> None:
        items = [(self.set(item, column), item) for item in self.get_children('')]

        if self.current_sort == column:
            self.reverse_sort = not self.reverse_sort
        else:
            self.reverse_sort = False
        self.current_sort = column

        items.sort(reverse=self.reverse_sort)
        for index, (_, item) in enumerate(items):
            self.move(item, '', index)


class StatusBar(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, style='Statusbar.TFrame', **kwargs)

        status_frame = ttk.Frame(self, style='Statusbar.TFrame')
        status_frame.pack(side="left", fill="x", expand=True, padx=5, pady=2)
        
        self.status_label = ttk.Label(status_frame,
                                    text="Готов",
                                    style='Statusbar.TLabel')
        self.status_label.pack(side="left", fill="x", expand=True)

        progress_frame = ttk.Frame(self, style='Statusbar.TFrame')
        progress_frame.pack(side="right", padx=5, pady=2)
        
        self.progress = ttk.Progressbar(progress_frame,
                                      orient="horizontal",
                                      length=200,
                                      mode='determinate',
                                      style='Colored.Horizontal.TProgressbar')
        self.progress.pack(side="right")

        self.percent_label = ttk.Label(progress_frame,
                                     text="",
                                     style='Statusbar.TLabel')
        self.percent_label.pack(side="right", padx=(0, 5))

    def set_status(self, text: str, error: bool = False) -> None:
        self.status_label.configure(
            text=text,
            style='StatusbarError.TLabel' if error else 'Statusbar.TLabel'
        )
        self.status_label.update_idletasks()

    def show_progress(self, show: bool = True) -> None:
        if show:
            self.progress.pack(side="right")
            self.percent_label.pack(side="right", padx=(0, 5))
        else:
            self.progress.pack_forget()
            self.percent_label.pack_forget()

    def set_progress(self, value: float) -> None:
        self.progress['value'] = value
        self.percent_label.configure(text=f"{int(value)}%")
        self.progress.update_idletasks()
        self.percent_label.update_idletasks()


class ConnectionPanel(ttk.LabelFrame):
    def __init__(self, parent, on_connect: Callable, **kwargs):
        super().__init__(parent, text="Подключение", style='Connection.TFrame', **kwargs)

        entries = [
            ("Сервер:", "host", "localhost"),
            ("Порт:", "port", "21"),
            ("Пользователь:", "user", "user")
        ]
        
        self.entries = {}
        for i, (label, name, default) in enumerate(entries):
            ttk.Label(self, text=label).grid(row=i, column=0, padx=5, pady=2, sticky="e")
            entry = ttk.Entry(self)
            entry.insert(0, default)
            entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
            self.entries[name] = entry

        ttk.Label(self, text="Пароль:").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        pwd_frame = ttk.Frame(self)
        pwd_frame.grid(row=3, column=1, padx=5, pady=2, sticky="ew")
        
        self.password_entry = ttk.Entry(pwd_frame, show="*")
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.show_password = tk.BooleanVar(value=False)
        self.toggle_pwd_btn = ttk.Button(pwd_frame, text="👁", width=3,
                                       command=self._toggle_password_visibility)
        self.toggle_pwd_btn.pack(side=tk.LEFT, padx=(2, 0))

        self.connect_btn = ttk.Button(self, text="Подключиться",
                                    command=self._on_button_click,
                                    style="Primary.TButton")
        self.connect_btn.grid(row=4, column=0, columnspan=2, pady=5)

        self.columnconfigure(1, weight=1)
        
        self._on_connect_callback = on_connect
        self._is_connected = False

    def _on_button_click(self) -> None:
        if self._is_connected:
            if self._on_connect_callback:
                self._on_connect_callback(None, None, None, None)
        else:
            # Получаем значения полей
            host = self.entries["host"].get().strip()
            port = self.entries["port"].get().strip()
            user = self.entries["user"].get().strip()
            password = self.password_entry.get()

            # Базовая валидация
            if not host:
                self.entries["host"].focus()
                return
                
            if not port:
                self.entries["port"].focus()
                return
                
            if not user:
                self.entries["user"].focus()
                return
                
            if not password:
                self.password_entry.focus()
                return

            try:
                port = int(port)
            except ValueError:
                self.entries["port"].focus()
                return

            if self._on_connect_callback:
                self._on_connect_callback(host, port, user, password)

    def _toggle_password_visibility(self) -> None:
        if self.show_password.get():
            self.password_entry.configure(show="*")
            self.show_password.set(False)
        else:
            self.password_entry.configure(show="")
            self.show_password.set(True)

    def set_connected_state(self, connected: bool) -> None:
        self._is_connected = connected
        if connected:
            self.connect_btn.configure(text="Отключиться")
            for entry in self.entries.values():
                entry.configure(state="disabled")
            self.password_entry.configure(state="disabled")
        else:
            self.connect_btn.configure(text="Подключиться")
            for entry in self.entries.values():
                entry.configure(state="normal")
            self.password_entry.configure(state="normal")


class SearchPanel(ttk.LabelFrame):
    def __init__(self, parent, on_search: Callable, **kwargs):
        super().__init__(parent, text="Поиск файлов", style='Search.TFrame', **kwargs)

        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, padx=5, pady=2)

        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self._on_search())
        
        self.search_entry = ttk.Entry(input_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(input_frame, text="✕", width=3,
                  command=self.clear_search).pack(side=tk.LEFT, padx=2)

        options_frame = ttk.Frame(self)
        options_frame.pack(fill=tk.X, padx=5, pady=2)

        self.search_scope = tk.StringVar(value="both")
        ttk.Radiobutton(options_frame, text="Локальные", 
                       variable=self.search_scope, 
                       value="local",
                       command=self._on_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(options_frame, text="Удаленные", 
                       variable=self.search_scope, 
                       value="remote",
                       command=self._on_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(options_frame, text="Везде", 
                       variable=self.search_scope, 
                       value="both",
                       command=self._on_search).pack(side=tk.LEFT, padx=5)

        self.case_sensitive = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Учитывать регистр",
                       variable=self.case_sensitive,
                       command=self._on_search).pack(side=tk.LEFT, padx=5)

        self.search_in_folders = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Искать в папках",
                       variable=self.search_in_folders,
                       command=self._on_search).pack(side=tk.LEFT, padx=5)

        self._on_search_callback = on_search

    def clear_search(self) -> None:
        self.search_var.set("")

    def _on_search(self) -> None:
        if self._on_search_callback:
            self._on_search_callback(
                self.search_var.get(),
                self.search_scope.get(),
                self.case_sensitive.get(),
                self.search_in_folders.get()
            )


class PathPanel(ttk.Frame):
    def __init__(self, parent, on_path_change: Optional[Callable] = None, **kwargs):
        super().__init__(parent, style='Path.TFrame', **kwargs)
        
        self.path_var = tk.StringVar()
        self.label = ttk.Label(self, textvariable=self.path_var)
        self.label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        if on_path_change:
            self.browse_btn = ttk.Button(self, text="...",
                                       command=lambda: self._browse_directory(on_path_change))
            self.browse_btn.pack(side=tk.RIGHT, padx=2)

    def set_path(self, path: str) -> None:
        self.path_var.set(path)

    def _browse_directory(self, callback: Callable) -> None:
        directory = filedialog.askdirectory(initialdir=self.path_var.get())
        if directory:
            callback(directory) 