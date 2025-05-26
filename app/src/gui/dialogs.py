import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, List, Tuple
from datetime import datetime


class QuickConnectDialog:
    def __init__(self, parent, callback: Callable):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Быстрое подключение")
        self.dialog.geometry("350x200")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.dialog.geometry("+%d+%d" % (
            parent.winfo_rootx() + parent.winfo_width()//2 - 150,
            parent.winfo_rooty() + parent.winfo_height()//2 - 100
        ))

        frame = ttk.Frame(self.dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        entries = {}
        fields = [
            ("host", "Сервер:", "localhost"),
            ("port", "Порт:", "21"),
            ("user", "Пользователь:", "user"),
            ("password", "Пароль:", "")
        ]

        for row, (field, label, default) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="e", pady=2)
            entry = ttk.Entry(frame)
            entry.insert(0, default)
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            if field == "password":
                entry.configure(show="*")
            entries[field] = entry

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=10)

        ttk.Button(btn_frame, text="Подключиться", 
                  command=lambda: self._connect(callback, entries)).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Отмена",
                  command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _connect(self, callback: Callable, entries: Dict[str, ttk.Entry]):
        try:
            host = entries["host"].get()
            port = int(entries["port"].get())
            user = entries["user"].get()
            password = entries["password"].get()
            
            self.dialog.destroy()
            callback(host, port, user, password)
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат порта")


class HistoryDialog:
    def __init__(self, parent, history: List[Dict], callback: Callable):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("История подключений")
        self.dialog.geometry("800x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        tree = ttk.Treeview(self.dialog, 
                           columns=("host", "port", "user", "date"),
                           show="headings")
        
        tree.heading("host", text="Сервер")
        tree.heading("port", text="Порт")
        tree.heading("user", text="Пользователь")
        tree.heading("date", text="Дата")

        tree.column("host", width=250)
        tree.column("port", width=100)
        tree.column("user", width=200)
        tree.column("date", width=200)

        for conn in history:
            date = datetime.fromisoformat(conn['timestamp']).strftime("%Y-%m-%d %H:%M")
            tree.insert("", tk.END, values=(
                conn['host'],
                conn['port'],
                conn['user'],
                date
            ))

        tree.bind("<Double-1>", lambda e: self._connect(callback, tree))
        tree.pack(fill=tk.BOTH, expand=True)

    def _connect(self, callback: Callable, tree: ttk.Treeview):
        selected = tree.selection()
        if not selected:
            return
            
        item = tree.item(selected[0])
        values = item['values']
        
        self.dialog.destroy()
        callback(values)


class BookmarksDialog:
    def __init__(self, parent, bookmarks: List[Dict], 
                 connect_callback: Callable, delete_callback: Callable):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Закладки")
        self.dialog.geometry("800x350")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        tree = ttk.Treeview(self.dialog, 
                           columns=("name", "host", "port", "user"),
                           show="headings")
        
        tree.heading("name", text="Название")
        tree.heading("host", text="Сервер")
        tree.heading("port", text="Порт")
        tree.heading("user", text="Пользователь")
        tree.column("name", width=200)
        tree.column("host", width=250)
        tree.column("port", width=100)
        tree.column("user", width=200)

        for bookmark in bookmarks:
            tree.insert("", tk.END, values=(
                bookmark['name'],
                bookmark['host'],
                bookmark['port'],
                bookmark['user']
            ))

        tree.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Подключиться", 
                  command=lambda: self._connect(connect_callback, tree)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Удалить", 
                  command=lambda: self._delete(delete_callback, tree)).pack(side=tk.LEFT, padx=2)

    def _connect(self, callback: Callable, tree: ttk.Treeview):
        selected = tree.selection()
        if not selected:
            return
            
        item = tree.item(selected[0])
        values = item['values']
        
        self.dialog.destroy()
        callback(values)

    def _delete(self, callback: Callable, tree: ttk.Treeview):
        selected = tree.selection()
        if not selected:
            return
            
        item = tree.item(selected[0])
        name = item['values'][0]
        
        if callback(name):
            tree.delete(selected)


class SettingsDialog:
    def __init__(self, parent, settings: Dict, callback: Callable):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Настройки")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="Общие")

        interface_frame = ttk.LabelFrame(general_frame, text="Интерфейс")
        interface_frame.pack(fill=tk.X, padx=5, pady=5)

        self.show_hidden = tk.BooleanVar(value=settings.get('show_hidden_files', False))
        self.sort_folders = tk.BooleanVar(value=settings.get('sort_folders_first', True))
        self.confirm_delete = tk.BooleanVar(value=settings.get('confirm_delete', True))
        self.confirm_overwrite = tk.BooleanVar(value=settings.get('confirm_overwrite', True))

        ttk.Checkbutton(interface_frame, text="Показывать скрытые файлы",
                       variable=self.show_hidden).pack(anchor="w", padx=5, pady=2)
        ttk.Checkbutton(interface_frame, text="Показывать папки первыми",
                       variable=self.sort_folders).pack(anchor="w", padx=5, pady=2)
        ttk.Checkbutton(interface_frame, text="Подтверждать удаление",
                       variable=self.confirm_delete).pack(anchor="w", padx=5, pady=2)
        ttk.Checkbutton(interface_frame, text="Подтверждать перезапись",
                       variable=self.confirm_overwrite).pack(anchor="w", padx=5, pady=2)

        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Сохранить", 
                  command=lambda: self._save(callback)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена",
                  command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def _save(self, callback: Callable):
        settings = {
            'show_hidden_files': self.show_hidden.get(),
            'sort_folders_first': self.sort_folders.get(),
            'confirm_delete': self.confirm_delete.get(),
            'confirm_overwrite': self.confirm_overwrite.get()
        }
        self.dialog.destroy()
        callback(settings)


class AboutDialog:
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("О программе")
        self.dialog.geometry("400x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.dialog.geometry("+%d+%d" % (
            parent.winfo_rootx() + parent.winfo_width()//2 - 200,
            parent.winfo_rooty() + parent.winfo_height()//2 - 150
        ))

        frame = ttk.Frame(self.dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="FTP Клиент", 
                 font=('Helvetica', 16, 'bold')).pack(pady=10)
        
        ttk.Label(frame, text="Версия 1.0", 
                 font=('Helvetica', 10)).pack()
        
        ttk.Label(frame, text="\n© 2025 Все права защищены\n",
                 font=('Helvetica', 9)).pack()
        
        ttk.Label(frame, text="Программа для работы с FTP-серверами\n" +
                            "Поддерживает основные операции с файлами,\n" +
                            "закладки и историю подключений.", 
                 justify=tk.CENTER).pack(pady=10)
        
        ttk.Button(frame, text="Закрыть", 
                  command=self.dialog.destroy).pack(pady=10) 