from tkinter import ttk


def setup_styles():
    style = ttk.Style()

    style.theme_use('clam')

    style.configure('TButton',
                   padding=5,
                   relief='flat',
                   background='#f0f0f0',
                   foreground='black')
    
    style.map('TButton',
              background=[('active', '#e0e0e0'),
                         ('pressed', '#d0d0d0')],
              relief=[('pressed', 'sunken')])

    style.configure('TLabel',
                   padding=2,
                   background='#f5f5f5',
                   foreground='black')

    style.configure('TEntry',
                   padding=5,
                   relief='solid',
                   fieldbackground='white')

    style.configure('TFrame',
                   background='#f5f5f5')
    
    style.configure('TLabelframe',
                   background='#f5f5f5',
                   padding=5)
    
    style.configure('TLabelframe.Label',
                   background='#f5f5f5',
                   foreground='black',
                   padding=(5, 2))

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

    style.configure('Toolbar.TFrame',
                   background='#f0f0f0',
                   relief='flat')

    style.configure('Statusbar.TFrame',
                   background='#f0f0f0',
                   relief='sunken',
                   borderwidth=1)
    
    style.configure('Statusbar.TLabel',
                   background='#f0f0f0',
                   foreground='black',
                   font=('Helvetica', 9),
                   padding=(5, 2))
                   
    style.configure('StatusbarError.TLabel',
                   background='#f0f0f0',
                   foreground='red',
                   font=('Helvetica', 9, 'bold'),
                   padding=(5, 2))

    style.configure("Colored.Horizontal.TProgressbar",
                   troughcolor='#f0f0f0',
                   background='#4CAF50',
                   bordercolor='#f0f0f0',
                   lightcolor='#4CAF50',
                   darkcolor='#4CAF50')

    style.configure('Search.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=5)

    style.configure('Path.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=2)

    style.configure('Connection.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=5)

    style.configure('Dialog.TFrame',
                   background='#f5f5f5',
                   relief='flat',
                   padding=10) 