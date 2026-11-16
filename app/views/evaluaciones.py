"""Evaluación de las prácticas: criterios del tutor y del referente, resultado final e informe en PDF."""
from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import auth, pdfs, services
from ..auth import perm_required
from ..crud import C, Entity, F
from ..db import audit, commit, ex, get_config, now, q, q1, today

bp = Blueprint("evaluaciones", __name__, url_prefix="/evaluaciones")


def _access_eval(id):
    r = q1("SELECT alumno_practica_id FROM evaluaciones WHERE id = ?", (id,))
    if r:
        auth.check_ap_access(r["alumno_practica_id"])


def _default_nombre():
    ap = request.values.get("alumno_practica_id", "")
    if request.values.get("evaluador") == "Referente" and ap.isdigit():
        r = q1("SELECT r.nombre FROM alumnos_practicas x JOIN practicas p ON p.id = x.practica_id JOIN referentes_empresas r ON r.id = p.referente_id WHERE x.id = ?", (int(ap),))
        return r["nombre"] if r else ""
    if g.user["rol"] == "tutor":
        return g.user["nombre"]
    if ap.isdigit():
        r = q1("SELECT d.apellido || ', ' || d.nombre AS n FROM alumnos_practicas x JOIN practicas p ON p.id = x.practica_id JOIN docentes d ON d.id = p.tutor_id WHERE x.id = ?", (int(ap),))
        return r["n"] if r else ""
    return ""


def _before_eval(vals, row, errors):
    ap_id = vals.get("alumno_practica_id")
    if not ap_id:
        return
    auth.check_ap_access(ap_id)
    if not q1("SELECT 1 FROM alumnos_practicas WHERE id = ? AND eliminado_en IS NULL", (ap_id,)):
        errors["alumno_practica_id"] = "Asignación inexistente."
        return
    if g.user["rol"] == "tutor" and vals.get("evaluador") != "Tutor":
        errors["evaluador"] = "Un docente tutor sólo puede cargar la evaluación del tutor."
    if vals.get("evaluador"):
        dup = q1("SELECT id FROM evaluaciones WHERE alumno_practica_id = ? AND evaluador = ? AND eliminado_en IS NULL AND id <> ?",
                 (ap_id, vals["evaluador"], row["id"] if row else 0))
        if dup:
            errors["evaluador"] = "Ya existe una evaluación de este evaluador. Edítela desde la ficha."
    if vals.get("fecha") and vals["fecha"] > today():
        errors["fecha"] = "La fecha no puede ser futura."
    notas = [vals.get(k) for k, _ in services.CRITERIOS]
    if all(n is not None for n in notas):
        vals["promedio"] = round(sum(notas) / len(notas), 2)


evaluaciones = Entity(
    "evals", "evaluaciones", "Evaluación", "Evaluaciones", "evaluaciones",
    fields=lambda row=None: [
        F("alumno_practica_id", "Asignación", "hidden", coerce=int, required=True),
        F("evaluador", "Evaluador", "select", required=True, default=lambda: request.values.get("evaluador", "Tutor"),
          choices=[("Tutor", "Docente tutor"), ("Referente", "Referente de la empresa")]),
        F("evaluador_nombre", "Nombre del evaluador", maxlen=150, default=_default_nombre),
        F("fecha", "Fecha de la evaluación", "date", required=True, default=today),
    ] + [F(k, lbl, "number", required=True, min=1, max=10, help="1 a 10") for k, lbl in services.CRITERIOS] + [
        F("observaciones", "Observaciones", "textarea", cols=2),
    ],
    columns=[C("fecha", "Fecha", "date")], listable=False, before_save=_before_eval, access=_access_eval, nuevo_label="Cargar evaluación",
)
bp_eval = evaluaciones.blueprint("/evaluaciones/cargar")


@bp.route("/")
@perm_required("evaluaciones.ver")
def inicio():
    args = request.args
    ciclo = services.ciclo_activo()
    filtros = {"ciclo_id": args.get("ciclo_id", ciclo["id"] if ciclo and "ciclo_id" not in args else ""),
               "especialidad_id": args.get("especialidad_id"), "curso_id": args.get("curso_id"), "estado": args.get("estado")}
    rows = services.ap_rows(filtros, order="a.apellido, a.nombre", con_docs=False)
    evs = {}
    for e in q("SELECT alumno_practica_id AS ap, evaluador, promedio FROM evaluaciones WHERE eliminado_en IS NULL"):
        evs.setdefault(e["ap"], {})[e["evaluador"]] = e["promedio"]
    for r in rows:
        r["ev_tutor"] = evs.get(r["ap_id"], {}).get("Tutor")
        r["ev_ref"] = evs.get(r["ap_id"], {}).get("Referente")
    if args.get("resultado") == "pendiente":
        rows = [r for r in rows if not r["resultado"]]
    elif args.get("resultado") in ("Aprobado", "Desaprobado"):
        rows = [r for r in rows if r["resultado"] == args["resultado"]]
    return render_template("evaluaciones/inicio.html", rows=rows, f=filtros, args=args, ciclos=services.lista_ciclos(),
                           especialidades=services.lista_especialidades(), cursos=services.lista_cursos(), estados=services.ESTADOS_PP)


