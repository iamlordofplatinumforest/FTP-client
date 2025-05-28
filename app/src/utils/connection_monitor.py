import socket
import threading
import time
from typing import Dict, Optional

class ConnectionMonitor:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.running = False
        self.stats: Dict[str, float] = {
            'latency': 0.0,
            'packet_loss': 0.0,
            'last_check': 0.0
        }
        self.monitor_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def start_monitoring(self):
        """Запуск мониторинга в отдельном потоке"""
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()

    def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self.running:
            try:
                # Создаем сокет для проверки соединения
                start_time = time.time()
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(2.0)
                    result = sock.connect_ex((self.host, self.port))
                    end_time = time.time()
                    
                with self.lock:
                    if result == 0:
                        self.stats['latency'] = (end_time - start_time) * 1000  # в миллисекундах
                        self.stats['packet_loss'] = 0.0
                    else:
                        self.stats['packet_loss'] = 100.0
                    self.stats['last_check'] = time.time()
                    
            except Exception:
                with self.lock:
                    self.stats['packet_loss'] = 100.0
                    self.stats['latency'] = 0.0
                    self.stats['last_check'] = time.time()
            
            time.sleep(1)  # Проверка каждую секунду

    def get_stats(self) -> Dict[str, float]:
        """Получение текущей статистики"""
        with self.lock:
            return self.stats.copy() 