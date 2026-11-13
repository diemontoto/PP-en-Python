"""Seguimiento y control de horas: asistencia, visitas y avance por alumno."""
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

from .. import auth, services
from ..auth import perm_required
from ..crud import C, Entity, F
from ..db import audit, commit, ex, now, q, q1, today

TIPOS_ASIST = ["Presente", "Ausente justificado", "Ausente injustificado"]


def _access_asistencia(id):
    r = q1("SELECT alumno_practica_id FROM asistencias WHERE id = ?", (id,))
    if r:
        auth.check_ap_access(r["alumno_practica_id"])


def _before_asist(vals, row, errors):
    ap_id = vals.get("alumno_practica_id")
    if not ap_id:
        return
    auth.check_ap_access(ap_id)
    ap = q1("SELECT estado FROM alumnos_practicas WHERE id = ? AND eliminado_en IS NULL", (ap_id,))
    if not ap:
        errors["alumno_practica_id"] = "Asignación inexistente."
        return
    if ap["estado"] in ("Aprobada", "Desaprobada"):
        errors["fecha"] = "La práctica ya tiene resultado final: no admite nuevas asistencias."
        return
    if vals.get("fecha") and "fecha" not in errors:
        if vals["fecha"] > today():
            errors["fecha"] = "No se puede registrar asistencia en una fecha futura."
        dup = q1("SELECT id FROM asistencias WHERE alumno_practica_id = ? AND fecha = ? AND eliminado_en IS NULL AND id <> ?",
                 (ap_id, vals["fecha"], row["id"] if row else 0))
        if dup:
            errors["fecha"] = "Ya existe un registro de asistencia para ese día."
    if vals.get("tipo") == "Presente":
        if not vals.get("hora_entrada"):
            errors["hora_entrada"] = "Obligatoria para asistencias presentes."
        if not vals.get("hora_salida"):
            errors["hora_salida"] = "Obligatoria para asistencias presentes."
        if vals.get("hora_entrada") and vals.get("hora_salida") and "hora_entrada" not in errors and "hora_salida" not in errors:
            h = services.calc_horas(vals["hora_entrada"], vals["hora_salida"])
            if h is None:
                errors["hora_salida"] = "La salida debe ser posterior a la entrada."
            elif h > 14:
                errors["hora_salida"] = "La jornada no puede superar las 14 horas."
            vals["horas"] = h
    else:
        vals["horas"] = 0
        vals["hora_entrada"] = vals["hora_salida"] = None


asistencias = Entity(
    "asistencias", "asistencias", "Asistencia", "Asistencias", "seguimiento",
    fields=[
        F("alumno_practica_id", "Asignación", "hidden", coerce=int, required=True),
        F("fecha", "Fecha", "date", required=True, default=today),
        F("tipo", "Tipo", "select", required=True, default="Presente", choices=[(t, t) for t in TIPOS_ASIST]),
        F("hora_entrada", "Hora de entrada", "time"),
        F("hora_salida", "Hora de salida", "time"),
        F("observaciones", "Observaciones", maxlen=300, cols=2),
    ],
    columns=[C("fecha", "Fecha", "date")], listable=False, before_save=_before_asist, access=_access_asistencia,
    nuevo_label="Registrar asistencia",
)

visitas = Entity(
    "visitas", "seguimiento", "Registro de seguimiento", "Seguimiento", "seguimiento",
    fields=lambda row=None: [
        F("practica_id", "Práctica", "hidden", coerce=int, required=True),
        F("alumno_practica_id", "Alumno (opcional)", "select", coerce=int,
          choices=lambda: _aps_choices(request.values.get("practica_id") or (row["practica_id"] if row else 0))),
        F("fecha", "Fecha", "date", required=True, default=today),
        F("tipo", "Tipo", "select", required=True, default="Visita", choices=[(t, t) for t in ("Visita", "Llamado", "Reunión", "Informe", "Otro")]),
        F("docente_id", "Docente que realiza el seguimiento", "select", coerce=int,
          default=lambda: g.user["docente_id"] or "", choices=lambda: [(d["id"], d["nombre"]) for d in services.lista_docentes(False)]),
        F("descripcion", "Descripción / observaciones", "textarea", required=True, cols=2, maxlen=3000),
    ],
    columns=[C("fecha", "Fecha", "date")], listable=False,
    access=lambda id: auth.check_practica_access(q1("SELECT practica_id FROM seguimiento WHERE id = ?", (id,))["practica_id"]),
    before_save=lambda vals, row, errors: (auth.check_practica_access(vals["practica_id"]) if vals.get("practica_id") else None),
    nuevo_label="Registrar seguimiento",
)


