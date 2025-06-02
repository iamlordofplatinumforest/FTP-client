from ftplib import FTP, FTP_TLS, error_perm
import os
from threading import Lock, Thread
from typing import Optional, Tuple, List, Dict, Any, Callable
from datetime import datetime, timezone
import humanize
import time
from queue import Queue
import socket
import sys
from src.core.settings import Settings


def debug_log(message: str):
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


class FTPClient:
    def __init__(self):
        self.ftp = None
        self.ftp_lock = Lock()
        self.monitor_thread = None
        self.stop_monitor = False
        self.settings = Settings()
        self.current_remote_dir = "/"
        self.connection_params = None
        self.monitor_running = False
        self.remote_cache = {}

    def connect(self, host: str, port: int, user: str, password: str) -> Tuple[bool, str]:
        debug_log("\nDEBUG: FTPClient: Начало подключения")
        try:
            with self.ftp_lock:
                # Если есть активное подключение, сначала отключаемся
                if self.ftp:
                    debug_log("DEBUG: FTPClient: Закрываем предыдущее подключение")
                    try:
                        self.ftp.quit()
                    except:
                        pass
                    self.ftp = None

                debug_log("DEBUG: FTPClient: Создаем новое подключение")
                self.ftp = FTP()
                self.ftp.connect(host, port)
                self.ftp.login(user, password)
                self.ftp.encoding = self.settings.get('encoding', 'utf-8')

                self.connection_params = {
                    'host': host,
                    'port': port,
                    'user': user,
                    'password': password
                }

                debug_log("DEBUG: FTPClient: Подключение успешно установлено")
                return True, "Успешное подключение"
        except Exception as e:
            debug_log(f"DEBUG: FTPClient: Ошибка подключения: {str(e)}")
            # Очищаем объект FTP при ошибке
            self.ftp = None
            self.connection_params = None
            return False, str(e)

    def reconnect(self) -> Tuple[bool, str]:
        if not self.connection_params:
            return False, "Нет сохраненных параметров подключения"

        return self.connect(**self.connection_params)

    def disconnect(self) -> None:
        debug_log("\nDEBUG: FTPClient: Начало отключения")
        self.monitor_running = False

        with self.ftp_lock:
            if self.ftp:
                try:
                    debug_log("DEBUG: FTPClient: Отправляем команду QUIT")
                    self.ftp.quit()
                except Exception as e:
                    debug_log(f"DEBUG: FTPClient: Ошибка при отправке QUIT: {str(e)}")
                finally:
                    debug_log("DEBUG: FTPClient: Очищаем объект FTP")
                    self.ftp = None
                    self.connection_params = None
                    debug_log("DEBUG: FTPClient: Отключение завершено")

    def _get_file_list(self) -> List[Tuple[str, bool]]:
        file_list = []
        self.ftp.retrlines('LIST', file_list.append)
        items = []
        for line in file_list:
            parts = line.split(maxsplit=8)
            if len(parts) < 9:
                continue
            perm = parts[0]
            name = parts[8].strip()
            if name in ('.', '..'):
                continue
            is_dir = perm.startswith('d')
            items.append((name, is_dir))
        return items

    def list_files(self) -> List[Tuple[str, str, str, str]]:
        if not self.ftp:
            return []

        items = []
        try:
            with self.ftp_lock:
                file_list = []
                self.ftp.retrlines('LIST', file_list.append)

                for line in file_list:
                    try:
                        parts = line.split(maxsplit=8)
                        if len(parts) < 9:
                            continue

                        name = parts[8].strip()
                        if name in ('.', '..'):
                            continue

                        perm = parts[0]
                        is_dir = perm.startswith('d')

                        if is_dir:
                            try:
                                current_dir = self.ftp.pwd()
                                self.ftp.cwd(name)
                                dir_items = []
                                self.ftp.retrlines('NLST', dir_items.append)
                                size = f"{len(dir_items)} элем."
                                self.ftp.cwd(current_dir)
                            except:
                                size = "Нет доступа"
                        else:
                            try:
                                size = humanize.naturalsize(int(parts[4]))
                            except:
                                size = parts[4]

                        time_str = ' '.join(parts[5:8])
                        modified = self._parse_ftp_time(time_str)

                        items.append((name, size, "Папка" if is_dir else "Файл", modified))
                    except:
                        continue
        except:
            pass

        return items

    def download_file(self, remote_file: str, local_path: str,
                     progress_callback=None) -> Tuple[bool, str]:
        if not self.ftp:
            return False, "Нет подключения"

        try:
            file_size = self.ftp.size(remote_file)
            buffer_size = self.settings.get('buffer_size', 8192)

            with self.ftp_lock:
                with open(local_path, 'wb') as f:
                    bytes_received = 0

                    def callback(block):
                        nonlocal bytes_received
                        bytes_received += len(block)
                        f.write(block)
                        if progress_callback:
                            progress_callback(bytes_received, file_size)

                    self.ftp.retrbinary(f'RETR {remote_file}', callback, buffer_size)

                downloaded_size = os.path.getsize(local_path)
                if downloaded_size != file_size:
                    os.remove(local_path)
                    return False, "Ошибка скачивания: размер файла не совпадает"

                return True, "Файл успешно скачан"

        except Exception as e:
            if os.path.exists(local_path):
                os.remove(local_path)
            return False, str(e)

    def upload_file(self, local_path: str, remote_file: str,
                   progress_callback=None) -> Tuple[bool, str]:
        if not self.ftp:
            return False, "Нет подключения"

        try:
            file_size = os.path.getsize(local_path)
            buffer_size = self.settings.get('buffer_size', 8192)

            with self.ftp_lock:
                with open(local_path, 'rb') as f:
                    bytes_sent = 0

                    def callback(block):
                        nonlocal bytes_sent
                        bytes_sent += len(block)
                        if progress_callback:
                            progress_callback(bytes_sent, file_size)
                        return block

                    self.ftp.storbinary(f'STOR {remote_file}', f, buffer_size, callback)

                uploaded_size = self.ftp.size(remote_file)
                if uploaded_size != file_size:
                    self.ftp.delete(remote_file)
                    return False, "Ошибка загрузки: размер файла не совпадает"

                return True, "Файл успешно загружен"

        except Exception as e:
            return False, str(e)

    def upload_folder(self, local_path: str, remote_folder: str,
                     progress_callback=None) -> Tuple[bool, str]:
        try:
            with self.ftp_lock:
                try:
                    self.ftp.mkd(remote_folder)
                except:
                    pass

                current_remote = self.ftp.pwd()
                self.ftp.cwd(remote_folder)

                for item in os.listdir(local_path):
                    local_item_path = os.path.join(local_path, item)

                    if os.path.isfile(local_item_path):
                        success, message = self.upload_file(local_item_path, item, progress_callback)
                        if not success:
                            return False, f"Ошибка загрузки {item}: {message}"
                    elif os.path.isdir(local_item_path):
                        success, message = self.upload_folder(local_item_path, item, progress_callback)
                        if not success:
                            return False, message

                self.ftp.cwd(current_remote)
                return True, "Папка успешно загружена"

        except Exception as e:
            return False, str(e)

    def create_directory(self, dirname: str) -> Tuple[bool, str]:
        if not self.ftp:
            return False, "Нет подключения"

        try:
            dirname = dirname.strip()
            if not dirname:
                return False, "Пустое имя директории"

            with self.ftp_lock:
                items = self._get_file_list()
                for name, is_dir in items:
                    if name == dirname and is_dir:
                        return False, f"Папка '{dirname}' уже существует"

                try:
                    self.ftp.mkd(dirname)
                    return True, f"Папка '{dirname}' создана"
                except error_perm as e:
                    if '550' in str(e):
                        return False, f"Папка '{dirname}' не может быть создана: {str(e)}"
                    else:
                        return False, f"Ошибка создания папки: {str(e)}"
                except Exception as e:
                    return False, f"Ошибка создания папки: {str(e)}"
        except Exception as e:
            return False, str(e)

    def delete_item(self, name: str) -> Tuple[bool, str]:
        if not self.ftp:
            return False, "Нет подключения"

        try:
            name = name.strip()
            if not name:
                return False, "Пустое имя"

            with self.ftp_lock:
                current_dir = self.ftp.pwd()
                try:
                    self.ftp.cwd(name)
                    is_dir = True
                    self.ftp.cwd(current_dir)
                except:
                    is_dir = False

                if is_dir:
                    try:
                        self.ftp.cwd(name)
                        dir_items = []
                        self.ftp.retrlines('NLST', dir_items.append)
                        self.ftp.cwd(current_dir)

                        dir_items = [item for item in dir_items if item not in ('.', '..')]
                        
                        if dir_items:
                            return False, "NOT_EMPTY_DIR"

                        self.ftp.rmd(name)
                        return True, f"Папка '{name}' удалена"
                    except Exception as e:
                        return False, f"Ошибка удаления папки: {str(e)}"
                else:
                    try:
                        self.ftp.delete(name)
                        return True, f"Файл '{name}' удален"
                    except Exception as e:
                        return False, f"Ошибка удаления файла: {str(e)}"
        except Exception as e:
            return False, str(e)

    def delete_directory_recursive(self, dirname: str) -> Tuple[bool, str]:
        if not self.ftp:
            return False, "Нет подключения"

        try:
            with self.ftp_lock:
                current_dir = self.ftp.pwd()
                
                try:
                    self.ftp.cwd(dirname)

                    file_list = []
                    self.ftp.retrlines('NLST', file_list.append)

                    file_list = [f for f in file_list if f not in ('.', '..')]

                    for item in file_list:
                        try:
                            self.ftp.delete(item)
                        except:
                            try:
                                self.delete_directory_recursive(item)
                            except Exception as e:
                                self.ftp.cwd(current_dir)
                                return False, f"Ошибка удаления {item}: {str(e)}"

                    self.ftp.cwd(current_dir)

                    self.ftp.rmd(dirname)
                    return True, f"Папка '{dirname}' и её содержимое удалены"
                    
                except Exception as e:
                    self.ftp.cwd(current_dir)
                    return False, f"Ошибка при удалении директории: {str(e)}"
                    
        except Exception as e:
            return False, str(e)

    def rename_item(self, old_name: str, new_name: str) -> Tuple[bool, str]:
        if not self.ftp:
            return False, "Нет подключения"

        try:
            with self.ftp_lock:
                self.ftp.rename(str(old_name), str(new_name))
                return True, "Успешно переименовано"
        except Exception as e:
            return False, str(e)

    def change_directory(self, path: str) -> Tuple[bool, str]:
        if not self.ftp:
            return False, "Нет подключения"

        try:
            with self.ftp_lock:
                self.ftp.cwd(path)
                self.current_remote_dir = self.ftp.pwd()
                return True, "Директория изменена"
        except Exception as e:
            return False, str(e)

    def get_current_directory(self) -> str:
        if not self.ftp:
            return "/"
        try:
            with self.ftp_lock:
                return self.ftp.pwd()
        except:
            return "/"

    def _parse_ftp_time(self, time_str: str) -> str:
        """Парсинг времени из FTP-листинга с учетом UTC"""
        try:
            current_year = datetime.now().year
            months = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }
            
            parts = time_str.split()
            if len(parts) != 3:
                return time_str
                
            month = months.get(parts[0], 1)
            day = int(parts[1])
            
            if ':' in parts[2]:  # Формат времени ЧЧ:ММ
                hour, minute = map(int, parts[2].split(':'))
                year = current_year

                dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)

                if dt > datetime.now(timezone.utc):
                    dt = datetime(year - 1, month, day, hour, minute, tzinfo=timezone.utc)

                local_dt = dt.astimezone()
                return local_dt.strftime("%Y-%m-%d %H:%M")
            else:
                year = int(parts[2])
                dt = datetime(year, month, day, 0, 0, tzinfo=timezone.utc)
                local_dt = dt.astimezone()
                return local_dt.strftime("%Y-%m-%d %H:%M")
        except:
            return time_str

    def _get_optimal_buffer_size(self, file_size: int) -> int:
        if file_size < 1024 * 1024:  # < 1MB
            return 8192
        elif file_size < 10 * 1024 * 1024:  # < 10MB
            return 32768
        else:  # >= 10MB
            return 65536

    def start_connection_monitor(self, on_connection_lost: Callable):
        def monitor():
            while not self.stop_monitor:
                try:
                    with self.ftp_lock:
                        if self.ftp:
                            self.ftp.voidcmd("NOOP")
                except:
                    if self.settings.get('auto_reconnect', True):
                        attempts = self.settings.get('reconnect_attempts', 3)
                        for _ in range(attempts):
                            success, _ = self.reconnect()
                            if success:
                                break
                        else:
                            on_connection_lost()
                    else:
                        on_connection_lost()
                time.sleep(30)

        self.stop_monitor = False
        self.monitor_thread = Thread(target=monitor, daemon=True)
        self.monitor_thread.start()

    def stop_connection_monitor(self):
        self.stop_monitor = True
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
            self.monitor_thread = None