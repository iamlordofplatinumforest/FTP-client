"""
FTP клиент - основной класс для работы с FTP-соединением
"""

from ftplib import FTP, FTP_TLS, error_perm
import os
from threading import Lock
from typing import Optional, Tuple, List
from datetime import datetime
import humanize


class FTPClient:
    def __init__(self):
        self.ftp: Optional[FTP] = None
        self.ftp_lock = Lock()
        self.current_remote_dir = "/"
        
    def connect(self, host: str, port: int, user: str, password: str) -> Tuple[bool, str]:
        """Подключение к FTP серверу"""
        try:
            with self.ftp_lock:
                if self.ftp:
                    self.ftp.quit()
                self.ftp = FTP()
                self.ftp.connect(host, port, timeout=10)
                self.ftp.login(user=user, passwd=password)
                return True, "Подключено успешно"
        except Exception as e:
            return False, str(e)

    def disconnect(self) -> None:
        """Отключение от сервера"""
        with self.ftp_lock:
            if self.ftp:
                try:
                    self.ftp.quit()
                except:
                    pass
                finally:
                    self.ftp = None

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
                    def callback(data):
                        f.write(data)
                        if progress_callback:
                            progress_callback(len(data))

                    self.ftp.retrbinary(f'RETR {remote_file}', callback, buffer_size)

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
                self.ftp.voidcmd('TYPE I')
                with open(local_path, 'rb') as f:
                    def callback(data):
                        if progress_callback:
                            progress_callback(len(data))
                        return data

                    self.ftp.storbinary(f'STOR {remote_file}', f, buffer_size, callback)

                uploaded_size = self.ftp.size(remote_file)
                if uploaded_size != file_size:
                    self.ftp.delete(remote_file)
                    return False, "Ошибка загрузки: размер файла не совпадает"

                return True, "Файл успешно загружен"

        except Exception as e:
            return False, str(e)

    def _get_optimal_buffer_size(self, file_size: int) -> int:
        """Определение оптимального размера буфера"""
        if file_size < 1024 * 1024:  # < 1MB
            return 8192
        elif file_size < 10 * 1024 * 1024:  # < 10MB
            return 32768
        else:  # >= 10MB
            return 65536 