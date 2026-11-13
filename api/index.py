"""Entrada para Vercel (MODO DEMOSTRACIÓN). El disco de Vercel es temporal: los datos se reinician solos.
No usar con datos reales; para producción vea docs/DESPLIEGUE.md (servidor con disco persistente)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PP_INSTANCE", "/tmp/pp-demo")
os.environ.setdefault("PP_HTTPS", "1")
# Clave fija sólo para la demo (varias instancias de Vercel deben compartirla). Mejor: definir PP_SECRET_KEY en Vercel.
os.environ.setdefault("PP_SECRET_KEY", "demo-no-usar-en-produccion-" + "x" * 32)

from app import create_app, seed  # noqa: E402
from app.db import get_db, q1  # noqa: E402

app = create_app()
with app.app_context():
    get_db()
    if not q1("SELECT 1 FROM alumnos"):
        seed.run()
