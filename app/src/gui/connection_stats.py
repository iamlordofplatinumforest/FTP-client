import tkinter as tk
from tkinter import ttk
import time
from src.utils.connection_monitor import ConnectionMonitor

class ConnectionStatsPanel(ttk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text="Статистика соединения")
        
           
        self.latency_label = ttk.Label(self, text="Задержка: --")
        self.latency_label.pack(anchor="w", padx=5, pady=2)
        
        self.packet_loss_label = ttk.Label(self, text="Потери пакетов: --")
        self.packet_loss_label.pack(anchor="w", padx=5, pady=2)
        
        self.last_check_label = ttk.Label(self, text="Последняя проверка: --")
        self.last_check_label.pack(anchor="w", padx=5, pady=2)
        
        self.monitor = None
        
    def start_monitoring(self, host: str, port: int):
        if self.monitor:
            self.stop_monitoring()
            
        self.monitor = ConnectionMonitor(host, port)
        self.monitor.start_monitoring()
        self.update_stats()
        
    def stop_monitoring(self):
        if self.monitor:
            self.monitor.stop_monitoring()
            self.monitor = None

        self.latency_label.config(text="Задержка: --")
        self.packet_loss_label.config(text="Потери пакетов: --")
        self.last_check_label.config(text="Последняя проверка: --")
            
    def update_stats(self):
        if self.monitor:
            stats = self.monitor.get_stats()

            latency = stats['latency']
            if latency > 0:
                latency_text = f"Задержка: {latency:.1f} мс"
            else:
                latency_text = "Задержка: --"
            self.latency_label.config(text=latency_text)

            packet_loss = stats['packet_loss']
            if packet_loss >= 0:
                packet_loss_text = f"Потери пакетов: {packet_loss:.1f}%"
            else:
                packet_loss_text = "Потери пакетов: --"
            self.packet_loss_label.config(text=packet_loss_text)

            last_check = stats['last_check']
            if last_check > 0:
                last_check_time = time.strftime("%H:%M:%S", time.localtime(last_check))
                last_check_text = f"Последняя проверка: {last_check_time}"
            else:
                last_check_text = "Последняя проверка: --"
            self.last_check_label.config(text=last_check_text)

            self.after(500, self.update_stats) 