@bp.route("/ap/<int:ap_id>")
@perm_required("evaluaciones.ver")
def detalle(ap_id):
    auth.check_ap_access(ap_id)
    d = services.evaluacion_data(ap_id, scoped=False)
    if not d:
        abort(404)
    return render_template("evaluaciones/detalle.html", d=d, ap=d["ap"], criterios=services.CRITERIOS,
                           nota_min=float(get_config("nota_aprobacion", 6)), hoy=today())


@bp.route("/ap/<int:ap_id>/final", methods=["POST"])
@perm_required("evaluaciones.editar")
def final(ap_id):
    auth.check_ap_access(ap_id)
    d = services.evaluacion_data(ap_id, scoped=False)
    if not d:
        abort(404)
    ap = d["ap"]
    back = redirect(url_for("evaluaciones.detalle", ap_id=ap_id))
    try:
        nota = float((request.form.get("calificacion_final") or "").replace(",", "."))
    except ValueError:
        nota = None
    resultado = request.form.get("resultado")
    forzar = request.form.get("forzar") == "1"
    obs = (request.form.get("observaciones_finales") or "").strip()[:2000] or None
    if nota is None or not 1 <= nota <= 10:
        flash("La calificación final debe ser un número entre 1 y 10.", "danger")
        return back
    if resultado not in ("Aprobado", "Desaprobado"):
        flash("Seleccione el resultado: aprobado o desaprobado.", "danger")
        return back
    if resultado == "Aprobado" and ap["horas_faltan"] > 0 and not forzar:
        flash(f"No se puede aprobar: al alumno le faltan {ap['horas_faltan']:.0f} h de las {ap['horas_requeridas']} requeridas. "
              "Marque «Aprobar con horas incompletas» si corresponde (queda registrado).", "danger")
        return back
    nuevo_estado = "Aprobada" if resultado == "Aprobado" else "Desaprobada"
    ex("UPDATE alumnos_practicas SET calificacion_final = ?, resultado = ?, observaciones_finales = ?, fecha_resultado = ?, estado = ?, "
       "fecha_fin_real = COALESCE(fecha_fin_real, ?), modificado_en = ?, modificado_por = ? WHERE id = ?",
       (round(nota, 2), resultado, obs, today(), nuevo_estado, today(), now(), g.user["id"], ap_id), commit=False)
    services.sincronizar_estado_practica(ap["practica_id"])
    audit("alumnos_practicas", ap_id, "modificar", {"resultado": resultado, "calificacion_final": nota, "horas_incompletas_forzado": forzar and ap["horas_faltan"] > 0})
    commit()
    flash(f"Resultado registrado: {resultado} ({nota:g}).", "success")
    return back


@bp.route("/ap/<int:ap_id>/reabrir", methods=["POST"])
@perm_required("evaluaciones.editar")
def reabrir(ap_id):
    auth.check_ap_access(ap_id)
    ap = q1("SELECT * FROM alumnos_practicas WHERE id = ? AND eliminado_en IS NULL", (ap_id,))
    if not ap:
        abort(404)
    ex("UPDATE alumnos_practicas SET resultado = NULL, calificacion_final = NULL, fecha_resultado = NULL, estado = 'Finalizada', modificado_en = ?, modificado_por = ? WHERE id = ?",
       (now(), g.user["id"], ap_id), commit=False)
    ex("UPDATE practicas SET estado = 'Finalizada' WHERE id = ? AND estado IN ('Aprobada','Desaprobada')", (ap["practica_id"],), commit=False)
    audit("alumnos_practicas", ap_id, "modificar", {"resultado": [ap["resultado"], None], "reabierta": True})
    commit()
    flash("Resultado anulado: la práctica volvió al estado «Finalizada».", "success")
    return redirect(url_for("evaluaciones.detalle", ap_id=ap_id))


@bp.route("/ap/<int:ap_id>/informe.pdf")
@perm_required("evaluaciones.ver")
def informe_pdf(ap_id):
    auth.check_ap_access(ap_id)
    data = pdfs.informe_evaluacion(ap_id)
    if data is None:
        abort(404)
    audit("alumnos_practicas", ap_id, "exportar", {"formato": "pdf informe de evaluación"})
    commit()
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="informe_evaluacion_{ap_id}.pdf"'})


def blueprints():
    return [bp, bp_eval]
