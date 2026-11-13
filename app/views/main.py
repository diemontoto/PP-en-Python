"""Dashboard, búsqueda global y alertas."""
from flask import Blueprint, render_template, request

from .. import auth, charts, services
from ..auth import perm_required
from ..db import norm, q, q1

bp = Blueprint("main", __name__)

ESTADO_COLOR = {
    "Pendiente de asignación": "#6b7280", "En proceso de asignación": "#2f6fb3", "Documentación pendiente": "#d98a1d",
    "Habilitada para comenzar": "#0f6b6b", "En curso": "#1d4f91", "Suspendida": "#a14a0a", "Finalizada": "#5b3a9a",
    "Aprobada": "#1b7f4b", "Desaprobada": "#b42318",
}


@bp.route("/salud")
def salud():
    return "ok", 200, {"Content-Type": "text/plain"}


def _filtros_dashboard():
    args = request.args
    ciclo = services.ciclo_activo()
    return {
        "ciclo_id": args.get("ciclo_id", str(ciclo["id"]) if ciclo and "ciclo_id" not in args else ""),
        "especialidad_id": args.get("especialidad_id", ""), "curso_id": args.get("curso_id", ""), "division_id": args.get("division_id", ""),
    }


def kpis(f):
    """Indicadores del panel de control según filtros (año lectivo, especialidad, curso, división)."""
    # alumnos (año de cursada = ciclo)
    where, params = ["a.eliminado_en IS NULL"], []
    for key, col in (("ciclo_id", "a.ciclo_id"), ("especialidad_id", "a.especialidad_id"), ("curso_id", "a.curso_id"), ("division_id", "a.division_id")):
        if f.get(key):
            where.append(f"{col} = ?")
            params.append(f[key])
    sql, sp = auth.scope_alumnos("a")
    where.append(sql)
    params += sp
    alumnos = q("SELECT a.id, a.especialidad_id, c.requiere_pp, a.estado_academico, e.nombre AS esp FROM alumnos a JOIN cursos c ON c.id = a.curso_id "
                "LEFT JOIN especialidades e ON e.id = a.especialidad_id WHERE " + " AND ".join(where), params)
    deben = [a for a in alumnos if a["requiere_pp"] and a["estado_academico"] in ("Regular", "Repitente")]
    aps = services.ap_rows(f, order="a.apellido")
    asignados = {r["alumno_id"] for r in aps}
    k = {
        "total_alumnos": len(alumnos), "deben_pp": len(deben),
        "asignados": len({a["id"] for a in deben} & asignados) if f.get("ciclo_id") is not None else len(asignados),
        "en_curso": sum(1 for r in aps if r["estado"] == "En curso"),
        "finalizadas": sum(1 for r in aps if r["estado"] in ("Finalizada", "Aprobada", "Desaprobada")),
        "aprobadas": sum(1 for r in aps if r["estado"] == "Aprobada"),
        "desaprobadas": sum(1 for r in aps if r["estado"] == "Desaprobada"),
        "pendientes": sum(1 for r in aps if r["estado"] in services.PRE_INICIO),
        "sin_asignar": len([a for a in deben if a["id"] not in asignados]),
        "docs_incompletas": len({r["alumno_id"] for r in aps if r["estado"] in services.PRE_INICIO[1:] + ["En curso"] and r["docs_estado"] != "Completa"}),
        "horas_pendientes": len({r["alumno_id"] for r in aps if r["estado"] in ("En curso", "Suspendida", "Finalizada") and r["horas_faltan"] > 0}),
        "empresas_activas": q1("SELECT COUNT(*) AS n FROM empresas WHERE activo = 1 AND eliminado_en IS NULL")["n"],
        "vacantes": services.vacantes_disponibles_total(),
    }
    # gráficos
    por_estado = [(e, sum(1 for r in aps if r["estado"] == e), ESTADO_COLOR[e]) for e in services.ESTADOS_PP]
    por_estado = [x for x in por_estado if x[1]]
    esp_count = {}
    for a in deben:
        esp_count[a["esp"] or "Sin especialidad"] = esp_count.get(a["esp"] or "Sin especialidad", 0) + 1
    cumpl = {}
    for r in aps:
        d = cumpl.setdefault(r["especialidad"] or "Sin especialidad", [0.0, 0.0])
        d[0] += r["horas_realizadas"]
        d[1] += r["horas_requeridas"]
    situacion = [("Aprobadas", k["aprobadas"], "#1b7f4b"), ("Desaprobadas", k["desaprobadas"], "#b42318"),
                 ("En curso", k["en_curso"], "#1d4f91"), ("Finalizadas sin resultado", k["finalizadas"] - k["aprobadas"] - k["desaprobadas"], "#5b3a9a"),
                 ("Previas al inicio", k["pendientes"], "#d98a1d"), ("Suspendidas", sum(1 for r in aps if r["estado"] == "Suspendida"), "#a14a0a"),
                 ("Alumnos sin asignar", k["sin_asignar"], "#6b7280")]
    k["chart_estado"] = charts.bar_chart(por_estado)
    k["chart_situacion"] = charts.donut(situacion, "situaciones")
    k["chart_esp"] = charts.bar_chart([(n, v, charts.PALETTE[i % 8]) for i, (n, v) in enumerate(sorted(esp_count.items()))])
    k["chart_cumpl"] = charts.bar_chart([(n, round(h * 100 / r, 1), "#1b7f4b") for n, (h, r) in sorted(cumpl.items()) if r], unit=" %", max_value=100)
    return k


