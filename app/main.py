import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from ftplib import FTP
import os


class FTPClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python FTP Client")
        self.root.geometry("800x600")

        self.ftp = None
        self.current_remote_dir = "/"
        self.current_local_dir = os.getcwd()

        self.create_widgets()

    def create_widgets(self):
        # Панель подключения
        connection_frame = ttk.LabelFrame(self.root, text="Подключение")
        connection_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(connection_frame, text="Сервер:").grid(row=0, column=0, padx=5, pady=5)
        self.host_entry = ttk.Entry(connection_frame)
        self.host_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(connection_frame, text="Пользователь:").grid(row=1, column=0, padx=5, pady=5)
        self.user_entry = ttk.Entry(connection_frame)
        self.user_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(connection_frame, text="Пароль:").grid(row=2, column=0, padx=5, pady=5)
        self.password_entry = ttk.Entry(connection_frame, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)

        self.connect_btn = ttk.Button(connection_frame, text="Подключиться", command=self.connect_to_server)
        self.connect_btn.grid(row=3, column=0, columnspan=2, pady=5)

        # Основная область с файлами
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Локальные файлы
        local_frame = ttk.LabelFrame(main_frame, text="Локальные файлы")
        local_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.local_tree = ttk.Treeview(local_frame, columns=("name", "size"), show="headings")
        self.local_tree.heading("name", text="Имя")
        self.local_tree.heading("size", text="Размер")
        self.local_tree.pack(fill=tk.BOTH, expand=True)

        # Удаленные файлы
        remote_frame = ttk.LabelFrame(main_frame, text="Удаленные файлы")
        remote_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.remote_tree = ttk.Treeview(remote_frame, columns=("name", "size"), show="headings")
        self.remote_tree.heading("name", text="Имя")
        self.remote_tree.heading("size", text="Размер")
        self.remote_tree.pack(fill=tk.BOTH, expand=True)

        # Кнопки управления
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Загрузить", command=self.upload_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Скачать", command=self.download_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_remote_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Обновить", command=self.refresh_lists).pack(side=tk.RIGHT, padx=5)

    def connect_to_server(self):
        host = self.host_entry.get()
        user = self.user_entry.get()
        password = self.password_entry.get()

        try:
            self.ftp = FTP(host)
            self.ftp.login(user=user, passwd=password)
            messagebox.showinfo("Успех", "Успешное подключение к серверу")
            self.refresh_remote_list()
            self.connect_btn.config(text="Отключиться", command=self.disconnect_from_server)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться: {str(e)}")

    def disconnect_from_server(self):
        if self.ftp:
            self.ftp.quit()
            self.ftp = None
            self.connect_btn.config(text="Подключиться", command=self.connect_to_server)
            messagebox.showinfo("Отключение", "Соединение закрыто")

    def refresh_lists(self):
        self.refresh_local_list()
        if self.ftp:
            self.refresh_remote_list()

    def refresh_local_list(self):
        self.local_tree.delete(*self.local_tree.get_children())
        try:
            for item in os.listdir(self.current_local_dir):
                full_path = os.path.join(self.current_local_dir, item)
                size = os.path.getsize(full_path) if os.path.isfile(full_path) else ""
                self.local_tree.insert("", tk.END, values=(item, size))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить локальный список: {str(e)}")

    def refresh_remote_list(self):
        self.remote_tree.delete(*self.remote_tree.get_children())
        try:
            files = []
            self.ftp.retrlines('LIST', files.append)

            for line in files:
                parts = line.split()
                if len(parts) < 9:
                    continue
                name = ' '.join(parts[8:])
                size = parts[4] if parts[0].startswith('-') else ""
                self.remote_tree.insert("", tk.END, values=(name, size))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить удаленный список: {str(e)}")

    def download_file(self):
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файл для скачивания")
            return

        filename = self.remote_tree.item(selected[0])['values'][0]
        save_path = filedialog.asksaveasfilename(initialdir=self.current_local_dir,
                                                 initialfile=filename)
        if not save_path:
            return

        try:
            with open(save_path, 'wb') as f:
                self.ftp.retrbinary(f'RETR {filename}', f.write)
            messagebox.showinfo("Успех", "Файл успешно скачан")
            self.refresh_local_list()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось скачать файл: {str(e)}")

    def upload_file(self):
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        filepath = filedialog.askopenfilename(initialdir=self.current_local_dir)
        if not filepath:
            return

        filename = os.path.basename(filepath)
        try:
            with open(filepath, 'rb') as f:
                self.ftp.storbinary(f'STOR {filename}', f)
            messagebox.showinfo("Успех", "Файл успешно загружен")
            self.refresh_remote_list()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл: {str(e)}")

    def delete_remote_file(self):
        if not self.ftp:
            messagebox.showwarning("Ошибка", "Сначала подключитесь к серверу")
            return

        selected = self.remote_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите файл для удаления")
            return

        filename = self.remote_tree.item(selected[0])['values'][0]

        try:
            # Проверяем, это файл или директория
            is_dir = False
            files = []
            self.ftp.retrlines('LIST', files.append)
            for line in files:
                parts = line.split()
                if len(parts) < 9:
                    continue
                name = ' '.join(parts[8:])
                if name == filename and parts[0].startswith('d'):
                    is_dir = True
                    break

            if is_dir:
                # Удаление директории
                self.ftp.rmd(filename)
            else:
                # Удаление файла
                self.ftp.delete(filename)

            messagebox.showinfo("Успех", "Файл успешно удален")
            self.refresh_remote_list()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить файл: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = FTPClientApp(root)
    root.mainloop()