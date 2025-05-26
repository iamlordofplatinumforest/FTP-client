"""
Стили для GUI элементов
"""

from tkinter import ttk


def setup_styles():
    """Настройка стилей приложения"""
    style = ttk.Style()
    
    # Основные стили
    style.configure("Treeview",
                   rowheight=25,
                   font=('Helvetica', 10))
    
    style.configure("Treeview.Heading",
                   font=('Helvetica', 10, 'bold'))
    
    # Стили для кнопок
    style.configure("Primary.TButton",
                   padding=5,
                   font=('Helvetica', 10))
    
    style.configure("Secondary.TButton",
                   padding=5,
                   font=('Helvetica', 10))
    
    # Стили для меток
    style.configure("Status.TLabel",
                   padding=5,
                   font=('Helvetica', 10))
    
    style.configure("Error.TLabel",
                   padding=5,
                   font=('Helvetica', 10),
                   foreground='red')
    
    # Стили для фреймов
    style.configure("Panel.TLabelframe",
                   padding=10)
    
    # Стили для прогресс-бара
    style.configure("Horizontal.TProgressbar",
                   thickness=20) 