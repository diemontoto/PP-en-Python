"""Repositorio digital de documentación: carga segura de archivos, revisión y control documental."""
import os
import re
import uuid

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request, send_from_directory, url_for)

from .. import auth, services
from ..auth import perm_required, safe_next
from ..db import audit, commit, ex, norm, now, q, q1, today

bp = Blueprint("documentos", __name__, url_prefix="/documentos")

ALLOWED = {
    "pdf": ("application/pdf", [b"%PDF"]),
    "doc": ("application/msword", [b"\xd0\xcf\x11\xe0"]),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", [b"PK\x03\x04"]),
    "xls": ("application/vnd.ms-excel", [b"\xd0\xcf\x11\xe0"]),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", [b"PK\x03\x04"]),
    "png": ("image/png", [b"\x89PNG"]),
    "jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    "jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
}
MAX_BYTES = 15 * 1024 * 1024
ESTADOS_DOC = ["Pendiente de revisión", "Aprobado", "Observado"]


def _scope_sql():
    """Documentos visibles para el usuario (los tutores sólo ven los de sus alumnos/prácticas)."""
    if auth.tutor_docente() is None:
        return "1=1", []
    sa, pa = auth.scope_alumnos("a")
    sp, pp = auth.scope_practicas("p")
    return (f"((d.alumno_id IS NULL OR d.alumno_id IN (SELECT a.id FROM alumnos a WHERE {sa})) "
            f"AND (d.practica_id IS NULL OR d.practica_id IN (SELECT p.id FROM practicas p WHERE {sp})))", pa + pp)


def _check_access(d):
    if d["alumno_id"]:
        auth.check_alumno_access(d["alumno_id"])
    if d["practica_id"]:
        auth.check_practica_access(d["practica_id"])


def _clean_name(name):
    name = os.path.basename((name or "documento").replace("\\", "/"))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "documento"
    return name[:150]


BASE = """
SELECT d.*, td.nombre AS tipo, td.ambito, a.apellido || ', ' || a.nombre AS alumno, em.razon_social AS empresa, p.numero AS practica,
       u.nombre AS cargado_por
FROM documentos d
JOIN tipos_documentos td ON td.id = d.tipo_documento_id
LEFT JOIN alumnos a ON a.id = d.alumno_id
LEFT JOIN empresas em ON em.id = d.empresa_id
LEFT JOIN practicas p ON p.id = d.practica_id
LEFT JOIN usuarios u ON u.id = d.creado_por
WHERE d.eliminado_en IS NULL
"""


@bp.route("/")
@perm_required("documentos.ver")
def lista():
    args = request.args
    where, params = [], []
    sql, sp = _scope_sql()
    where.append(sql)
    params += sp
    for key, col in (("tipo", "d.tipo_documento_id"), ("estado", "d.estado"), ("empresa", "d.empresa_id"), ("practica", "d.practica_id")):
        if args.get(key):
            where.append(f"{col} = ?")
            params.append(args[key])
    if args.get("vencidos") == "1":
        where.append("d.vencimiento IS NOT NULL AND d.vencimiento < ?")
        params.append(today())
    if args.get("q"):
        for w in norm(args["q"]).split():
            where.append("norm(COALESCE(d.nombre_original,'') || ' ' || COALESCE(a.apellido,'') || ' ' || COALESCE(a.nombre,'') || ' ' || COALESCE(a.dni,'') || ' ' || "
                         "COALESCE(em.razon_social,'') || ' ' || COALESCE(p.numero,'') || ' ' || td.nombre) LIKE ?")
            params.append(f"%{w}%")
    rows = q(BASE + " AND " + " AND ".join(where) + " ORDER BY d.creado_en DESC LIMIT 500", params)
    return render_template("documentos/lista.html", rows=rows, args=args, hoy=today(),
                           tipos=q("SELECT id, nombre FROM tipos_documentos WHERE eliminado_en IS NULL ORDER BY nombre"),
                           estados=ESTADOS_DOC, empresas=services.lista_empresas(False))


