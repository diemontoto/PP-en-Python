"""Docentes y tutores: ABM, ficha y asignación de alumnos."""
from flask import abort, flash, g, redirect, render_template, request, url_for

from .. import auth, services
from ..auth import perm_required
from ..crud import C, Entity, F
from ..db import audit, commit, ex, now, q, q1

SELECT = """
SELECT t.*, t.apellido || ', ' || t.nombre AS docente, e.nombre AS especialidad,
  (SELECT COUNT(DISTINCT at.alumno_id) FROM asignaciones_tutor at JOIN ciclos_lectivos ci ON ci.id = at.ciclo_id
     WHERE at.docente_id = t.id AND ci.activo = 1) AS alumnos_asignados
FROM docentes t LEFT JOIN especialidades e ON e.id = t.especialidad_id
"""

docentes = Entity(
    "docentes", "docentes", "Docente tutor", "Docentes y tutores", "docentes",
    fields=[
        F("apellido", "Apellido", required=True, maxlen=80),
        F("nombre", "Nombre", required=True, maxlen=80),
        F("dni", "DNI", "dni", required=True, unique=True),
        F("email", "Correo electrónico", "email"),
        F("telefono", "Teléfono", "tel", maxlen=40),
        F("especialidad_id", "Especialidad", "select", coerce=int, choices=lambda: services.choices(services.lista_especialidades())),
        F("cargo", "Cargo o función", maxlen=100),
        F("activo", "Activo", "checkbox", default=1),
    ],
    columns=[C("docente", "Apellido y nombre", link=True), C("dni", "DNI"), C("email", "Correo"), C("telefono", "Teléfono"),
             C("especialidad", "Especialidad"), C("cargo", "Cargo"), C("alumnos_asignados", "Alumnos asignados (ciclo activo)"),
             C("activo", "Activo", "bool")],
    select=SELECT, search=("t.apellido", "t.nombre", "t.dni", "t.email"),
    filters=[dict(name="especialidad", label="Especialidad", expr="t.especialidad_id", choices=lambda: services.choices(services.lista_especialidades())),
             dict(name="activo", label="Estado", expr="t.activo", choices=[(1, "Activos"), (0, "Inactivos")])],
    order="t.apellido, t.nombre", detail=True, nuevo_label="Nuevo docente",
    deps=(("SELECT COUNT(*) FROM practicas WHERE tutor_id = ? AND eliminado_en IS NULL", "práctica(s) a cargo"),
          ("SELECT COUNT(*) FROM usuarios WHERE docente_id = ? AND eliminado_en IS NULL", "usuario(s) vinculado(s)")),
)

bp = docentes.blueprint()


@bp.route("/<int:id>")
@perm_required("docentes.ver")
def ficha(id):
    d = q1(SELECT + " WHERE t.id = ?", (id,))
    if not d or d["eliminado_en"]:
        abort(404)
    ciclo = request.args.get("ciclo_id") or (services.ciclo_activo() or {"id": ""})["id"]
    asignados = q("""SELECT at.id AS asig_id, a.id, a.apellido || ', ' || a.nombre AS alumno, a.dni, c.nombre AS curso,
                            dv.nombre AS division, e.nombre AS especialidad, ci.anio
                     FROM asignaciones_tutor at JOIN alumnos a ON a.id = at.alumno_id AND a.eliminado_en IS NULL
                     JOIN cursos c ON c.id = a.curso_id LEFT JOIN divisiones dv ON dv.id = a.division_id
                     LEFT JOIN especialidades e ON e.id = a.especialidad_id JOIN ciclos_lectivos ci ON ci.id = at.ciclo_id
                     WHERE at.docente_id = ? AND at.ciclo_id = ? ORDER BY a.apellido, a.nombre""", (id, ciclo))
    candidatos = q("""SELECT a.id, a.apellido || ', ' || a.nombre AS alumno, c.nombre AS curso, dv.nombre AS division, e.nombre AS especialidad
                      FROM alumnos a JOIN cursos c ON c.id = a.curso_id LEFT JOIN divisiones dv ON dv.id = a.division_id
                      LEFT JOIN especialidades e ON e.id = a.especialidad_id
                      WHERE a.eliminado_en IS NULL AND a.estado_academico IN ('Regular','Repitente') AND c.requiere_pp = 1
                        AND a.id NOT IN (SELECT alumno_id FROM asignaciones_tutor WHERE docente_id = ? AND ciclo_id = ?)
                      ORDER BY c.orden, a.apellido, a.nombre""", (id, ciclo))
    practicas = q("""SELECT p.*, ci.anio, em.razon_social AS empresa,
                     (SELECT COUNT(*) FROM alumnos_practicas ap WHERE ap.practica_id = p.id AND ap.eliminado_en IS NULL) AS n
                     FROM practicas p JOIN ciclos_lectivos ci ON ci.id = p.ciclo_id JOIN empresas em ON em.id = p.empresa_id
                     WHERE p.tutor_id = ? AND p.eliminado_en IS NULL ORDER BY ci.anio DESC, p.numero DESC""", (id,))
    return render_template("docentes/ficha.html", d=d, asignados=asignados, candidatos=candidatos, practicas=practicas,
                           ciclo_id=int(ciclo) if str(ciclo).isdigit() else None, ciclos=services.lista_ciclos())


@bp.route("/<int:id>/asignar", methods=["POST"])
@perm_required("docentes.editar")
def asignar(id):
    if not q1("SELECT 1 FROM docentes WHERE id = ? AND eliminado_en IS NULL", (id,)):
        abort(404)
    ciclo = request.form.get("ciclo_id", "")
    ids = [int(x) for x in request.form.getlist("alumno_ids") if x.isdigit()]
    if not ciclo.isdigit() or not ids:
        flash("Seleccione el ciclo lectivo y al menos un alumno.", "danger")
        return redirect(url_for("docentes.ficha", id=id))
    n = 0
    for aid in ids:
        if q1("SELECT 1 FROM alumnos WHERE id = ? AND eliminado_en IS NULL", (aid,)):
            cur = ex("INSERT OR IGNORE INTO asignaciones_tutor(docente_id, alumno_id, ciclo_id, creado_en, creado_por) VALUES (?,?,?,?,?)",
                     (id, aid, int(ciclo), now(), g.user["id"]), commit=False)
            n += cur.rowcount
    audit("docentes", id, "asignar_alumnos", {"ciclo_id": int(ciclo), "alumnos": ids})
    commit()
    flash(f"{n} alumno(s) asignado(s) al tutor.", "success")
    return redirect(url_for("docentes.ficha", id=id, ciclo_id=ciclo))


@bp.route("/<int:id>/quitar/<int:asig_id>", methods=["POST"])
@perm_required("docentes.editar")
def quitar(id, asig_id):
    row = q1("SELECT * FROM asignaciones_tutor WHERE id = ? AND docente_id = ?", (asig_id, id))
    if not row:
        abort(404)
    ex("DELETE FROM asignaciones_tutor WHERE id = ?", (asig_id,), commit=False)
    audit("docentes", id, "quitar_alumno", {"alumno_id": row["alumno_id"], "ciclo_id": row["ciclo_id"]})
    commit()
    flash("Asignación eliminada.", "success")
    return redirect(url_for("docentes.ficha", id=id, ciclo_id=row["ciclo_id"]))


def blueprints():
    return [bp]
