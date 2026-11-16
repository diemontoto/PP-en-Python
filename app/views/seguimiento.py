<<<<<<< HEAD
"""Seguimiento y control de horas: asistencia automática, inasistencias, visitas y avance por alumno."""
=======
"""Seguimiento y control de horas: asistencia, visitas y avance por alumno."""
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

from .. import auth, services
from ..auth import perm_required
from ..crud import C, Entity, F
from ..db import audit, commit, ex, now, q, q1, today

<<<<<<< HEAD
TIPOS_ASIST = services.TIPOS_INASISTENCIA
ADMITEN_INASISTENCIAS = ("En curso", "Suspendida", "Finalizada")
=======
TIPOS_ASIST = ["Presente", "Ausente justificado", "Ausente injustificado"]
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3


def _access_asistencia(id):
    r = q1("SELECT alumno_practica_id FROM asistencias WHERE id = ?", (id,))
    if r:
        auth.check_ap_access(r["alumno_practica_id"])


<<<<<<< HEAD
def _ap_calc(ap_id):
    rows = services.ap_rows({"ap_id": ap_id}, scoped=False, con_docs=False)
    return rows[0] if rows else None


def _motivo_no_programado(ap, fecha):
    """Explica por qué en una fecha no corren horas para la asignación (None si es un día de práctica)."""
    if fecha in ap["dias_prog"]:
        return None
    if fecha > today():
        return "No se pueden registrar inasistencias en una fecha futura."
    if ap["estado"] not in services.CORREN_HORAS or not ap["periodo_desde"]:
        return "La práctica del alumno todavía no comenzó: no hay horas corriendo."
    if fecha < ap["periodo_desde"] or fecha > ap["periodo_hasta"]:
        return (f"La fecha está fuera del período de la práctica ({ap['periodo_desde'][8:10]}/{ap['periodo_desde'][5:7]}/{ap['periodo_desde'][:4]} "
                f"al {ap['periodo_hasta'][8:10]}/{ap['periodo_hasta'][5:7]}/{ap['periodo_hasta'][:4]}).")
    return "Ese día no es un día de práctica (día no laborable de la práctica, feriado, receso o suspensión): no hay horas para descontar."


def _horas_inasistencia(valor, jornada):
    """Horas a descontar: vacío = jornada completa. Devuelve (horas, error)."""
    if valor in (None, ""):
        return jornada, None
    try:
        h = round(float(str(valor).replace(",", ".")), 2)
    except ValueError:
        return None, "Número inválido."
    if h <= 0:
        return None, "Debe ser mayor que cero."
    if h > jornada:
        return None, f"No puede superar la jornada de la práctica ({jornada:g} h)."
    return h, None


=======
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3
def _before_asist(vals, row, errors):
    ap_id = vals.get("alumno_practica_id")
    if not ap_id:
        return
    auth.check_ap_access(ap_id)
<<<<<<< HEAD
    ap = _ap_calc(ap_id)
=======
    ap = q1("SELECT estado FROM alumnos_practicas WHERE id = ? AND eliminado_en IS NULL", (ap_id,))
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3
    if not ap:
        errors["alumno_practica_id"] = "Asignación inexistente."
        return
    if ap["estado"] in ("Aprobada", "Desaprobada"):
<<<<<<< HEAD
        errors["fecha"] = "La práctica ya tiene resultado final: no admite nuevas inasistencias."
        return
    if vals.get("fecha") and "fecha" not in errors:
        motivo = _motivo_no_programado(ap, vals["fecha"])
        if motivo:
            errors["fecha"] = motivo
        elif q1("SELECT id FROM asistencias WHERE alumno_practica_id = ? AND fecha = ? AND eliminado_en IS NULL AND id <> ?",
                (ap_id, vals["fecha"], row["id"] if row else 0)):
            errors["fecha"] = "Ya existe una inasistencia registrada para ese día."
    if "horas" not in errors:
        h, err = _horas_inasistencia(vals.get("horas"), float(ap["horas_dia"]))
        if err:
            errors["horas"] = err
        vals["horas"] = h
    vals["hora_entrada"] = vals["hora_salida"] = None


