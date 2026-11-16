"""Filtros y funciones de formato para las plantillas Jinja."""
from datetime import datetime

from markupsafe import Markup, escape

BADGES = {
    # estados de práctica
    "Pendiente de asignación": "gray",
    "En proceso de asignación": "blue",
    "Documentación pendiente": "amber",
    "Habilitada para comenzar": "teal",
    "En curso": "blue",
    "Suspendida": "orange",
    "Finalizada": "violet",
    "Aprobada": "green",
    "Desaprobada": "red",
    # resultados / documentación
    "Aprobado": "green",
    "Desaprobado": "red",
    "Completa": "green",
    "Incompleta": "red",
    "Pendiente de revisión": "amber",
    "Observado": "orange",
    # asistencia
    "Presente": "green",
    "Ausente justificado": "amber",
    "Ausente injustificado": "red",
    # alumnos
    "Regular": "green",
    "Repitente": "amber",
    "Libre": "orange",
    "Egresado": "violet",
    "Baja / Pase": "gray",
    "Sin asignar": "gray",
}


def badge(value, css=None):
    if value in (None, ""):
        return Markup('<span class="muted">—</span>')
    cls = css or BADGES.get(value, "gray")
    return Markup('<span class="badge badge-%s">%s</span>') % (cls, value)


def fecha(value):
    if not value:
        return ""
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def fechahora(value):
    if not value:
        return ""
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)


def num(value, dec=1):
    if value is None or value == "":
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v == int(v) and dec <= 1:
        return str(int(v))
    return f"{v:.{dec}f}".replace(".", ",")


def cell(value, kind="text"):
    """Formatea una celda de tabla según su tipo."""
    if kind == "date":
        return fecha(value)
    if kind == "datetime":
        return fechahora(value)
    if kind == "bool":
        return Markup('<span class="badge badge-green">Sí</span>') if value else Markup('<span class="badge badge-gray">No</span>')
    if kind == "badge":
        return badge(value)
    if kind == "num":
        return num(value)
    if kind == "pct":
        return "" if value is None else f"{num(value, 0)} %"
    if value is None:
        return ""
    return str(value)


def plain(value, kind="text"):
    """Valor de texto plano (para Excel/PDF)."""
    if kind == "date":
        return fecha(value)
    if kind == "datetime":
        return fechahora(value)
    if kind == "bool":
        return "Sí" if value else "No"
    if kind in ("num", "pct"):
        return num(value)
    return "" if value is None else str(value)


def init_app(app):
    app.jinja_env.filters.update(badge=badge, fecha=fecha, fechahora=fechahora, num=num, cell=cell)
