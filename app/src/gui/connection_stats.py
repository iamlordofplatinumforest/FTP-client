import tkinter as tk
from tkinter import ttk
import time
from src.utils.connection_monitor import ConnectionMonitor

class ConnectionStatsPanel(ttk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text="Статистика соединения")
        
        # Создаем метки для отображения статистики
        self.latency_label = ttk.Label(self, text="Задержка: --")
        self.latency_label.pack(anchor="w", padx=5, pady=2)
        
        self.packet_loss_label = ttk.Label(self, text="Потери пакетов: --")
        self.packet_loss_label.pack(anchor="w", padx=5, pady=2)
        
        self.last_check_label = ttk.Label(self, text="Последняя проверка: --")
        self.last_check_label.pack(anchor="w", padx=5, pady=2)
        
        self.monitor = None
        
    def start_monitoring(self, host: str, port: int):
        """Запуск мониторинга для указанного хоста"""
        if self.monitor:
            self.stop_monitoring()
            
        self.monitor = ConnectionMonitor(host, port)
        self.monitor.start_monitoring()
        self.update_stats()
        
    def stop_monitoring(self):
        """Остановка мониторинга"""
        if self.monitor:
            self.monitor.stop_monitoring()
            self.monitor = None
            
        # Сбрасываем метки
        self.latency_label.config(text="Задержка: --")
        self.packet_loss_label.config(text="Потери пакетов: --")
        self.last_check_label.config(text="Последняя проверка: --")
            
    def update_stats(self):
        """Обновление отображаемой статистики"""
        if self.monitor:
            stats = self.monitor.get_stats()
            self.latency_label.config(
                text=f"Задержка: {stats['latency']:.1f} мс")
            self.packet_loss_label.config(
                text=f"Потери пакетов: {stats['packet_loss']:.1f}%")
            self.last_check_label.config(
                text=f"Последняя проверка: {time.strftime('%H:%M:%S')}")
        
        # Планируем следующее обновление
        self.after(1000, self.update_stats) 