def _aps_choices(practica_id):
    if not str(practica_id).isdigit():
        return []
    return [(r["ap_id"], r["alumno"]) for r in services.ap_rows({"practica_id": practica_id})]


bp = auth_bp = None
from flask import Blueprint  # noqa: E402
bp = Blueprint("seguimiento", __name__, url_prefix="/seguimiento")
bp_asist = asistencias.blueprint("/seguimiento/asistencias")
bp_vis = visitas.blueprint("/seguimiento/visitas")


@bp.route("/")
@perm_required("seguimiento.ver")
def inicio():
    args = request.args
    ciclo = services.ciclo_activo()
    filtros = {
        "ciclo_id": args.get("ciclo_id", ciclo["id"] if ciclo and "ciclo_id" not in args else ""),
        "especialidad_id": args.get("especialidad_id"), "curso_id": args.get("curso_id"), "division_id": args.get("division_id"),
        "empresa_id": args.get("empresa_id"), "tutor_id": args.get("tutor_id"), "estado": args.get("estado"),
    }
    rows = services.ap_rows(filtros, order="a.apellido, a.nombre")
    if args.get("pendientes") == "1":
        rows = [r for r in rows if r["horas_faltan"] > 0 and r["estado"] in ("En curso", "Finalizada", "Suspendida", "Habilitada para comenzar")]
    if args.get("q"):
        from ..db import norm
        t = norm(args["q"])
        rows = [r for r in rows if t in norm(r["alumno"] + " " + r["dni"] + " " + r["empresa"] + " " + r["numero"])]
    total_req = sum(r["horas_requeridas"] for r in rows)
    total_hs = sum(r["horas_realizadas"] for r in rows)
    return render_template("seguimiento/inicio.html", rows=rows, f=filtros, args=args,
                           ciclos=services.lista_ciclos(), especialidades=services.lista_especialidades(), cursos=services.lista_cursos(),
                           divisiones=services.lista_divisiones(), empresas=services.lista_empresas(False),
                           docentes=services.lista_docentes(False), estados=services.ESTADOS_PP,
                           cumplimiento=round(total_hs * 100 / total_req, 1) if total_req else 0, total_hs=total_hs, total_req=total_req)


@bp.route("/ap/<int:ap_id>")
@perm_required("seguimiento.ver")
def detalle(ap_id):
    auth.check_ap_access(ap_id)
    rows = services.ap_rows({"ap_id": ap_id}, scoped=False)
    if not rows:
        abort(404)
    ap = rows[0]
    asist = q("SELECT * FROM asistencias WHERE alumno_practica_id = ? AND eliminado_en IS NULL ORDER BY fecha DESC", (ap_id,))
    segs = q("SELECT s.*, dc.apellido || ', ' || dc.nombre AS docente FROM seguimiento s LEFT JOIN docentes dc ON dc.id = s.docente_id "
             "WHERE s.practica_id = ? AND (s.alumno_practica_id = ? OR s.alumno_practica_id IS NULL) AND s.eliminado_en IS NULL "
             "ORDER BY s.fecha DESC, s.id DESC", (ap["practica_id"], ap_id))
    total_dias = ap["dias_presente"] + ap["faltas_just"] + ap["faltas_injust"]
    pct_asist = round(ap["dias_presente"] * 100 / total_dias, 1) if total_dias else None
    return render_template("seguimiento/detalle.html", ap=ap, asist=asist, segs=segs, pct_asist=pct_asist, tipos=TIPOS_ASIST, hoy=today(),
                           cerrado=ap["estado"] in ("Aprobada", "Desaprobada"))


