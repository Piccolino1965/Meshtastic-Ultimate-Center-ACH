#!/usr/bin/env python3
# Entry point - avvia l'applicazione
# aiutocomputerhelp.it
# Giovanni Popolizio - anon@m00n
###################################

import tkinter as tk
from tkinter import ttk
from i18n import load_language
from gui import MeshtasticUltimateCenter

if __name__ == "__main__":
    load_language()
    root = tk.Tk()
    try:
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
    except:
        pass
    
    app = MeshtasticUltimateCenter(root)
    root.mainloop()
