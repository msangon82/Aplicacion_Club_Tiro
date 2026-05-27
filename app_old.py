"""
Club de Tiro Olímpico de Cartagena
Calculadora de Puntuación - Aplicación web con base de datos SQLite
"""

import sqlite3, os, json, bcrypt
from functools import wraps
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, g
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cto_cartagena_2026_changeme")
DB_PATH = os.path.join(os.path.dirname(__file__), "tiradores.db")

# ─────────────────────────────────────────
#  FLASK-LOGIN
# ─────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesión para continuar."

class User(UserMixin):
    def __init__(self, id, username, rol, tirador_id=None):
        self.id         = str(id)
        self.username   = username
        self.rol        = rol
        self.tirador_id = tirador_id

@login_manager.user_loader
def load_user(user_id):
    db  = get_db()
    row = db.execute("SELECT * FROM usuarios WHERE id=? AND activo=1", (user_id,)).fetchone()
    if row:
        return User(row["id"], row["username"], row["rol"], row["tirador_id"])
    return None

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.rol not in roles:
                return render_template("403.html"), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ─────────────────────────────────────────
#  BASE DE DATOS
# ─────────────────────────────────────────
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tiradores (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre    TEXT NOT NULL,
                apellidos TEXT NOT NULL,
                dni       TEXT UNIQUE NOT NULL,
                licencia  TEXT,
                club      TEXT,
                categoria TEXT
            );

            CREATE TABLE IF NOT EXISTS competiciones (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre    TEXT NOT NULL,
                fecha     TEXT,
                modalidad TEXT DEFAULT 'Pistola Standard'
            );

            CREATE TABLE IF NOT EXISTS inscripciones (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                competicion_id     INTEGER NOT NULL,
                tirador_id         INTEGER NOT NULL,
                puesto             INTEGER NOT NULL,
                pagado             INTEGER DEFAULT 0,
                ocultar_categoria  INTEGER DEFAULT 0,
                FOREIGN KEY (competicion_id) REFERENCES competiciones(id),
                FOREIGN KEY (tirador_id)     REFERENCES tiradores(id),
                UNIQUE(competicion_id, puesto)
            );

            CREATE TABLE IF NOT EXISTS puntuaciones (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                inscripcion_id INTEGER NOT NULL,
                serie          INTEGER NOT NULL,
                d1 REAL DEFAULT 0, d2 REAL DEFAULT 0, d3 REAL DEFAULT 0,
                d4 REAL DEFAULT 0, d5 REAL DEFAULT 0,
                FOREIGN KEY (inscripcion_id) REFERENCES inscripciones(id),
                UNIQUE(inscripcion_id, serie)
            );

            CREATE TABLE IF NOT EXISTS municion_stock (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                calibre TEXT UNIQUE NOT NULL,
                stock   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS municion_movimientos (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha      TEXT NOT NULL,
                tipo       TEXT NOT NULL,
                calibre    TEXT NOT NULL,
                cantidad   INTEGER NOT NULL,
                tirador_id INTEGER,
                notas      TEXT,
                FOREIGN KEY (tirador_id) REFERENCES tiradores(id)
            );

            CREATE TABLE IF NOT EXISTS usuarios (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                rol        TEXT NOT NULL DEFAULT 'tirador',
                tirador_id INTEGER,
                activo     INTEGER DEFAULT 1,
                FOREIGN KEY (tirador_id) REFERENCES tiradores(id)
            );
        """)
        db.commit()

        # Migraciones para bases de datos existentes
        for sql in [
            "ALTER TABLE inscripciones ADD COLUMN ocultar_categoria INTEGER DEFAULT 0",
        ]:
            try:
                db.execute(sql)
                db.commit()
            except Exception:
                pass

        # Stock inicial de calibres
        for cal in ['.32 S&W', '9 PB', '.38 SPL', '.22lr']:
            try:
                db.execute("INSERT INTO municion_stock (calibre, stock) VALUES (?,0)", (cal,))
            except sqlite3.IntegrityError:
                pass

        # Datos de muestra tiradores
        sample = [
            ("Miguel Alejandro", "Díaz Montero",    "15481552E", "10382", "Cartagena", "Tercera"),
            ("Cosme Jose",       "Martínez Frutos",  "23020490C", "5432",  "Cartagena", "Segunda"),
            ("Francisco",        "Zaplana Calleja",  "22933078P", "3453",  "Cartagena", "Primera"),
            ("Alfonso",          "Asensio Perez",    "74423434B", "9262",  "Lorca",     "Tercera"),
            ("Jose",             "Balastegui Monzon","22904494J", "6096",  "Cartagena", "Veteranos"),
            ("Carmelo",          "Pagan Rebollo",    "22985423M", "4964",  "Cartagena", "Segunda"),
        ]
        for t in sample:
            try:
                db.execute(
                    "INSERT INTO tiradores (nombre,apellidos,dni,licencia,club,categoria) VALUES (?,?,?,?,?,?)", t)
            except sqlite3.IntegrityError:
                pass

        # Admin por defecto si no existe ningún usuario
        if not db.execute("SELECT 1 FROM usuarios").fetchone():
            pw = bcrypt.hashpw(b"admin1234", bcrypt.gensalt()).decode()
            db.execute(
                "INSERT INTO usuarios (username,password,rol) VALUES (?,?,?)",
                ("admin", pw, "admin"))

        db.commit()

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
CATEGORIAS = ["Primera", "Segunda", "Tercera", "Veteranos", "Junior", "Femenino"]
CALIBRES   = [".32 S&W", "9 PB", ".38 SPL", ".22lr"]
SERIES_150 = [1, 2, 3, 4]
SERIES_20  = [5, 6, 7, 8, 9, 10]
ROLES      = ["admin", "encargado", "arbitro", "directiva", "tirador"]

ROL_LABELS = {
    "admin":     "Administrador",
    "encargado": "Encargado",
    "arbitro":   "Árbitro",
    "directiva": "Directiva",
    "tirador":   "Tirador",
}

def calcular_suma_serie(d1, d2, d3, d4, d5):
    total = 0
    for v in [d1, d2, d3, d4, d5]:
        try:
            total += float(v) if str(v).lower() != 'x' else 10
        except:
            pass
    return total

def calcular_total_inscripcion(insc_id, db):
    filas = db.execute(
        "SELECT d1,d2,d3,d4,d5 FROM puntuaciones WHERE inscripcion_id=?", (insc_id,)
    ).fetchall()
    return sum(calcular_suma_serie(r["d1"],r["d2"],r["d3"],r["d4"],r["d5"]) for r in filas)

def get_stocks(db):
    rows = db.execute("SELECT calibre, stock FROM municion_stock ORDER BY calibre").fetchall()
    return {r["calibre"]: r["stock"] for r in rows}

# ─────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────
@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].encode("utf-8")
        db  = get_db()
        row = db.execute("SELECT * FROM usuarios WHERE username=? AND activo=1", (username,)).fetchone()
        if row and bcrypt.checkpw(password, row["password"].encode("utf-8")):
            user = User(row["id"], row["username"], row["rol"], row["tirador_id"])
            login_user(user)
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ─────────────────────────────────────────
#  USUARIOS (solo admin)
# ─────────────────────────────────────────
@app.route("/usuarios")
@role_required("admin")
def usuarios():
    db    = get_db()
    lista = db.execute("""
        SELECT u.*, t.nombre as t_nombre, t.apellidos as t_apellidos
        FROM usuarios u
        LEFT JOIN tiradores t ON t.id = u.tirador_id
        ORDER BY u.id
    """).fetchall()
    return render_template("usuarios.html", usuarios=lista, rol_labels=ROL_LABELS)

@app.route("/usuarios/nuevo", methods=["GET","POST"])
@role_required("admin")
def usuario_nuevo():
    db        = get_db()
    tiradores = db.execute("SELECT id,nombre,apellidos FROM tiradores ORDER BY apellidos").fetchall()
    error     = None
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        rol      = request.form["rol"]
        tid      = request.form.get("tirador_id") or None
        if not username or not password:
            error = "Usuario y contraseña son obligatorios."
        else:
            pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()
            try:
                db.execute(
                    "INSERT INTO usuarios (username,password,rol,tirador_id) VALUES (?,?,?,?)",
                    (username, pw, rol, tid))
                db.commit()
                return redirect(url_for("usuarios"))
            except sqlite3.IntegrityError:
                error = "El nombre de usuario ya existe."
    return render_template("usuario_form.html", u=None, roles=ROLES,
                           rol_labels=ROL_LABELS, tiradores=tiradores, error=error)

@app.route("/usuarios/<int:uid>/editar", methods=["GET","POST"])
@role_required("admin")
def usuario_editar(uid):
    db  = get_db()
    row = db.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not row:
        return redirect(url_for("usuarios"))
    tiradores = db.execute("SELECT id,nombre,apellidos FROM tiradores ORDER BY apellidos").fetchall()
    error     = None
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        rol      = request.form["rol"]
        tid      = request.form.get("tirador_id") or None
        activo   = 1 if request.form.get("activo") else 0
        new_pw   = request.form.get("password","").strip()
        try:
            if new_pw:
                pw = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode()
                db.execute(
                    "UPDATE usuarios SET username=?,password=?,rol=?,tirador_id=?,activo=? WHERE id=?",
                    (username, pw, rol, tid, activo, uid))
            else:
                db.execute(
                    "UPDATE usuarios SET username=?,rol=?,tirador_id=?,activo=? WHERE id=?",
                    (username, rol, tid, activo, uid))
            db.commit()
            return redirect(url_for("usuarios"))
        except sqlite3.IntegrityError:
            error = "El nombre de usuario ya existe."
    return render_template("usuario_form.html", u=row, roles=ROLES,
                           rol_labels=ROL_LABELS, tiradores=tiradores, error=error)

@app.route("/usuarios/<int:uid>/eliminar", methods=["POST"])
@role_required("admin")
def usuario_eliminar(uid):
    if str(uid) == current_user.id:
        return redirect(url_for("usuarios"))
    db = get_db()
    db.execute("DELETE FROM usuarios WHERE id=?", (uid,))
    db.commit()
    return redirect(url_for("usuarios"))

# ─────────────────────────────────────────
#  INICIO
# ─────────────────────────────────────────
@app.route("/")
@login_required
def index():
    db = get_db()
    n_tiradores     = db.execute("SELECT COUNT(*) FROM tiradores").fetchone()[0]
    n_competiciones = db.execute("SELECT COUNT(*) FROM competiciones").fetchone()[0]
    ultimas = db.execute("SELECT * FROM competiciones ORDER BY id DESC LIMIT 5").fetchall()
    stocks  = get_stocks(db)
    return render_template("index.html",
        n_tiradores=n_tiradores,
        n_competiciones=n_competiciones,
        ultimas=ultimas,
        stocks=stocks)

# ─────────────────────────────────────────
#  TIRADORES
# ─────────────────────────────────────────
@app.route("/tiradores")
@role_required("admin","encargado","directiva")
def tiradores():
    db  = get_db()
    q   = request.args.get("q","").strip()
    cat = request.args.get("cat","")
    query  = "SELECT * FROM tiradores WHERE 1=1"
    params = []
    if q:
        query += " AND (nombre LIKE ? OR apellidos LIKE ? OR dni LIKE ? OR licencia LIKE ?)"
        params += [f"%{q}%"]*4
    if cat:
        query += " AND categoria=?"
        params.append(cat)
    query += " ORDER BY apellidos, nombre"
    lista = db.execute(query, params).fetchall()
    return render_template("tiradores.html", tiradores=lista,
        categorias=CATEGORIAS, q=q, cat=cat)

@app.route("/tiradores/nuevo", methods=["GET","POST"])
@role_required("admin","encargado")
def tirador_nuevo():
    if request.method == "POST":
        db = get_db()
        try:
            db.execute(
                "INSERT INTO tiradores (nombre,apellidos,dni,licencia,club,categoria) VALUES (?,?,?,?,?,?)",
                (request.form["nombre"], request.form["apellidos"],
                 request.form["dni"],    request.form["licencia"],
                 request.form["club"],   request.form["categoria"]))
            db.commit()
            return redirect(url_for("tiradores"))
        except sqlite3.IntegrityError:
            return render_template("tirador_form.html",
                categorias=CATEGORIAS, error="El DNI ya existe en la base de datos.", t=None)
    return render_template("tirador_form.html", categorias=CATEGORIAS, error=None, t=None)

@app.route("/tiradores/<int:tid>/editar", methods=["GET","POST"])
@role_required("admin","encargado")
def tirador_editar(tid):
    db = get_db()
    t  = db.execute("SELECT * FROM tiradores WHERE id=?", (tid,)).fetchone()
    if not t:
        return redirect(url_for("tiradores"))
    if request.method == "POST":
        try:
            db.execute(
                "UPDATE tiradores SET nombre=?,apellidos=?,dni=?,licencia=?,club=?,categoria=? WHERE id=?",
                (request.form["nombre"], request.form["apellidos"],
                 request.form["dni"],    request.form["licencia"],
                 request.form["club"],   request.form["categoria"], tid))
            db.commit()
            return redirect(url_for("tiradores"))
        except sqlite3.IntegrityError:
            return render_template("tirador_form.html",
                categorias=CATEGORIAS, error="El DNI ya existe.", t=t)
    return render_template("tirador_form.html", categorias=CATEGORIAS, error=None, t=t)

@app.route("/tiradores/<int:tid>/eliminar", methods=["POST"])
@role_required("admin","encargado")
def tirador_eliminar(tid):
    db = get_db()
    db.execute("DELETE FROM tiradores WHERE id=?", (tid,))
    db.commit()
    return redirect(url_for("tiradores"))

# ─────────────────────────────────────────
#  COMPETICIONES
# ─────────────────────────────────────────
@app.route("/competiciones")
@login_required
def competiciones():
    db = get_db()
    lista = db.execute("SELECT * FROM competiciones ORDER BY id DESC").fetchall()
    return render_template("competiciones.html", competiciones=lista)

@app.route("/competiciones/nueva", methods=["GET","POST"])
@role_required("admin","encargado")
def competicion_nueva():
    if request.method == "POST":
        db = get_db()
        db.execute("INSERT INTO competiciones (nombre,fecha,modalidad) VALUES (?,?,?)",
            (request.form["nombre"], request.form["fecha"], request.form["modalidad"]))
        db.commit()
        return redirect(url_for("competiciones"))
    return render_template("competicion_form.html", c=None)

@app.route("/competiciones/<int:cid>")
@login_required
def competicion_ver(cid):
    db   = get_db()
    comp = db.execute("SELECT * FROM competiciones WHERE id=?", (cid,)).fetchone()
    if not comp:
        return redirect(url_for("competiciones"))

    insc_rows = db.execute("""
        SELECT i.id, i.puesto, i.pagado,
               t.id as tid, t.nombre, t.apellidos, t.dni, t.licencia, t.club, t.categoria
        FROM inscripciones i
        JOIN tiradores t ON t.id = i.tirador_id
        WHERE i.competicion_id = ?
        ORDER BY i.puesto
    """, (cid,)).fetchall()

    inscripciones = []
    for row in insc_rows:
        total = calcular_total_inscripcion(row["id"], db)
        inscripciones.append(dict(row) | {"total": total})

    clasificacion = sorted([i for i in inscripciones if i["total"] > 0],
                           key=lambda x: -x["total"])
    por_cat = {}
    for i in clasificacion:
        por_cat.setdefault(i["categoria"], []).append(i)

    disponibles = []
    if current_user.rol in ("admin", "encargado"):
        inscritos_ids = [i["tid"] for i in inscripciones]
        disponibles = db.execute(
            f"SELECT * FROM tiradores {'WHERE id NOT IN ('+','.join('?'*len(inscritos_ids))+')' if inscritos_ids else ''} ORDER BY apellidos",
            inscritos_ids
        ).fetchall()

    return render_template("competicion_ver.html",
        comp=comp, inscripciones=inscripciones,
        clasificacion=clasificacion, por_cat=por_cat,
        disponibles=disponibles, categorias=CATEGORIAS)

@app.route("/competiciones/<int:cid>/imprimir")
@login_required
def competicion_imprimir(cid):
    db   = get_db()
    comp = db.execute("SELECT * FROM competiciones WHERE id=?", (cid,)).fetchone()
    if not comp:
        return redirect(url_for("competiciones"))

    insc_rows = db.execute("""
        SELECT i.id, i.puesto, i.pagado, i.ocultar_categoria,
               t.id as tid, t.nombre, t.apellidos, t.dni, t.licencia, t.club, t.categoria
        FROM inscripciones i
        JOIN tiradores t ON t.id = i.tirador_id
        WHERE i.competicion_id = ?
        ORDER BY i.puesto
    """, (cid,)).fetchall()

    inscripciones = []
    for row in insc_rows:
        total = calcular_total_inscripcion(row["id"], db)
        inscripciones.append(dict(row) | {"total": total})

    visibles = [i for i in inscripciones if not i["ocultar_categoria"]]
    clasificacion = sorted([i for i in visibles if i["total"] > 0],
                           key=lambda x: -x["total"])
    por_cat = {}
    for i in clasificacion:
        por_cat.setdefault(i["categoria"], []).append(i)

    sin_puntos = [i for i in visibles if i["total"] == 0]
    for i in sin_puntos:
        por_cat.setdefault(i["categoria"], [])

    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    return render_template("competicion_imprimir.html", now=now,
        comp=comp, clasificacion=clasificacion, por_cat=por_cat)

@app.route("/competiciones/<int:cid>/inscribir", methods=["POST"])
@role_required("admin","encargado")
def inscribir(cid):
    db                = get_db()
    tid               = request.form["tirador_id"]
    puesto            = request.form["puesto"]
    pagado            = 1 if request.form.get("pagado") else 0
    ocultar_categoria = 1 if request.form.get("ocultar_categoria") else 0
    try:
        db.execute(
            "INSERT INTO inscripciones (competicion_id,tirador_id,puesto,pagado,ocultar_categoria) VALUES (?,?,?,?,?)",
            (cid, tid, puesto, pagado, ocultar_categoria))
        db.commit()
    except sqlite3.IntegrityError:
        pass
    return redirect(url_for("competicion_ver", cid=cid))

@app.route("/inscripciones/<int:iid>/eliminar", methods=["POST"])
@role_required("admin","encargado")
def inscripcion_eliminar(iid):
    db  = get_db()
    row = db.execute("SELECT competicion_id FROM inscripciones WHERE id=?", (iid,)).fetchone()
    cid = row["competicion_id"] if row else None
    db.execute("DELETE FROM puntuaciones WHERE inscripcion_id=?", (iid,))
    db.execute("DELETE FROM inscripciones WHERE id=?", (iid,))
    db.commit()
    return redirect(url_for("competicion_ver", cid=cid))

# ─────────────────────────────────────────
#  PUNTUACIONES
# ─────────────────────────────────────────
@app.route("/puntuaciones/<int:iid>", methods=["GET","POST"])
@login_required
def puntuaciones(iid):
    db   = get_db()
    insc = db.execute("""
        SELECT i.*, t.nombre, t.apellidos, t.categoria, t.club,
               c.nombre as comp_nombre, c.id as cid
        FROM inscripciones i
        JOIN tiradores t ON t.id=i.tirador_id
        JOIN competiciones c ON c.id=i.competicion_id
        WHERE i.id=?
    """, (iid,)).fetchone()
    if not insc:
        return redirect(url_for("competiciones"))

    # Tirador solo puede ver sus propias puntuaciones
    if current_user.rol == "tirador":
        if current_user.tirador_id != insc["tirador_id"]:
            return render_template("403.html"), 403

    can_edit = current_user.rol in ("admin", "encargado", "arbitro")

    if request.method == "POST":
        if not can_edit:
            return render_template("403.html"), 403
        for serie in range(1, 11):
            d = [request.form.get(f"s{serie}_d{j}", 0) for j in range(1,6)]
            db.execute("""
                INSERT INTO puntuaciones (inscripcion_id,serie,d1,d2,d3,d4,d5)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(inscripcion_id,serie) DO UPDATE SET
                  d1=excluded.d1, d2=excluded.d2, d3=excluded.d3,
                  d4=excluded.d4, d5=excluded.d5
            """, [iid, serie] + d)
        db.commit()
        return redirect(url_for("competicion_ver", cid=insc["cid"]))

    series = {}
    for row in db.execute("SELECT * FROM puntuaciones WHERE inscripcion_id=? ORDER BY serie", (iid,)):
        series[row["serie"]] = row
    total = calcular_total_inscripcion(iid, db)

    return render_template("puntuaciones.html",
        insc=insc, series=series, total=total,
        series_150=SERIES_150, series_20=SERIES_20,
        can_edit=can_edit)

@app.route("/api/puntuacion", methods=["POST"])
@login_required
def api_puntuacion():
    if current_user.rol not in ("admin", "encargado", "arbitro"):
        return jsonify({"ok": False, "error": "Sin permiso"}), 403
    data  = request.json
    iid   = data["inscripcion_id"]
    serie = data["serie"]
    campo = data["campo"]
    valor = data["valor"]
    db    = get_db()
    db.execute(f"""
        INSERT INTO puntuaciones (inscripcion_id,serie,{campo})
        VALUES (?,?,?)
        ON CONFLICT(inscripcion_id,serie) DO UPDATE SET {campo}=excluded.{campo}
    """, (iid, serie, valor))
    db.commit()
    total      = calcular_total_inscripcion(iid, db)
    row        = db.execute("SELECT d1,d2,d3,d4,d5 FROM puntuaciones WHERE inscripcion_id=? AND serie=?",
                            (iid, serie)).fetchone()
    suma_serie = calcular_suma_serie(*row) if row else 0
    return jsonify({"ok": True, "total": total, "suma_serie": suma_serie})

# ─────────────────────────────────────────
#  MUNICIÓN
# ─────────────────────────────────────────
@app.route("/municion")
@role_required("admin","encargado","directiva")
def municion():
    db        = get_db()
    stocks    = get_stocks(db)
    q         = request.args.get("q","").strip()
    calibre_f = request.args.get("calibre","")
    tipo_f    = request.args.get("tipo","")

    query  = """
        SELECT m.*, t.nombre, t.apellidos, t.licencia
        FROM municion_movimientos m
        LEFT JOIN tiradores t ON t.id = m.tirador_id
        WHERE 1=1
    """
    params = []
    if q:
        query += " AND (t.nombre LIKE ? OR t.apellidos LIKE ? OR t.licencia LIKE ?)"
        params += [f"%{q}%"]*3
    if calibre_f:
        query += " AND m.calibre=?"
        params.append(calibre_f)
    if tipo_f:
        query += " AND m.tipo=?"
        params.append(tipo_f)
    query += " ORDER BY m.id DESC"

    movimientos = db.execute(query, params).fetchall()
    tiradores   = db.execute("SELECT id,nombre,apellidos,licencia FROM tiradores ORDER BY apellidos").fetchall()

    today = date.today().strftime('%Y-%m-%d')
    return render_template("municion.html", today=today,
        stocks=stocks, movimientos=movimientos,
        tiradores=tiradores, calibres=CALIBRES,
        q=q, calibre_f=calibre_f, tipo_f=tipo_f)

@app.route("/municion/entrada", methods=["POST"])
@role_required("admin","encargado")
def municion_entrada():
    db       = get_db()
    calibre  = request.form["calibre"]
    cantidad = int(request.form["cantidad"])
    fecha    = request.form["fecha"]
    notas    = request.form.get("notas","")
    db.execute(
        "INSERT INTO municion_movimientos (fecha,tipo,calibre,cantidad,notas) VALUES (?,?,?,?,?)",
        (fecha, "entrada", calibre, cantidad, notas))
    db.execute(
        "UPDATE municion_stock SET stock = stock + ? WHERE calibre=?",
        (cantidad, calibre))
    db.commit()
    return redirect(url_for("municion"))

@app.route("/municion/salida", methods=["POST"])
@role_required("admin","encargado")
def municion_salida():
    db         = get_db()
    calibre    = request.form["calibre"]
    cantidad   = int(request.form["cantidad"])
    fecha      = request.form["fecha"]
    tirador_id = request.form.get("tirador_id") or None
    notas      = request.form.get("notas","")
    stock_row  = db.execute("SELECT stock FROM municion_stock WHERE calibre=?", (calibre,)).fetchone()
    stock_actual = stock_row["stock"] if stock_row else 0
    if cantidad > stock_actual:
        return redirect(url_for("municion") + "?error=stock")
    db.execute(
        "INSERT INTO municion_movimientos (fecha,tipo,calibre,cantidad,tirador_id,notas) VALUES (?,?,?,?,?,?)",
        (fecha, "salida", calibre, cantidad, tirador_id, notas))
    db.execute(
        "UPDATE municion_stock SET stock = stock - ? WHERE calibre=?",
        (cantidad, calibre))
    db.commit()
    return redirect(url_for("municion"))

@app.route("/municion/<int:mid>/eliminar", methods=["POST"])
@role_required("admin","encargado")
def municion_eliminar(mid):
    db  = get_db()
    mov = db.execute("SELECT * FROM municion_movimientos WHERE id=?", (mid,)).fetchone()
    if mov:
        if mov["tipo"] == "entrada":
            db.execute("UPDATE municion_stock SET stock = stock - ? WHERE calibre=?",
                       (mov["cantidad"], mov["calibre"]))
        else:
            db.execute("UPDATE municion_stock SET stock = stock + ? WHERE calibre=?",
                       (mov["cantidad"], mov["calibre"]))
        db.execute("DELETE FROM municion_movimientos WHERE id=?", (mid,))
        db.commit()
    return redirect(url_for("municion"))

if __name__ == "__main__":
    init_db()
    print("✓ Base de datos inicializada")
    print("  Usuario admin por defecto: admin / admin1234")
    print("✓ Abriendo en http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
