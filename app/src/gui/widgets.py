"""
Виджеты для GUI
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, List, Tuple


class FileListView(ttk.Treeview):
    """Виджет для отображения списка файлов"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, 
                        columns=("name", "size", "type", "modified"),
                        show="headings",
                        selectmode="extended",
                        **kwargs)
        
        # Настройка колонок
        columns = [
            ("name", "Имя", 300),
            ("size", "Размер", 100),
            ("type", "Тип", 100),
            ("modified", "Изменён", 150)
        ]
        
        for col_id, heading, width in columns:
            self.heading(col_id, text=heading)
            self.column(col_id, width=width, anchor="w" if col_id == "name" else "center")
        
        # Добавляем скроллбар
        self.scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.yview)
        self.configure(yscrollcommand=self.scrollbar.set)
        
        # Размещаем элементы
        self.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def set_items(self, items: List[Tuple[str, str, str, str]]) -> None:
        """Установка списка файлов"""
        self.delete(*self.get_children())
        for item in items:
            self.insert("", "end", values=item)


class StatusBar(ttk.Frame):
    """Статус бар"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.progress = ttk.Progressbar(self, orient="horizontal", 
                                      mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=5, pady=2)
        
        self.label = ttk.Label(self, text="Готов", style="Status.TLabel")
        self.label.pack(fill="x", padx=5)

    def set_progress(self, value: float) -> None:
        """Установка значения прогресса"""
        self.progress["value"] = value

    def set_status(self, text: str, error: bool = False) -> None:
        """Установка текста статуса"""
        self.label["style"] = "Error.TLabel" if error else "Status.TLabel"
        self.label["text"] = text


class ConnectionPanel(ttk.LabelFrame):
    """Панель подключения"""
    def __init__(self, parent, on_connect: Callable, **kwargs):
        super().__init__(parent, text="Подключение", **kwargs)
        
        # Создаем и размещаем элементы
        entries = [
            ("Сервер:", "host", "localhost"),
            ("Порт:", "port", "21"),
            ("Пользователь:", "user", "anonymous")
        ]
        
        self.entries = {}
        for i, (label, name, default) in enumerate(entries):
            ttk.Label(self, text=label).grid(row=i, column=0, padx=5, pady=2, sticky="e")
            entry = ttk.Entry(self)
            entry.insert(0, default)
            entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
            self.entries[name] = entry
        
        # Поле для пароля
        ttk.Label(self, text="Пароль:").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        self.password_entry = ttk.Entry(self, show="*")
        self.password_entry.grid(row=3, column=1, padx=5, pady=2, sticky="ew")
        
        # Кнопка подключения
        self.connect_btn = ttk.Button(self, text="Подключиться",
                                    command=self._on_connect,
                                    style="Primary.TButton")
        self.connect_btn.grid(row=4, column=0, columnspan=2, pady=5)
        
        # Настраиваем растяжение колонок
        self.columnconfigure(1, weight=1)
        
        self._on_connect_callback = on_connect

    def _on_connect(self) -> None:
        """Обработка нажатия кнопки подключения"""
        if self._on_connect_callback:
            self._on_connect_callback(
                self.entries["host"].get(),
                int(self.entries["port"].get()),
                self.entries["user"].get(),
                self.password_entry.get()
            )

    def set_connected_state(self, connected: bool) -> None:
        """Установка состояния подключения"""
        if connected:
            self.connect_btn.configure(text="Отключиться")
        else:
            self.connect_btn.configure(text="Подключиться") 