@bp.route("/control")
@perm_required("documentos.ver")
def control():
    ciclo = services.ciclo_activo()
    args = request.args
    filtros = {"ciclo_id": args.get("ciclo_id", ciclo["id"] if ciclo and "ciclo_id" not in args else ""),
               "especialidad_id": args.get("especialidad_id"), "curso_id": args.get("curso_id"), "empresa_id": args.get("empresa_id")}
    rows = [r for r in services.ap_rows(filtros, order="a.apellido, a.nombre") if r["estado"] not in ("Aprobada", "Desaprobada")]
    if args.get("estado"):
        rows = [r for r in rows if r["docs_estado"] == args["estado"]]
    tipos, det = services.doc_detail_map(rows)
    return render_template("documentos/control.html", rows=rows, tipos=tipos, det=det, args=args, f=filtros,
                           ciclos=services.lista_ciclos(), especialidades=services.lista_especialidades(), cursos=services.lista_cursos(),
                           empresas=services.lista_empresas(False))


def _opciones():
    alumnos = q("SELECT id, apellido || ', ' || nombre || ' (' || dni || ')' AS n FROM alumnos WHERE eliminado_en IS NULL ORDER BY apellido, nombre LIMIT 3000")
    sql, sp = auth.scope_practicas("p")
    practicas = q(f"SELECT p.id, p.numero || ' · ' || em.razon_social || ' · ' || p.proyecto AS n FROM practicas p "
                  f"JOIN empresas em ON em.id = p.empresa_id WHERE p.eliminado_en IS NULL AND {sql} ORDER BY p.numero DESC LIMIT 1000", sp)
    return dict(tipos=q("SELECT id, nombre, ambito, obligatorio FROM tipos_documentos WHERE eliminado_en IS NULL AND activo = 1 ORDER BY nombre"),
                alumnos=alumnos, practicas=practicas, empresas=services.lista_empresas(False), estados=ESTADOS_DOC)


@bp.route("/nuevo", methods=["GET", "POST"])
@perm_required("documentos.editar")
def nuevo():
    nxt = safe_next(request.values.get("next"))
    values = {k: request.values.get(k, "") for k in ("tipo_documento_id", "alumno_id", "practica_id", "empresa_id", "vencimiento", "observaciones")}
    if request.method == "POST":
        errors = []
        f = request.files.get("archivo")
        tipo = q1("SELECT * FROM tipos_documentos WHERE id = ? AND eliminado_en IS NULL AND activo = 1",
                  (values["tipo_documento_id"],)) if values["tipo_documento_id"].isdigit() else None
        if not tipo:
            errors.append("Seleccione el tipo de documento.")
        ids = {}
        for k, tabla in (("alumno_id", "alumnos"), ("practica_id", "practicas"), ("empresa_id", "empresas")):
            v = values[k]
            if v:
                if not v.isdigit() or not q1(f"SELECT 1 FROM {tabla} WHERE id = ? AND eliminado_en IS NULL", (int(v),)):
                    errors.append("Registro vinculado inexistente.")
                else:
                    ids[k] = int(v)
        if tipo:
            req = {"alumno": "alumno_id", "practica": "practica_id", "empresa": "empresa_id"}[tipo["ambito"]]
            if req not in ids:
                errors.append({"alumno_id": "Este tipo de documento corresponde a un alumno: seleccione el alumno.",
                               "practica_id": "Este tipo de documento corresponde a una práctica: seleccione la práctica.",
                               "empresa_id": "Este tipo de documento corresponde a una empresa: seleccione la empresa."}[req])
            else:
                # se conservan sólo los vínculos coherentes con el ámbito del tipo
                keep = {req} | ({"alumno_id"} if tipo["ambito"] == "practica" else set())
                ids = {k: v for k, v in ids.items() if k in keep}
        if values["vencimiento"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", values["vencimiento"]):
            errors.append("Fecha de vencimiento inválida.")
        name = ext = None
        data = b""
        if not f or not f.filename:
            errors.append("Seleccione el archivo a subir.")
        else:
            name = _clean_name(f.filename)
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            data = f.read(MAX_BYTES + 1)
            if ext not in ALLOWED:
                errors.append("Formato no permitido. Se admiten: PDF, Word, Excel e imágenes (PNG/JPG).")
            elif len(data) > MAX_BYTES:
                errors.append("El archivo supera los 15 MB.")
            elif not data:
                errors.append("El archivo está vacío.")
            elif not any(data.startswith(sig) for sig in ALLOWED[ext][1]):
                errors.append("El contenido del archivo no corresponde a su extensión.")
        if not errors:
            if "alumno_id" in ids:
                auth.check_alumno_access(ids["alumno_id"])
            if "practica_id" in ids:
                auth.check_practica_access(ids["practica_id"])
            stored = uuid.uuid4().hex + "." + ext
            with open(os.path.join(current_app.config["UPLOAD_DIR"], stored), "wb") as fh:
                fh.write(data)
            cur = ex("INSERT INTO documentos(tipo_documento_id, alumno_id, empresa_id, practica_id, nombre_original, archivo, mime, tamano, "
                     "estado, vencimiento, observaciones, creado_en, creado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (tipo["id"], ids.get("alumno_id"), ids.get("empresa_id"), ids.get("practica_id"), name, stored, ALLOWED[ext][0], len(data),
                      "Pendiente de revisión", values["vencimiento"] or None, (values["observaciones"] or "").strip()[:500] or None,
                      now(), g.user["id"]), commit=False)
            audit("documentos", cur.lastrowid, "crear", {"tipo": tipo["nombre"], "archivo": name, "vinculos": ids})
            commit()
            flash("Documento cargado. Queda pendiente de revisión.", "success")
            return redirect(nxt or url_for("documentos.lista"))
        for e in errors:
            flash(e, "danger")
    return render_template("documentos/nuevo.html", values=values, next=nxt or "", **_opciones())


