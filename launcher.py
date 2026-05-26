"""
Punto de entrada para el ejecutable standalone.
Parchea rutas de Flask antes de arrancar para que funcione
tanto en desarrollo como empaquetado con PyInstaller.
"""
import sys, os, threading, webbrowser, time

# ── Rutas base ──────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _BASE = sys._MEIPASS                         # templates/static extraídos por PyInstaller
    _DATA = os.path.dirname(sys.executable)      # la BD vive junto al .exe
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
    _DATA = _BASE

# ── Importar app y aplicar rutas correctas ──────────────
import app as m
from jinja2 import FileSystemLoader

m.DB_PATH                  = os.path.join(_DATA, 'tiradores.db')
m.app.template_folder      = os.path.join(_BASE, 'templates')
m.app.jinja_loader         = FileSystemLoader(os.path.join(_BASE, 'templates'))
m.app.static_folder        = os.path.join(_BASE, 'static')
m.app.static_url_path      = '/static'

# ── Inicializar BD ──────────────────────────────────────
m.init_db()

# ── Abrir navegador tras arrancar ───────────────────────
def _abrir():
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')

threading.Thread(target=_abrir, daemon=True).start()

print("=" * 48)
print("  C.T.O. Cartagena — Sistema de gestión")
print("  Abriendo en http://127.0.0.1:5000 ...")
print("  Cierra esta ventana para detener el servidor.")
print("=" * 48)

m.app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
