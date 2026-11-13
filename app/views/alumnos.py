"""Gestión de alumnos: ABM, ficha individual (web y PDF) e importación masiva desde Excel."""
import io
import re
import unicodedata
from datetime import date, datetime

from flask import Response, abort, flash, g, redirect, render_template, request, url_for
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .. import auth, pdfs, services
from ..crud import C, Entity, F
from ..db import audit, commit, ex, get_db, now, q, q1
from ..auth import perm_required

ESTADOS_ACAD = ["Regular", "Repitente", "Libre", "Egresado", "Baja / Pase"]


def _fields(row=None):
    return [
        F("legajo", "N° de legajo", required=True, unique=True, maxlen=30),
        F("dni", "DNI", "dni", required=True, unique=True),
        F("apellido", "Apellido", required=True, maxlen=80),
        F("nombre", "Nombre", required=True, maxlen=80),
        F("fecha_nacimiento", "Fecha de nacimiento", "date"),
        F("domicilio", "Domicilio", maxlen=200),
        F("telefono", "Teléfono", "tel", maxlen=40),
        F("email", "Correo electrónico", "email"),
        F("curso_id", "Curso", "select", required=True, coerce=int, choices=lambda: services.choices(services.lista_cursos())),
        F("division_id", "División", "select", coerce=int, choices=lambda: services.choices(services.lista_divisiones())),
        F("especialidad_id", "Especialidad técnica", "select", coerce=int, choices=lambda: services.choices(services.lista_especialidades())),
        F("ciclo_id", "Año de cursada (ciclo lectivo)", "select", coerce=int, required=True,
          default=lambda: (services.ciclo_activo() or {"id": ""})["id"],
          choices=lambda: [(c["id"], c["anio"]) for c in services.lista_ciclos()]),
        F("estado_academico", "Estado académico", "select", required=True, default="Regular", choices=[(e, e) for e in ESTADOS_ACAD]),
        F("observaciones", "Observaciones", "textarea", cols=2),
        F("tutor_legal_nombre", "Responsable / tutor legal: nombre", maxlen=120),
        F("tutor_legal_parentesco", "Parentesco", maxlen=40),
        F("tutor_legal_telefono", "Responsable: teléfono", "tel", maxlen=40),
        F("tutor_legal_email", "Responsable: correo electrónico", "email"),
    ]


def _before(vals, row, errors):
    e = services.edad(vals.get("fecha_nacimiento"))
    if vals.get("fecha_nacimiento") and "fecha_nacimiento" not in errors:
        if vals["fecha_nacimiento"] > date.today().isoformat():
            errors["fecha_nacimiento"] = "La fecha de nacimiento no puede ser futura."
        elif e is not None and e < 18 and not vals.get("tutor_legal_nombre"):
            errors["tutor_legal_nombre"] = "El alumno es menor de edad: debe registrar al responsable o tutor legal."


SELECT = """
SELECT t.*, t.apellido || ', ' || t.nombre AS alumno, c.nombre AS curso, d.nombre AS division,
       e.nombre AS especialidad, ci.anio AS ciclo,
       COALESCE((SELECT ap.estado FROM alumnos_practicas ap JOIN practicas p ON p.id = ap.practica_id
                 WHERE ap.alumno_id = t.id AND ap.eliminado_en IS NULL AND p.eliminado_en IS NULL
                 ORDER BY p.ciclo_id DESC, ap.id DESC LIMIT 1),
                CASE WHEN c.requiere_pp = 1 AND t.estado_academico IN ('Regular','Repitente') THEN 'Sin asignar' END) AS pp_estado
FROM alumnos t
JOIN cursos c ON c.id = t.curso_id
LEFT JOIN divisiones d ON d.id = t.division_id
LEFT JOIN especialidades e ON e.id = t.especialidad_id
LEFT JOIN ciclos_lectivos ci ON ci.id = t.ciclo_id
"""