def _get(id):
    d = q1(BASE + " AND d.id = ?", (id,))
    if not d:
        abort(404)
    _check_access(d)
    return d


@bp.route("/<int:id>/descargar")
@perm_required("documentos.ver")
def descargar(id):
    d = _get(id)
    audit("documentos", id, "descargar", {"archivo": d["nombre_original"]})
    commit()
    return send_from_directory(current_app.config["UPLOAD_DIR"], d["archivo"], as_attachment=True,
                               download_name=d["nombre_original"], mimetype=d["mime"] or "application/octet-stream")


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@perm_required("documentos.editar")
def editar(id):
    d = _get(id)
    nxt = safe_next(request.values.get("next"), url_for("documentos.lista"))
    if request.method == "POST":
        estado = request.form.get("estado")
        venc = request.form.get("vencimiento") or None
        obs = (request.form.get("observaciones") or "").strip()[:500] or None
        if estado not in ESTADOS_DOC:
            flash("Estado inválido.", "danger")
        elif venc and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", venc):
            flash("Fecha de vencimiento inválida.", "danger")
        elif estado == "Observado" and not obs:
            flash("Indique en observaciones qué debe corregirse.", "danger")
        else:
            ex("UPDATE documentos SET estado = ?, vencimiento = ?, observaciones = ?, modificado_en = ?, modificado_por = ? WHERE id = ?",
               (estado, venc, obs, now(), g.user["id"], id), commit=False)
            audit("documentos", id, "modificar", {"estado": [d["estado"], estado], "vencimiento": [d["vencimiento"], venc]})
            commit()
            flash("Documento actualizado.", "success")
            return redirect(nxt)
    return render_template("documentos/editar.html", d=d, estados=ESTADOS_DOC, next=nxt)


@bp.route("/<int:id>/estado", methods=["POST"])
@perm_required("documentos.editar")
def estado(id):
    d = _get(id)
    nuevo = request.form.get("estado")
    if nuevo in ("Aprobado", "Pendiente de revisión"):
        ex("UPDATE documentos SET estado = ?, modificado_en = ?, modificado_por = ? WHERE id = ?", (nuevo, now(), g.user["id"], id), commit=False)
        audit("documentos", id, "modificar", {"estado": [d["estado"], nuevo]})
        commit()
        flash(f"Documento marcado como «{nuevo}».", "success")
    return redirect(safe_next(request.form.get("next"), url_for("documentos.lista")))


@bp.route("/<int:id>/baja", methods=["POST"])
@perm_required("documentos.eliminar")
def baja(id):
    d = _get(id)
    ex("UPDATE documentos SET eliminado_en = ?, eliminado_por = ? WHERE id = ?", (now(), g.user["id"], id), commit=False)
    audit("documentos", id, "baja", {"archivo": d["nombre_original"], "tipo": d["tipo"]})
    commit()
    flash("Documento dado de baja (el archivo se conserva para auditoría).", "success")
    return redirect(safe_next(request.form.get("next"), url_for("documentos.lista")))


def blueprints():
    return [bp]
