"""Acceso a la base de datos (SQLite), auditoría y utilidades comunes."""
import json
import os
import sqlite3
import unicodedata
from datetime import datetime

from flask import current_app, g, has_request_context, request, session

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")


def norm(s):
    """Minúsculas y sin acentos (para búsquedas)."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def connect(path):
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 15000")
    con.create_function("norm", 1, norm, deterministic=True)
    return con


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def init_db(path):
    """Crea la base de datos vacía a partir de schema.sql."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = connect(path)
    con.execute("PRAGMA journal_mode = WAL")
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        con.executescript(fh.read())
    con.commit()
    con.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def q(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def q1(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def ex(sql, params=(), commit=True):
    con = get_db()
    cur = con.execute(sql, params)
    if commit:
        con.commit()
    return cur


def commit():
    get_db().commit()


def current_uid():
    return session.get("uid") if has_request_context() else None


def audit(tabla, registro_id, accion, detalle=None, commit_now=False):
    """Registra una operación en historial_cambios."""
    nombre = None
    ip = None
    if has_request_context():
        user = getattr(g, "user", None)
        nombre = user["nombre"] if user else None
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip:
            ip = ip.split(",")[0].strip()
    ex(
        "INSERT INTO historial_cambios(fecha, usuario_id, usuario_nombre, tabla, registro_id, accion, detalle, ip) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (now(), current_uid(), nombre, tabla, registro_id, accion,
         json.dumps(detalle, ensure_ascii=False, default=str) if detalle is not None else None, ip),
        commit=commit_now,
    )


def diff(antes, despues):
    """Devuelve {campo: [antes, despues]} sólo con los campos que cambiaron."""
    out = {}
    for k, v in despues.items():
        old = antes.get(k)
        if (old if old != "" else None) != (v if v != "" else None):
            out[k] = [old, v]
    return out


def get_config(clave, default=None):
    row = q1("SELECT valor FROM configuracion WHERE clave = ?", (clave,))
    return row["valor"] if row and row["valor"] not in (None, "") else default


def all_config():
    return {r["clave"]: r["valor"] for r in q("SELECT clave, valor FROM configuracion")}


def set_config(clave, valor):
    ex("INSERT INTO configuracion(clave, valor) VALUES (?,?) "
       "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, valor), commit=False)
