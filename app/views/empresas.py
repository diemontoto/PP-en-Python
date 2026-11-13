"""Empresas e instituciones, referentes y fichas con historial de alumnos."""
from flask import abort, render_template

from .. import auth, services
from ..auth import perm_required
from ..crud import C, Entity, F
from ..db import q, q1

OCUP = ",".join(f"'{e}'" for e in services.OCUPAN_VACANTE)

SELECT = f"""
SELECT t.*,
  (SELECT r.nombre FROM referentes_empresas r WHERE r.empresa_id = t.id AND r.activo = 1 AND r.eliminado_en IS NULL ORDER BY r.id LIMIT 1) AS referente,
  (SELECT COUNT(*) FROM alumnos_practicas ap JOIN practicas p ON p.id = ap.practica_id
     WHERE p.empresa_id = t.id AND ap.estado IN ({OCUP}) AND ap.eliminado_en IS NULL AND p.eliminado_en IS NULL) AS ocupadas,
  MAX(0, t.vacantes - (SELECT COUNT(*) FROM alumnos_practicas ap JOIN practicas p ON p.id = ap.practica_id
     WHERE p.empresa_id = t.id AND ap.estado IN ({OCUP}) AND ap.eliminado_en IS NULL AND p.eliminado_en IS NULL)) AS disponibles
FROM empresas t
"""

empresas = Entity(
    "empresas", "empresas", "Empresa", "Empresas e instituciones", "empresas",
    fields=[
        F("razon_social", "Razón social", required=True, maxlen=200, cols=2),
        F("nombre_fantasia", "Nombre de fantasía", maxlen=200),
        F("cuit", "CUIT", "cuit", unique=True, placeholder="30-12345678-9"),
        F("direccion", "Dirección", maxlen=200),
        F("localidad", "Localidad", maxlen=100),
        F("telefono", "Teléfono", "tel", maxlen=40),
        F("email", "Correo electrónico", "email"),
        F("actividad", "Actividad principal", maxlen=200),
        F("vacantes", "Cantidad de vacantes", "number", required=True, default=0, min=0, max=500,
          help="Plazas simultáneas que la empresa puede recibir."),
        F("activo", "Activa", "checkbox", default=1),
        F("observaciones", "Observaciones", "textarea", cols=2),
    ],
    columns=[C("razon_social", "Razón social", link=True), C("nombre_fantasia", "Nombre de fantasía"), C("cuit", "CUIT"),
             C("localidad", "Localidad"), C("telefono", "Teléfono"), C("referente", "Referente"),
             C("vacantes", "Vacantes"), C("disponibles", "Disponibles"), C("activo", "Activa", "bool")],
    select=SELECT, search=("t.razon_social", "t.nombre_fantasia", "t.cuit", "t.localidad", "t.actividad"),
    filters=[dict(name="activa", label="Estado", expr="t.activo", choices=[(1, "Activas"), (0, "Inactivas")])],
    order="t.razon_social", detail=True, nuevo_label="Nueva empresa",
    deps=(("SELECT COUNT(*) FROM practicas WHERE empresa_id = ? AND eliminado_en IS NULL", "práctica(s)"),),
)

referentes = Entity(
    "referentes", "referentes_empresas", "Referente", "Referentes de empresa", "empresas",
    fields=[
        F("empresa_id", "Empresa", "hidden", coerce=int, required=True),
        F("nombre", "Nombre y apellido", required=True, maxlen=150),
        F("cargo", "Cargo", maxlen=100),
        F("telefono", "Teléfono", "tel", maxlen=40),
        F("email", "Correo electrónico", "email"),
        F("activo", "Activo", "checkbox", default=1),
    ],
    columns=[C("nombre", "Nombre")], listable=False, nuevo_label="Nuevo referente",
)

bp = empresas.blueprint()
bp_ref = referentes.blueprint("/empresas/referentes")


@bp.route("/<int:id>")
@perm_required("empresas.ver")
def ficha(id):
    e = q1(SELECT + " WHERE t.id = ?", (id,))
    if not e or e["eliminado_en"]:
        abort(404)
    refs = q("SELECT * FROM referentes_empresas WHERE empresa_id = ? AND eliminado_en IS NULL ORDER BY activo DESC, nombre", (id,))
    practicas = q("""SELECT p.*, ci.anio, (SELECT COUNT(*) FROM alumnos_practicas ap WHERE ap.practica_id = p.id AND ap.eliminado_en IS NULL) AS n
                     FROM practicas p JOIN ciclos_lectivos ci ON ci.id = p.ciclo_id
                     WHERE p.empresa_id = ? AND p.eliminado_en IS NULL AND """ + auth.scope_practicas("p")[0] + " ORDER BY ci.anio DESC, p.numero DESC",
                  [id] + auth.scope_practicas("p")[1])
    historial = services.ap_rows({"empresa_id": id}, order="ci.anio DESC, a.apellido")
    docs = q("SELECT d.*, td.nombre AS tipo FROM documentos d JOIN tipos_documentos td ON td.id = d.tipo_documento_id "
             "WHERE d.empresa_id = ? AND d.practica_id IS NULL AND d.alumno_id IS NULL AND d.eliminado_en IS NULL ORDER BY d.creado_en DESC", (id,))
    return render_template("empresas/ficha.html", e=e, refs=refs, practicas=practicas, historial=historial, docs=docs)


def blueprints():
    return [bp, bp_ref]