asistencias = Entity(
    "asistencias", "asistencias", "Inasistencia", "Inasistencias", "seguimiento",
    fields=[
        F("alumno_practica_id", "Asignación", "hidden", coerce=int, required=True),
        F("fecha", "Fecha de la inasistencia", "date", required=True, default=today),
        F("tipo", "Tipo", "select", required=True, default=TIPOS_ASIST[0], choices=[(t, t) for t in TIPOS_ASIST]),
        F("horas", "Horas a descontar", "number", decimal=True, min=0.25, max=14,
          help="Déjelo vacío para descontar la jornada completa. Use un valor menor si el alumno faltó sólo una parte del día."),
        F("observaciones", "Motivo / observaciones", maxlen=300, cols=2),
    ],
    columns=[C("fecha", "Fecha", "date")], listable=False, before_save=_before_asist, access=_access_asistencia,
    nuevo_label="Registrar inasistencia",
=======
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
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3
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
<<<<<<< HEAD
    asist = [dict(a, aplica=a["fecha"] in ap["dias_prog"]) for a in
             q("SELECT * FROM asistencias WHERE alumno_practica_id = ? AND eliminado_en IS NULL AND tipo <> 'Presente' ORDER BY fecha DESC", (ap_id,))]
    segs = q("SELECT s.*, dc.apellido || ', ' || dc.nombre AS docente FROM seguimiento s LEFT JOIN docentes dc ON dc.id = s.docente_id "
             "WHERE s.practica_id = ? AND (s.alumno_practica_id = ? OR s.alumno_practica_id IS NULL) AND s.eliminado_en IS NULL "
             "ORDER BY s.fecha DESC, s.id DESC", (ap["practica_id"], ap_id))
    pct_asist = round(ap["horas_realizadas"] * 100 / ap["horas_programadas"], 1) if ap["horas_programadas"] else None
    return render_template("seguimiento/detalle.html", ap=ap, asist=asist, segs=segs, pct_asist=pct_asist, tipos=TIPOS_ASIST, hoy=today(),
                           cerrado=ap["estado"] in ("Aprobada", "Desaprobada"), admite=ap["estado"] in ADMITEN_INASISTENCIAS,
                           dias_txt=services.dias_texto(ap["dias_semana"]))
=======
    asist = q("SELECT * FROM asistencias WHERE alumno_practica_id = ? AND eliminado_en IS NULL ORDER BY fecha DESC", (ap_id,))
    segs = q("SELECT s.*, dc.apellido || ', ' || dc.nombre AS docente FROM seguimiento s LEFT JOIN docentes dc ON dc.id = s.docente_id "
             "WHERE s.practica_id = ? AND (s.alumno_practica_id = ? OR s.alumno_practica_id IS NULL) AND s.eliminado_en IS NULL "
             "ORDER BY s.fecha DESC, s.id DESC", (ap["practica_id"], ap_id))
    total_dias = ap["dias_presente"] + ap["faltas_just"] + ap["faltas_injust"]
    pct_asist = round(ap["dias_presente"] * 100 / total_dias, 1) if total_dias else None
    return render_template("seguimiento/detalle.html", ap=ap, asist=asist, segs=segs, pct_asist=pct_asist, tipos=TIPOS_ASIST, hoy=today(),
                           cerrado=ap["estado"] in ("Aprobada", "Desaprobada"))
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3


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
<<<<<<< HEAD
    todos = services.ap_rows({"practica_id": practica_id}, con_docs=False)
    aps = [r for r in todos if r["estado"] in ADMITEN_INASISTENCIAS and fecha in r["dias_prog"]]
    if request.method == "POST":
        n, quitadas, errores = 0, 0, []
        previas = {r["alumno_practica_id"]: r for r in q("SELECT * FROM asistencias WHERE fecha = ? AND eliminado_en IS NULL AND tipo <> 'Presente'", (fecha,))}
        for r in aps:
            tipo = request.form.get(f"tipo_{r['ap_id']}", "")
            existente = previas.get(r["ap_id"])
            if not tipo:                      # asistió: si había una inasistencia cargada, se quita
                if existente:
                    ex("UPDATE asistencias SET eliminado_en = ?, eliminado_por = ? WHERE id = ?", (now(), g.user["id"], existente["id"]), commit=False)
                    audit("asistencias", existente["id"], "baja", {"fecha": fecha, "tipo": existente["tipo"], "horas": existente["horas"]})
                    quitadas += 1
=======
    aps = [r for r in services.ap_rows({"practica_id": practica_id}, con_docs=False) if r["estado"] not in ("Aprobada", "Desaprobada", "Pendiente de asignación")]
    if request.method == "POST":
        if fecha > today():
            flash("No se puede registrar asistencia en una fecha futura.", "danger")
            return redirect(url_for("seguimiento.dia", practica_id=practica_id))
        n, errores = 0, []
        for r in aps:
            tipo = request.form.get(f"tipo_{r['ap_id']}", "")
            if not tipo:
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3
                continue
            if tipo not in TIPOS_ASIST:
                errores.append(f"{r['alumno']}: tipo inválido")
                continue
<<<<<<< HEAD
            horas, err = _horas_inasistencia(request.form.get(f"hs_{r['ap_id']}", "").strip(), float(r["horas_dia"]))
            if err:
                errores.append(f"{r['alumno']}: horas a descontar — {err}")
                continue
            obs = (request.form.get(f"obs_{r['ap_id']}") or "").strip()[:300] or None
            if existente:
                if (existente["tipo"], existente["horas"], existente["observaciones"]) == (tipo, horas, obs):
                    continue
                ex("UPDATE asistencias SET tipo=?, hora_entrada=NULL, hora_salida=NULL, horas=?, observaciones=?, modificado_en=?, modificado_por=? WHERE id=?",
                   (tipo, horas, obs, now(), g.user["id"], existente["id"]), commit=False)
                audit("asistencias", existente["id"], "modificar", {"fecha": fecha, "tipo": tipo, "horas": horas})
            else:
                cur = ex("INSERT INTO asistencias(alumno_practica_id, fecha, tipo, horas, observaciones, creado_en, creado_por) VALUES (?,?,?,?,?,?,?)",
                         (r["ap_id"], fecha, tipo, horas, obs, now(), g.user["id"]), commit=False)
                audit("asistencias", cur.lastrowid, "crear", {"fecha": fecha, "tipo": tipo, "horas": horas})
            n += 1
        commit()
        f_txt = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}"
        if n:
            flash(f"Inasistencias del {f_txt}: {n} registrada(s) o actualizada(s).", "success")
        if quitadas:
            flash(f"Inasistencias del {f_txt}: {quitadas} quitada(s).", "success")
        if not n and not quitadas and not errores:
            flash("Sin cambios: todos los alumnos figuran presentes ese día.", "info")
        for e in errores:
            flash(e, "danger")
        return redirect(url_for("seguimiento.dia", practica_id=practica_id, fecha=fecha))
    previas = {r["alumno_practica_id"]: r for r in q("SELECT * FROM asistencias WHERE fecha = ? AND eliminado_en IS NULL AND tipo <> 'Presente'", (fecha,))}
    aviso = None
    if not aps:
        activos = [r for r in todos if r["estado"] in ADMITEN_INASISTENCIAS]
        aviso = _motivo_no_programado(activos[0], fecha) if activos else "No hay alumnos con la práctica en curso."
    return render_template("seguimiento/dia.html", p=p, aps=aps, fecha=fecha, previas=previas, tipos=TIPOS_ASIST, aviso=aviso, hoy=today(),
                           dias_txt=services.dias_texto(p["dias_semana"]))
=======
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
>>>>>>> ca0eab22fac98c6a3993d3997f2efc30742cd8d3


def blueprints():
    return [bp, bp_asist, bp_vis]