alumnos = Entity(
    "alumnos", "alumnos", "Alumno", "Alumnos", "alumnos", fields=_fields,
    columns=[C("legajo", "Legajo"), C("alumno", "Apellido y nombre", link=True), C("dni", "DNI"), C("curso", "Curso"),
             C("division", "División"), C("especialidad", "Especialidad"), C("ciclo", "Año cursada"),
             C("estado_academico", "Estado", "badge"), C("pp_estado", "Práctica", "badge")],
    select=SELECT,
    search=("t.apellido", "t.nombre", "t.dni", "t.legajo", "t.email"),
    filters=[
        dict(name="ciclo", label="Año de cursada", expr="t.ciclo_id", choices=lambda: [(c["id"], c["anio"]) for c in services.lista_ciclos()]),
        dict(name="curso", label="Curso", expr="t.curso_id", choices=lambda: services.choices(services.lista_cursos())),
        dict(name="division", label="División", expr="t.division_id", choices=lambda: services.choices(services.lista_divisiones())),
        dict(name="especialidad", label="Especialidad", expr="t.especialidad_id", choices=lambda: services.choices(services.lista_especialidades())),
        dict(name="estado", label="Estado académico", expr="t.estado_academico", choices=[(e, e) for e in ESTADOS_ACAD]),
    ],
    order="t.apellido, t.nombre", detail=True, before_save=_before, scope=lambda: auth.scope_alumnos("t"),
    access=auth.check_alumno_access,
    deps=(("SELECT COUNT(*) FROM alumnos_practicas WHERE alumno_id = ? AND eliminado_en IS NULL", "práctica(s) asignada(s)"),),
    nuevo_label="Nuevo alumno",
)

bp = alumnos.blueprint()


@bp.route("/<int:id>")
@perm_required("alumnos.ver")
def ficha(id):
    auth.check_alumno_access(id)
    a = q1(SELECT + " WHERE t.id = ?", (id,))
    if not a or a["eliminado_en"]:
        abort(404)
    practicas = services.ap_rows({"alumno_id": id}, order="ci.anio DESC, p.fecha_inicio DESC", scoped=False)
    docs = q("SELECT d.*, td.nombre AS tipo FROM documentos d JOIN tipos_documentos td ON td.id = d.tipo_documento_id "
             "WHERE d.alumno_id = ? AND d.eliminado_en IS NULL ORDER BY d.creado_en DESC", (id,))
    tutores = q("SELECT d.apellido || ', ' || d.nombre AS nombre, ci.anio FROM asignaciones_tutor at "
                "JOIN docentes d ON d.id = at.docente_id JOIN ciclos_lectivos ci ON ci.id = at.ciclo_id "
                "WHERE at.alumno_id = ? ORDER BY ci.anio DESC", (id,))
    historial = []
    if auth.can("configuracion.historial"):
        historial = q("SELECT * FROM historial_cambios WHERE tabla = 'alumnos' AND registro_id = ? ORDER BY id DESC LIMIT 30", (id,))
    return render_template("alumnos/ficha.html", a=a, practicas=practicas, docs=docs, tutores=tutores,
                           historial=historial, edad=services.edad(a["fecha_nacimiento"]))


@bp.route("/<int:id>/ficha.pdf")
@perm_required("alumnos.ver")
def ficha_pdf(id):
    auth.check_alumno_access(id)
    data = pdfs.ficha_alumno(id)
    if data is None:
        abort(404)
    audit("alumnos", id, "exportar", {"formato": "pdf ficha"})
    commit()
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="ficha_alumno_{id}.pdf"'})


# --------------------------------------------------------- importación Excel
COLS = [
    ("legajo", "Legajo"), ("apellido", "Apellido"), ("nombre", "Nombre"), ("dni", "DNI"),
    ("fecha_nacimiento", "Fecha de nacimiento"), ("domicilio", "Domicilio"), ("telefono", "Teléfono"),
    ("email", "Email"), ("curso", "Curso"), ("division", "División"), ("especialidad", "Especialidad"),
    ("ciclo", "Año de cursada"), ("estado_academico", "Estado académico"), ("observaciones", "Observaciones"),
    ("tutor_legal_nombre", "Responsable (nombre)"), ("tutor_legal_parentesco", "Parentesco"),
    ("tutor_legal_telefono", "Responsable (teléfono)"), ("tutor_legal_email", "Responsable (email)"),
]
ALIASES = {
    "legajo": "legajo", "nlegajo": "legajo", "nrolegajo": "legajo", "apellido": "apellido", "apellidos": "apellido",
    "nombre": "nombre", "nombres": "nombre", "dni": "dni", "documento": "dni",
    "fechadenacimiento": "fecha_nacimiento", "fechanacimiento": "fecha_nacimiento", "nacimiento": "fecha_nacimiento",
    "domicilio": "domicilio", "direccion": "domicilio", "telefono": "telefono", "celular": "telefono",
    "email": "email", "correo": "email", "correoelectronico": "email", "mail": "email",
    "curso": "curso", "anio": "curso", "division": "division", "especialidad": "especialidad",
    "aniodecursada": "ciclo", "ciclo": "ciclo", "ciclolectivo": "ciclo", "estado": "estado_academico",
    "estadoacademico": "estado_academico", "observaciones": "observaciones",
    "responsablenombre": "tutor_legal_nombre", "responsable": "tutor_legal_nombre", "tutorlegal": "tutor_legal_nombre",
    "parentesco": "tutor_legal_parentesco", "responsabletelefono": "tutor_legal_telefono",
    "responsableemail": "tutor_legal_email",
}


