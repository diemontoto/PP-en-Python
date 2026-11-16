#!/usr/bin/env python3
"""Utilidades de administración: init-db, create-admin, seed-demo, backup, run."""
import argparse
import getpass
import sys

from app import create_app, backup
from app.auth import hash_password, validate_password
from app.db import commit, ex, get_db, q1


def cmd_init_db(app, a):
    print("Base de datos lista en:", app.config["DATABASE"])


def cmd_create_admin(app, a):
    with app.app_context():
        get_db()
        pw = a.password or getpass.getpass("Contraseña: ")
        msg = validate_password(pw, a.username)
        if msg:
            sys.exit("Contraseña inválida: " + msg)
        rol = q1("SELECT id FROM roles WHERE codigo = 'admin'")
        if q1("SELECT 1 FROM usuarios WHERE username = ? AND eliminado_en IS NULL", (a.username,)):
            ex("UPDATE usuarios SET password_hash = ?, debe_cambiar_clave = 1, activo = 1, intentos_fallidos = 0, bloqueado_hasta = NULL "
               "WHERE username = ?", (hash_password(pw), a.username), commit=False)
            print("Contraseña restablecida para", a.username)
        else:
            ex("INSERT INTO usuarios(username, nombre, password_hash, rol_id, activo, debe_cambiar_clave) VALUES (?,?,?,?,1,1)",
               (a.username, a.nombre, hash_password(pw), rol["id"]), commit=False)
            print("Administrador creado:", a.username)
        commit()


def cmd_bootstrap(app, a):
    """Arranque de contenedor: crea la base y, si no hay usuarios, el administrador inicial (PP_ADMIN_USER / PP_ADMIN_PASSWORD)."""
    import os
    import secrets
    with app.app_context():
        get_db()
        if q1("SELECT 1 FROM usuarios WHERE eliminado_en IS NULL"):
            return
        user = os.environ.get("PP_ADMIN_USER", "admin")
        pw = os.environ.get("PP_ADMIN_PASSWORD")
        generada = not pw
        if generada:
            pw = secrets.token_urlsafe(9) + "a1"
        msg = validate_password(pw, user)
        if msg:
            sys.exit("PP_ADMIN_PASSWORD inválida: " + msg)
        ex("INSERT INTO usuarios(username, nombre, password_hash, rol_id, activo, debe_cambiar_clave) VALUES (?,?,?,?,1,1)",
           (user, "Administrador", hash_password(pw), q1("SELECT id FROM roles WHERE codigo = 'admin'")["id"]), commit=False)
        commit()
        print(f"[bootstrap] Administrador inicial creado: usuario «{user}»" + (f", contraseña temporal: {pw}" if generada else "") +
              " (se pedirá cambiarla al ingresar).", flush=True)
        if os.environ.get("PP_DEMO") == "1" and not q1("SELECT 1 FROM alumnos"):
            from app import seed
            seed.run()


def cmd_seed(app, a):
    from app import seed
    with app.app_context():
        seed.run(force=a.force)


def cmd_backup(app, a):
    name = backup.create_backup(app)
    backup.prune(app, keep=a.keep)
    print("Copia creada:", name)


def cmd_run(app, a):
    app.run(host=a.host, port=a.port, debug=a.debug)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("init-db").set_defaults(f=cmd_init_db)
    s.add_parser("bootstrap").set_defaults(f=cmd_bootstrap)
    c = s.add_parser("create-admin")
    c.add_argument("username")
    c.add_argument("--nombre", default="Administrador")
    c.add_argument("--password")
    c.set_defaults(f=cmd_create_admin)
    d = s.add_parser("seed-demo")
    d.add_argument("--force", action="store_true", help="carga aunque ya existan alumnos")
    d.set_defaults(f=cmd_seed)
    b = s.add_parser("backup")
    b.add_argument("--keep", type=int, default=30)
    b.set_defaults(f=cmd_backup)
    r = s.add_parser("run")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=5000)
    r.add_argument("--debug", action="store_true")
    r.set_defaults(f=cmd_run)
    a = p.parse_args()
    a.f(create_app(), a)


if __name__ == "__main__":
    main()
