import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.main import Application

if __name__ == "__main__":
    app = Application()
    app.mainloop() 