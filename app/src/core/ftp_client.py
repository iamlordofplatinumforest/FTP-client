"""
FTP клиент - основной класс для работы с FTP-соединением
"""

from ftplib import FTP, FTP_TLS, error_perm
import os
from threading import Lock
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
import humanize
import time
from queue import Queue
import socket
import sys


def debug_log(message: str):
    """Принудительный вывод отладочной информации"""
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


class FTPClient:
    def __init__(self):
        self.ftp: Optional[FTP] = None
        self.ftp_lock = Lock()
        self.current_remote_dir = "/"
        self.monitor_running = False
        self.remote_cache = {}
        
    def connect(self, host: str, port: int, user: str, password: str) -> Tuple[bool, str]:
        """Подключение к FTP серверу"""
        try:
            # Проверка доступности сервера
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            if result != 0:
                return False, f"Сервер {host}:{port} недоступен"

            with self.ftp_lock:
                if self.ftp:
                    try:
                        self.ftp.quit()
                    except:
                        pass

                try:
                    self.ftp = FTP()
                    self.ftp.connect(host, port, timeout=10)
                    self.ftp.login(user=user, passwd=password)
                    self.monitor_running = True
                    return True, "Подключено успешно"
                except Exception as ftp_error:
                    if "530" in str(ftp_error):  # Ошибка аутентификации
                        return False, f"Ошибка аутентификации: неверное имя пользователя или пароль для {user}@{host}"
                    else:
                        return False, f"Ошибка подключения: {str(ftp_error)}"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"

    def disconnect(self) -> None:
        """Отключение от сервера"""
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
                    debug_log("DEBUG: FTPClient: Отключение завершено")

    def list_files(self) -> List[Tuple[str, str, str, str]]:
        """Получение списка файлов в текущей директории"""
        if not self.ftp:
            return []

        items = []
        try:
            with self.ftp_lock:
                files = []
                self.ftp.retrlines('LIST', files.append)
                
                for line in files:
                    try:
                        parts = line.split()
                        if len(parts) < 9:
                            continue
                        name = ' '.join(parts[8:])
                        is_dir = parts[0].startswith('d')
                        
                        if not is_dir:
                            try:
                                size = humanize.naturalsize(int(parts[4]))
                            except:
                                size = parts[4]
                        else:
                            try:
                                current_dir = self.ftp.pwd()
                                self.ftp.cwd(name)
                                dir_files = []
                                self.ftp.retrlines('LIST', dir_files.append)
                                size = f"{len(dir_files)} элем."
                                self.ftp.cwd(current_dir)
                            except:
                                size = "Нет доступа"
                        
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
        """Скачивание файла"""
        if not self.ftp:
            return False, "Нет подключения"

        try:
            with self.ftp_lock:
                try:
                    file_size = self.ftp.size(remote_file)
                except:
                    file_size = 1024 * 1024

                buffer_size = self._get_optimal_buffer_size(file_size)
                self.ftp.voidcmd('TYPE I')

                temp_path = local_path + '.tmp'
                with open(temp_path, 'wb') as f:
                    bytes_received = 0
                    
                    def callback(data):
                        nonlocal bytes_received
                        f.write(data)
                        bytes_received += len(data)
                        if progress_callback:
                            progress_callback(bytes_received, file_size)

                    self.ftp.retrbinary(f'RETR {remote_file}', callback, buffer_size)

                # Проверяем размер скачанного файла
                downloaded_size = os.path.getsize(temp_path)
                if downloaded_size != file_size:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    return False, "Ошибка скачивания: размер файла не совпадает"

                if os.path.exists(local_path):
                    os.remove(local_path)
                os.rename(temp_path, local_path)
                return True, "Файл успешно скачан"

        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            return False, str(e)

    def upload_file(self, local_path: str, remote_file: str, 
                   progress_callback=None) -> Tuple[bool, str]:
        """Загрузка файла"""
        if not self.ftp:
            return False, "Нет подключения"

        try:
            file_size = os.path.getsize(local_path)
            buffer_size = self._get_optimal_buffer_size(file_size)

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
        """Рекурсивная загрузка папки"""
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
        """Создание директории"""
        if not self.ftp:
            return False, "Нет подключения"

        try:
            with self.ftp_lock:
                self.ftp.mkd(dirname)
                return True, f"Папка '{dirname}' создана"
        except Exception as e:
            return False, str(e)

    def delete_item(self, name: str) -> Tuple[bool, str]:
        """Удаление файла или папки"""
        if not self.ftp:
            return False, "Нет подключения"

        debug_log(f"\nDEBUG: Начало удаления элемента: {name}")
        try:
            with self.ftp_lock:
                # Проверяем, это файл или директория
                is_dir = False
                try:
                    debug_log(f"DEBUG: Проверяем, является ли {name} директорией")
                    self.ftp.cwd(name)
                    is_dir = True
                    self.ftp.cwd('..')
                    debug_log(f"DEBUG: {name} является директорией")
                except:
                    debug_log(f"DEBUG: {name} является файлом")
                    pass

                if is_dir:
                    debug_log(f"DEBUG: Начинаем удаление директории {name}")
                    # Сохраняем текущую директорию
                    current_dir = self.ftp.pwd()
                    debug_log(f"DEBUG: Текущая директория: {current_dir}")
                    
                    try:
                        # Переходим в удаляемую директорию
                        debug_log(f"DEBUG: Переходим в директорию {name}")
                        self.ftp.cwd(name)
                        
                        # Получаем список файлов
                        files = []
                        debug_log("DEBUG: Получаем список файлов")
                        self.ftp.retrlines('LIST', lambda x: (files.append(x), debug_log(f"DEBUG: Найден элемент: {x}")))
                        
                        # Сначала собираем все файлы и папки
                        all_files = []
                        all_dirs = []
                        
                        # Обрабатываем каждый элемент
                        for item in files:
                            parts = item.split(None, 8)
                            if len(parts) < 9:
                                debug_log(f"DEBUG: Пропускаем некорректный элемент: {item}")
                                continue
                                
                            filename = parts[8]
                            if filename in ('.', '..'):
                                debug_log(f"DEBUG: Пропускаем специальный элемент: {filename}")
                                continue
                                
                            if parts[0].startswith('d'):
                                debug_log(f"DEBUG: Добавляем директорию в список: {filename}")
                                all_dirs.append(filename)
                            else:
                                debug_log(f"DEBUG: Добавляем файл в список: {filename}")
                                all_files.append(filename)
                        
                        # Сначала удаляем все файлы
                        debug_log("DEBUG: Удаляем файлы")
                        for file in all_files:
                            try:
                                debug_log(f"DEBUG: Удаляем файл: {file}")
                                self.ftp.delete(file)
                                debug_log(f"DEBUG: Файл {file} успешно удален")
                            except Exception as e:
                                debug_log(f"DEBUG: Ошибка при удалении файла {file}: {str(e)}")
                                raise
                        
                        # Возвращаемся в родительскую директорию
                        debug_log(f"DEBUG: Возвращаемся в директорию {current_dir}")
                        self.ftp.cwd(current_dir)
                        
                        # Рекурсивно удаляем поддиректории
                        debug_log("DEBUG: Удаляем поддиректории")
                        for dir_name in all_dirs:
                            try:
                                debug_log(f"DEBUG: Рекурсивно удаляем директорию: {dir_name}")
                                success, message = self.delete_item(dir_name)
                                if not success:
                                    debug_log(f"DEBUG: Ошибка при удалении директории {dir_name}: {message}")
                                    raise Exception(message)
                            except Exception as e:
                                debug_log(f"DEBUG: Ошибка при рекурсивном удалении {dir_name}: {str(e)}")
                                raise
                        
                        # Удаляем саму папку
                        debug_log(f"DEBUG: Удаляем саму папку {name}")
                        try:
                            self.ftp.rmd(name)
                            debug_log(f"DEBUG: Папка {name} успешно удалена")
                        except Exception as e:
                            debug_log(f"DEBUG: Ошибка при удалении папки {name}: {str(e)}")
                            raise
                    except Exception as e:
                        # В случае ошибки возвращаемся в исходную директорию
                        debug_log(f"DEBUG: Ошибка, возвращаемся в {current_dir}")
                        self.ftp.cwd(current_dir)
                        raise e
                else:
                    debug_log(f"DEBUG: Удаляем файл {name}")
                    self.ftp.delete(name)
                    debug_log(f"DEBUG: Файл {name} успешно удален")

                debug_log("DEBUG: Операция удаления завершена успешно")
                return True, "Успешно удалено"
        except Exception as e:
            error_msg = str(e)
            debug_log(f"DEBUG: Ошибка удаления: {error_msg}")
            return False, error_msg

    def rename_item(self, old_name: str, new_name: str) -> Tuple[bool, str]:
        """Переименование файла или папки"""
        if not self.ftp:
            return False, "Нет подключения"

        try:
            with self.ftp_lock:
                self.ftp.rename(old_name, new_name)
                return True, "Успешно переименовано"
        except Exception as e:
            return False, str(e)

    def change_directory(self, path: str) -> Tuple[bool, str]:
        """Смена текущей директории"""
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
        """Получение текущей директории"""
        if not self.ftp:
            return "/"
        try:
            with self.ftp_lock:
                return self.ftp.pwd()
        except:
            return "/"

    def _parse_ftp_time(self, time_str: str) -> str:
        """Парсинг времени из FTP-листинга"""
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
            
            if ':' in parts[2]:
                hour, minute = map(int, parts[2].split(':'))
                year = current_year
                dt = datetime(year, month, day, hour, minute)
                if dt > datetime.now():
                    dt = datetime(year - 1, month, day, hour, minute)
            else:
                year = int(parts[2])
                dt = datetime(year, month, day)
            
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return time_str

    def _get_optimal_buffer_size(self, file_size: int) -> int:
        """Определение оптимального размера буфера"""
        if file_size < 1024 * 1024:  # < 1MB
            return 8192
        elif file_size < 10 * 1024 * 1024:  # < 10MB
            return 32768
        else:  # >= 10MB
            return 65536

    def start_connection_monitor(self, on_connection_lost=None):
        """Запуск мониторинга соединения"""
        def monitor():
            check_interval = 30
            consecutive_failures = 0
            max_interval = 120
            min_interval = 10
            
            while self.monitor_running:
                try:
                    with self.ftp_lock:
                        if self.ftp:
                            start_time = time.time()
                            self.ftp.voidcmd('NOOP')
                            response_time = time.time() - start_time
                            
                            if response_time < 0.1:
                                check_interval = min(check_interval * 1.5, max_interval)
                            else:
                                check_interval = max(check_interval * 0.75, min_interval)
                                
                            consecutive_failures = 0
                            
                except:
                    consecutive_failures += 1
                    check_interval = max(check_interval * 0.5, min_interval)
                    
                    if consecutive_failures >= 3 and on_connection_lost:
                        on_connection_lost()
                        break
                        
                time.sleep(check_interval)

        from threading import Thread
        Thread(target=monitor, daemon=True).start() 