@bp.route("/practica/<int:practica_id>/dia", methods=["GET", "POST"])
@perm_required("seguimiento.editar")
def dia(practica_id):
    auth.check_practica_access(practica_id)
    p = q1("SELECT p.*, em.razon_social AS empresa FROM practicas p JOIN empresas em ON em.id = p.empresa_id WHERE p.id = ? AND p.eliminado_en IS NULL", (practica_id,))
    if not p:
        abort(404)
    fecha = request.values.get("fecha") or today()
    try:
        date.fromisoformat(fecha)
    except ValueError:
        fecha = today()
    aps = [r for r in services.ap_rows({"practica_id": practica_id}, con_docs=False) if r["estado"] not in ("Aprobada", "Desaprobada", "Pendiente de asignación")]
    if request.method == "POST":
        if fecha > today():
            flash("No se puede registrar asistencia en una fecha futura.", "danger")
            return redirect(url_for("seguimiento.dia", practica_id=practica_id))
        n, errores = 0, []
        for r in aps:
            tipo = request.form.get(f"tipo_{r['ap_id']}", "")
            if not tipo:
                continue
            if tipo not in TIPOS_ASIST:
                errores.append(f"{r['alumno']}: tipo inválido")
                continue
            ent, sal, horas = request.form.get(f"ent_{r['ap_id']}") or None, request.form.get(f"sal_{r['ap_id']}") or None, 0
            if tipo == "Presente":
                horas = services.calc_horas(ent or "", sal or "")
                if horas is None or horas > 14:
                    errores.append(f"{r['alumno']}: horario inválido")
                    continue
            else:
                ent = sal = None
            existente = q1("SELECT id FROM asistencias WHERE alumno_practica_id = ? AND fecha = ? AND eliminado_en IS NULL", (r["ap_id"], fecha))
            obs = (request.form.get(f"obs_{r['ap_id']}") or "").strip()[:300] or None
            if existente:
                ex("UPDATE asistencias SET tipo=?, hora_entrada=?, hora_salida=?, horas=?, observaciones=?, modificado_en=?, modificado_por=? WHERE id=?",
                   (tipo, ent, sal, horas, obs, now(), g.user["id"], existente["id"]), commit=False)
                audit("asistencias", existente["id"], "modificar", {"fecha": fecha, "tipo": tipo, "horas": horas})
            else:
                cur = ex("INSERT INTO asistencias(alumno_practica_id, fecha, tipo, hora_entrada, hora_salida, horas, observaciones, creado_en, creado_por) VALUES (?,?,?,?,?,?,?,?,?)",
                         (r["ap_id"], fecha, tipo, ent, sal, horas, obs, now(), g.user["id"]), commit=False)
                audit("asistencias", cur.lastrowid, "crear", {"fecha": fecha, "tipo": tipo, "horas": horas})
            n += 1
        commit()
        if n:
            flash(f"Asistencia del {fecha[8:10]}/{fecha[5:7]}/{fecha[:4]} guardada para {n} alumno(s).", "success")
        for e in errores:
            flash(e, "danger")
        return redirect(url_for("seguimiento.dia", practica_id=practica_id, fecha=fecha))
    previas = {r["alumno_practica_id"]: r for r in q("SELECT * FROM asistencias WHERE fecha = ? AND eliminado_en IS NULL", (fecha,))}
    ultimas = {}
    for r in q("SELECT alumno_practica_id, hora_entrada, hora_salida FROM asistencias WHERE tipo = 'Presente' AND eliminado_en IS NULL ORDER BY fecha"):
        ultimas[r["alumno_practica_id"]] = r
    return render_template("seguimiento/dia.html", p=p, aps=aps, fecha=fecha, previas=previas, ultimas=ultimas, tipos=TIPOS_ASIST)


def blueprints():
    return [bp, bp_asist, bp_vis]