def _key(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]", "", s)


def _div_key(s):
    return re.sub(r"(?<=\d)[ao]$", "", _key(s))


def _date(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"fecha inválida: {s}")


def _text(v):
    if v is None:
        return None
    if isinstance(v, float) and v == int(v):
        v = int(v)
    s = str(v).strip()
    return s or None


def importar_excel(fh, solo_validar):
    wb = load_workbook(fh, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        return {"error": "El archivo está vacío."}
    idx = {}
    for i, h in enumerate(header):
        f = ALIASES.get(_key(h))
        if f and f not in idx:
            idx[f] = i
    faltan = [lbl for k, lbl in COLS[:4] if k not in idx]
    if faltan:
        return {"error": "Faltan columnas obligatorias: " + ", ".join(faltan)}

    cursos = {}
    for c in services.lista_cursos():
        m = re.match(r"\s*(\d+)", c["nombre"])
        cursos[m.group(1) if m else _key(c["nombre"])] = c["id"]
    divs = {_div_key(d["nombre"]): d["id"] for d in services.lista_divisiones()}
    esps = {}
    for e in q("SELECT id, nombre, codigo FROM especialidades WHERE eliminado_en IS NULL"):
        esps[_key(e["nombre"])] = e["id"]
        if e["codigo"]:
            esps[_key(e["codigo"])] = e["id"]
    ciclos = {str(c["anio"]): c["id"] for c in services.lista_ciclos()}
    activo = services.ciclo_activo()
    estados = {_key(e): e for e in ESTADOS_ACAD}

    res = {"creados": 0, "actualizados": 0, "errores": [], "total": 0}
    from .. import crud as _crud
    for n, row in enumerate(rows, start=2):
        get = lambda k: row[idx[k]] if k in idx and idx[k] < len(row) else None
        if all(v in (None, "") for v in row):
            continue
        res["total"] += 1
        errs, d = [], {}
        try:
            for k in ("legajo", "apellido", "nombre", "domicilio", "telefono", "observaciones",
                      "tutor_legal_nombre", "tutor_legal_parentesco", "tutor_legal_telefono"):
                d[k] = _text(get(k))
            for k in ("email", "tutor_legal_email"):
                v = _text(get(k))
                if v and not _crud.EMAIL_RE.match(v):
                    errs.append(f"{k}: correo inválido")
                d[k] = v.lower() if v else None
            dni = re.sub(r"[.\s-]", "", _text(get("dni")) or "")
            if not re.fullmatch(r"\d{7,9}", dni):
                errs.append("DNI inválido")
            d["dni"] = dni
            for k in ("legajo", "apellido", "nombre"):
                if not d[k]:
                    errs.append(f"{k} obligatorio")
            try:
                d["fecha_nacimiento"] = _date(get("fecha_nacimiento"))
            except ValueError as exc:
                errs.append(str(exc))
            cv = _text(get("curso"))
            cm = re.match(r"\s*(\d+)", cv or "")
            d["curso_id"] = cursos.get(cm.group(1)) if cm else cursos.get(_key(cv))
            if not d["curso_id"]:
                errs.append(f"curso no reconocido ({cv})")
            dv = _text(get("division"))
            d["division_id"] = divs.get(_div_key(dv)) if dv else None
            if dv and not d["division_id"]:
                errs.append(f"división no reconocida ({dv})")
            ev = _text(get("especialidad"))
            d["especialidad_id"] = esps.get(_key(ev)) if ev else None
            if ev and not d["especialidad_id"]:
                errs.append(f"especialidad no reconocida ({ev})")
            cl = _text(get("ciclo"))
            d["ciclo_id"] = ciclos.get(cl) if cl else (activo["id"] if activo else None)
            if cl and not d["ciclo_id"]:
                errs.append(f"año de cursada no cargado ({cl})")
            st = _text(get("estado_academico"))
            d["estado_academico"] = estados.get(_key(st), None) if st else "Regular"
            if st and not d["estado_academico"]:
                errs.append(f"estado académico no válido ({st})")
            if d.get("fecha_nacimiento") and not errs:
                edad = services.edad(d["fecha_nacimiento"])
                if edad is not None and edad < 18 and not d["tutor_legal_nombre"]:
                    errs.append("menor de edad sin responsable / tutor legal")
            if errs:
                res["errores"].append((n, "; ".join(errs)))
                continue
            existing = q1("SELECT * FROM alumnos WHERE dni = ? AND eliminado_en IS NULL", (d["dni"],))
            clash = q1("SELECT id FROM alumnos WHERE legajo = ? AND eliminado_en IS NULL AND id <> ?",
                       (d["legajo"], existing["id"] if existing else 0))
            if clash:
                res["errores"].append((n, f"el legajo {d['legajo']} ya pertenece a otro alumno"))
                continue
            if existing:
                upd = {k: v for k, v in d.items() if v is not None}
                sets = ", ".join(f"{k} = ?" for k in upd) + ", modificado_en = ?, modificado_por = ?"
                ex(f"UPDATE alumnos SET {sets} WHERE id = ?", list(upd.values()) + [now(), g.user["id"], existing["id"]], commit=False)
                audit("alumnos", existing["id"], "modificar", {"origen": "importación Excel", "fila": n})
                res["actualizados"] += 1
            else:
                cols = list(d) + ["creado_en", "creado_por"]
                cur = ex(f"INSERT INTO alumnos({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         list(d.values()) + [now(), g.user["id"]], commit=False)
                audit("alumnos", cur.lastrowid, "crear", {"origen": "importación Excel", "fila": n})
                res["creados"] += 1
        except Exception as exc:  # fila defectuosa: no interrumpe el resto
            res["errores"].append((n, f"error inesperado: {exc}"))
    if solo_validar:
        get_db().rollback()
    else:
        commit()
    audit("alumnos", None, "importar", {"creados": res["creados"], "actualizados": res["actualizados"],
                                        "errores": len(res["errores"]), "solo_validar": bool(solo_validar)})
    commit()
    return res


@bp.route("/importar", methods=["GET", "POST"])
@perm_required("alumnos.editar")
def importar():
    res = None
    if request.method == "POST":
        f = request.files.get("archivo")
        if not f or not f.filename.lower().endswith(".xlsx"):
            flash("Seleccione un archivo Excel (.xlsx).", "danger")
        else:
            try:
                res = importar_excel(io.BytesIO(f.read()), solo_validar=bool(request.form.get("solo_validar")))
            except Exception:
                flash("No se pudo leer el archivo. Verifique que sea un .xlsx válido.", "danger")
                res = None
            if res and res.get("error"):
                flash(res["error"], "danger")
                res = None
            elif res:
                if request.form.get("solo_validar"):
                    flash("Validación finalizada. No se guardó ningún dato.", "info")
                else:
                    flash(f"Importación finalizada: {res['creados']} creados, {res['actualizados']} actualizados.", "success")
    return render_template("alumnos/importar.html", res=res, cols=COLS)


@bp.route("/plantilla.xlsx")
@perm_required("alumnos.editar")
def plantilla():
    wb = Workbook()
    ws = wb.active
    ws.title = "Alumnos"
    ws.append([lbl for _k, lbl in COLS])
    ws.append(["1001", "Pérez", "Juan Carlos", "40123456", "15/05/2008", "Calle 123", "3794-123456", "juan@example.com",
               "6° año", "1ª", "Programación", date.today().year, "Regular", "", "María Pérez", "Madre", "3794-654321", ""])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E3A5F")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for i in range(1, len(COLS) + 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = 22
    ayuda = wb.create_sheet("Instrucciones")
    ayuda.append(["Columnas obligatorias: Legajo, Apellido, Nombre, DNI, Curso."])
    ayuda.append(["Si el DNI ya existe, el alumno se ACTUALIZA; si no existe, se crea."])
    ayuda.append(["Los menores de 18 años requieren Responsable (nombre)."])
    ayuda.append(["Cursos válidos: " + ", ".join(c["nombre"] for c in services.lista_cursos())])
    ayuda.append(["Divisiones válidas: " + ", ".join(d["nombre"] for d in services.lista_divisiones())])
    ayuda.append(["Especialidades válidas: " + ", ".join(e["nombre"] for e in services.lista_especialidades())])
    ayuda.append(["Estados académicos válidos: " + ", ".join(ESTADOS_ACAD)])
    ayuda.column_dimensions["A"].width = 120
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="plantilla_alumnos.xlsx"'})


def blueprints():
    return [bp]
