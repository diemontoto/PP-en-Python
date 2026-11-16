# Sistema de Gestión de Prácticas Profesionalizantes

Sistema web para escuelas técnicas: alumnos, empresas, prácticas, asistencia y horas, documentación, tutores, evaluaciones, dashboard e informes PDF/Excel, con roles y auditoría.

**Stack:** Python · Flask · SQLite · Jinja2 · HTML/CSS/JS propios · openpyxl · reportlab.

## Inicio rápido
```bash
pip install -r requirements.txt
python manage.py seed-demo          # datos ficticios (opcional)
python manage.py run                # http://127.0.0.1:5000   (admin / Demo1234)
```
Para producción: `python manage.py create-admin admin` y ver `docs/DESPLIEGUE.md`.

## Documentación
- `docs/ARQUITECTURA.md` — arquitectura, diagrama ER (`docs/diagrama_er.png`), reglas de negocio, seguridad, migración a PostgreSQL
- `docs/MANUAL_INSTALACION.md` — instalación, primeros pasos, respaldos
- `docs/MANUAL_USUARIO.md` — uso por módulo y matriz de permisos
- `docs/DESPLIEGUE.md` — servidor (nginx + gunicorn + systemd), HTTPS, Docker, respaldos automáticos
- `schema.sql` — esquema completo de la base de datos

## Pruebas
`python -m unittest discover -s tests -v` (26 pruebas: seguridad, permisos, CRUD, flujo de prácticas, documentos, importación, informes, respaldos).