@bp.route("/")
def inicio():
    f = _filtros_dashboard()
    k = kpis(f) if auth.can("practicas.ver") else None
    al = services.alertas({"ciclo_id": f["ciclo_id"]}) if k else None
    return render_template("main/dashboard.html", k=k, f=f, al=al, ciclos=services.lista_ciclos(),
                           especialidades=services.lista_especialidades(), cursos=services.lista_cursos(), divisiones=services.lista_divisiones())


@bp.route("/alertas")
@perm_required("practicas.ver")
def alertas():
    ciclo = services.ciclo_activo()
    cid = request.args.get("ciclo_id", str(ciclo["id"]) if ciclo and "ciclo_id" not in request.args else "")
    return render_template("main/alertas.html", al=services.alertas({"ciclo_id": cid}), ciclo_id=cid, ciclos=services.lista_ciclos())


@bp.route("/buscar")
def buscar():
    term = (request.args.get("q") or "").strip()
    res = {"alumnos": [], "empresas": [], "docentes": [], "practicas": []}
    if len(term) >= 2:
        words = [f"%{w}%" for w in norm(term).split()]

        def cond(expr):
            return " AND ".join(f"norm({expr}) LIKE ?" for _ in words), list(words)
        if auth.can("alumnos.ver"):
            c, p = cond("COALESCE(a.apellido,'') || ' ' || COALESCE(a.nombre,'') || ' ' || a.dni || ' ' || a.legajo")
            s, sp = auth.scope_alumnos("a")
            res["alumnos"] = q(f"SELECT a.id, a.apellido || ', ' || a.nombre AS n, a.dni, a.legajo, cu.nombre AS curso FROM alumnos a JOIN cursos cu ON cu.id = a.curso_id "
                               f"WHERE a.eliminado_en IS NULL AND {c} AND {s} ORDER BY a.apellido LIMIT 15", p + sp)
        if auth.can("empresas.ver"):
            c, p = cond("COALESCE(e.razon_social,'') || ' ' || COALESCE(e.nombre_fantasia,'') || ' ' || COALESCE(e.cuit,'')")
            res["empresas"] = q(f"SELECT e.id, e.razon_social, e.cuit, e.localidad FROM empresas e WHERE e.eliminado_en IS NULL AND {c} ORDER BY e.razon_social LIMIT 15", p)
        if auth.can("docentes.ver"):
            c, p = cond("d.apellido || ' ' || d.nombre || ' ' || d.dni")
            res["docentes"] = q(f"SELECT d.id, d.apellido || ', ' || d.nombre AS n, d.dni FROM docentes d WHERE d.eliminado_en IS NULL AND {c} ORDER BY d.apellido LIMIT 15", p)
        if auth.can("practicas.ver"):
            c, p = cond("p.numero || ' ' || p.proyecto || ' ' || em.razon_social")
            s, sp = auth.scope_practicas("p")
            res["practicas"] = q(f"SELECT p.id, p.numero, p.proyecto, p.estado, em.razon_social AS empresa FROM practicas p JOIN empresas em ON em.id = p.empresa_id "
                                 f"WHERE p.eliminado_en IS NULL AND {c} AND {s} ORDER BY p.numero DESC LIMIT 15", p + sp)
    return render_template("main/buscar.html", term=term, res=res, total=sum(len(v) for v in res.values()))


def blueprints():
    return [bp]
