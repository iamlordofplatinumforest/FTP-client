"""
Стили для GUI компонентов
"""

from tkinter import ttk


def setup_styles():
    """Настройка стилей для виджетов"""
    style = ttk.Style()
    
    # Основная тема
    style.theme_use('clam')
    
    # Кнопки
    style.configure('TButton',
                   padding=5,
                   relief='flat',
                   background='#f0f0f0',
                   foreground='black')
    
    style.map('TButton',
              background=[('active', '#e0e0e0'),
                         ('pressed', '#d0d0d0')],
              relief=[('pressed', 'sunken')])
    
    # Метки
    style.configure('TLabel',
                   padding=2,
                   background='#f5f5f5',
                   foreground='black')
    
    # Поля ввода
    style.configure('TEntry',
                   padding=5,
                   relief='solid',
                   fieldbackground='white')
    
    # Фреймы
    style.configure('TFrame',
                   background='#f5f5f5')
    
    style.configure('TLabelframe',
                   background='#f5f5f5',
                   padding=5)
    
    style.configure('TLabelframe.Label',
                   background='#f5f5f5',
                   foreground='black',
                   padding=(5, 2))
    
    # Списки
    style.configure('Treeview',
                   background='white',
                   fieldbackground='white',
                   relief='solid',
                   borderwidth=1,
                   rowheight=25)
    
    style.configure('Treeview.Heading',
                   padding=2,
                   relief='flat',
                   background='#e0e0e0',
                   foreground='black')
    
    style.map('Treeview',
              background=[('selected', '#0078d7')],
              foreground=[('selected', 'white')])
    
    # Полоса прокрутки
    style.configure('Vertical.TScrollbar',
                   background='#f0f0f0',
                   relief='flat',
                   arrowcolor='black',
                   borderwidth=0)
    
    style.configure('Horizontal.TScrollbar',
                   background='#f0f0f0',
                   relief='flat',
                   arrowcolor='black',
                   borderwidth=0)
    
    # Панель инструментов
    style.configure('Toolbar.TFrame',
                   background='#f0f0f0',
                   relief='flat')
    
    # Статус бар
    style.configure('Statusbar.TFrame',
                   background='#f0f0f0',
                   relief='sunken')
    
    style.configure('Statusbar.TLabel',
                   background='#f0f0f0',
                   padding=(5, 2))
    
    # Панель поиска
    style.configure('Search.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=5)
    
    # Панель пути
    style.configure('Path.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=2)
    
    # Панель подключения
    style.configure('Connection.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=5)
    
    # Диалоги
    style.configure('Dialog.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=10) 