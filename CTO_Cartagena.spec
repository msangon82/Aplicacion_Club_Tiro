# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static',    'static'),
    ],
    hiddenimports=[
        'flask_login',
        'bcrypt',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.utils',
        'werkzeug.security',
        '_cffi_backend',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CTO_Cartagena',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # muestra ventana de consola con estado del servidor
    icon=None,
)
