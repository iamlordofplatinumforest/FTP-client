"""
Диалоговые окна
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict, Any, List, Tuple


class SettingsDialog(tk.Toplevel):
    """Диалог настроек"""
    def __init__(self, parent, settings: Dict[str, Any], on_save: callable):
        super().__init__(parent)
        self.title("Настройки")
        self.geometry("600x500")
        self.transient(parent)
        self.grab_set()

        # Создаем notebook для вкладок
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Создаем вкладки
        self._create_general_tab(settings)
        self._create_interface_tab(settings)
        self._create_advanced_tab(settings)

        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Сохранить",
                  command=lambda: self._on_save(on_save)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена",
                  command=self.destroy).pack(side=tk.RIGHT, padx=5)

        # Сохраняем ссылки на элементы управления
        self.settings = settings
        self.controls = {}

    def _create_general_tab(self, settings: Dict[str, Any]) -> None:
        """Создание вкладки общих настроек"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Общие")

        # Локальная директория
        dir_frame = ttk.LabelFrame(frame, text="Директории")
        dir_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(dir_frame, text="Локальная директория:").pack(anchor="w", padx=5, pady=2)
        dir_entry = ttk.Entry(dir_frame)
        dir_entry.insert(0, settings['default_local_dir'])
        dir_entry.pack(fill=tk.X, padx=5, pady=2)
        self.controls['default_local_dir'] = dir_entry

        # Настройки подключения
        conn_frame = ttk.LabelFrame(frame, text="Подключение")
        conn_frame.pack(fill=tk.X, padx=5, pady=5)

        auto_reconnect = tk.BooleanVar(value=settings['auto_reconnect'])
        ttk.Checkbutton(conn_frame, text="Автоматическое переподключение",
                       variable=auto_reconnect).pack(anchor="w", padx=5, pady=2)
        self.controls['auto_reconnect'] = auto_reconnect

        reconnect_frame = ttk.Frame(conn_frame)
        reconnect_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(reconnect_frame, text="Количество попыток:").pack(side=tk.LEFT)
        reconnect_attempts = ttk.Spinbox(reconnect_frame, from_=1, to=10, width=5)
        reconnect_attempts.set(settings['reconnect_attempts'])
        reconnect_attempts.pack(side=tk.LEFT, padx=5)
        self.controls['reconnect_attempts'] = reconnect_attempts

    def _create_interface_tab(self, settings: Dict[str, Any]) -> None:
        """Создание вкладки настроек интерфейса"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Интерфейс")

        # Настройки отображения
        show_hidden = tk.BooleanVar(value=settings['show_hidden_files'])
        ttk.Checkbutton(frame, text="Показывать скрытые файлы",
                       variable=show_hidden).pack(anchor="w", padx=5, pady=2)
        self.controls['show_hidden_files'] = show_hidden

        sort_folders = tk.BooleanVar(value=settings['sort_folders_first'])
        ttk.Checkbutton(frame, text="Показывать папки первыми",
                       variable=sort_folders).pack(anchor="w", padx=5, pady=2)
        self.controls['sort_folders_first'] = sort_folders

        # Подтверждения
        confirm_frame = ttk.LabelFrame(frame, text="Подтверждения")
        confirm_frame.pack(fill=tk.X, padx=5, pady=5)

        confirm_delete = tk.BooleanVar(value=settings['confirm_delete'])
        ttk.Checkbutton(confirm_frame, text="Подтверждать удаление",
                       variable=confirm_delete).pack(anchor="w", padx=5, pady=2)
        self.controls['confirm_delete'] = confirm_delete

        confirm_overwrite = tk.BooleanVar(value=settings['confirm_overwrite'])
        ttk.Checkbutton(confirm_frame, text="Подтверждать перезапись",
                       variable=confirm_overwrite).pack(anchor="w", padx=5, pady=2)
        self.controls['confirm_overwrite'] = confirm_overwrite

    def _create_advanced_tab(self, settings: Dict[str, Any]) -> None:
        """Создание вкладки расширенных настроек"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Расширенные")

        # Настройки производительности
        perf_frame = ttk.LabelFrame(frame, text="Производительность")
        perf_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(perf_frame, text="Размер буфера (байт):").pack(anchor="w", padx=5, pady=2)
        buffer_size = ttk.Entry(perf_frame)
        buffer_size.insert(0, str(settings['buffer_size']))
        buffer_size.pack(fill=tk.X, padx=5, pady=2)
        self.controls['buffer_size'] = buffer_size

        ttk.Label(perf_frame, text="Время жизни кэша (сек):").pack(anchor="w", padx=5, pady=2)
        cache_ttl = ttk.Entry(perf_frame)
        cache_ttl.insert(0, str(settings['cache_ttl']))
        cache_ttl.pack(fill=tk.X, padx=5, pady=2)
        self.controls['cache_ttl'] = cache_ttl

    def _on_save(self, callback: callable) -> None:
        """Сохранение настроек"""
        new_settings = {}
        
        # Собираем значения из элементов управления
        for key, control in self.controls.items():
            if isinstance(control, ttk.Entry):
                new_settings[key] = control.get()
            elif isinstance(control, tk.BooleanVar):
                new_settings[key] = control.get()
            elif isinstance(control, ttk.Spinbox):
                new_settings[key] = int(control.get())

        # Преобразуем типы данных
        if 'buffer_size' in new_settings:
            new_settings['buffer_size'] = int(new_settings['buffer_size'])
        if 'cache_ttl' in new_settings:
            new_settings['cache_ttl'] = int(new_settings['cache_ttl'])

        callback(new_settings)
        self.destroy()


class BookmarkDialog(tk.Toplevel):
    """Диалог управления закладками"""
    def __init__(self, parent, bookmarks: List[Dict], on_select: callable, on_delete: callable):
        super().__init__(parent)
        self.title("Закладки")
        self.geometry("800x300")
        self.transient(parent)
        self.grab_set()

        # Создаем таблицу закладок
        self.tree = ttk.Treeview(self, columns=("name", "host", "port", "user"),
                                show="headings")
        self.tree.heading("name", text="Название")
        self.tree.heading("host", text="Сервер")
        self.tree.heading("port", text="Порт")
        self.tree.heading("user", text="Пользователь")

        # Устанавливаем ширину колонок
        self.tree.column("name", width=200)
        self.tree.column("host", width=250)
        self.tree.column("port", width=100)
        self.tree.column("user", width=200)

        # Заполняем данными
        for bookmark in bookmarks:
            self.tree.insert("", tk.END, values=(
                bookmark['name'],
                bookmark['host'],
                bookmark['port'],
                bookmark['user']
            ))

        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Подключиться",
                  command=lambda: self._on_select(on_select)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Удалить",
                  command=lambda: self._on_delete(on_delete)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Закрыть",
                  command=self.destroy).pack(side=tk.RIGHT, padx=2)

    def _on_select(self, callback: callable) -> None:
        """Обработка выбора закладки"""
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            callback(item['values'])
            self.destroy()

    def _on_delete(self, callback: callable) -> None:
        """Обработка удаления закладки"""
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            if callback(item['values'][0]):  # Передаем имя закладки
                self.tree.delete(selected) 