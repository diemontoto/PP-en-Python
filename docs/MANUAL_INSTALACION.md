# Manual de instalación

## Requisitos
- Python 3.10 o superior (Windows, Linux o macOS).
- Paquetes: `Flask`, `openpyxl`, `reportlab` (y `waitress` o `gunicorn` para producción).
- Navegador moderno (Chrome, Edge, Firefox).

## Instalación (Linux / macOS)
```bash
cd practicas-pp
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py create-admin admin --nombre "Administrador"   # pide la contraseña
python manage.py run                                            # http://127.0.0.1:5000
```

## Instalación (Windows)
```bat
cd practicas-pp
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
py manage.py create-admin admin --nombre "Administrador"
py manage.py run
```

La primera vez se crea automáticamente la carpeta `instance/` con la base de datos (`practicas.db`), los documentos (`uploads/`), las copias de seguridad (`backups/`) y la clave secreta de sesión (`secret.key`). **Guarde `instance/` en sus respaldos.**

El usuario creado con `create-admin` debe cambiar la contraseña en su primer ingreso. Datos base ya cargados: roles y permisos, cursos 1° a 7° (6° y 7° requieren PP), divisiones 1ª a 4ª, tipos de documento y el ciclo lectivo del año en curso.

## Datos de demostración (opcional)
```bash
python manage.py seed-demo
```
Carga 40 alumnos, 10 empresas, 7 docentes y 15 prácticas ficticias. Usuarios: `admin`, `coordinador`, `tutor1`, `tutor2`, `consulta`, todos con la clave `Demo1234`. **No use datos de demostración en producción**: para empezar de cero borre la carpeta `instance/` y vuelva a crear el administrador.

## Primeros pasos tras instalar
1. Ingrese como administrador → **Configuración**: cargue nombre, CUE, dirección y teléfono de la escuela (aparecen en los informes PDF/Excel).
2. Revise **Ciclos lectivos**, **Especialidades** (horas de PP) y **Tipos de documento** (cuáles son obligatorios).
3. Cree los usuarios en **Usuarios**; a los tutores vincúlelos con su ficha de docente.
4. Importe los alumnos desde Excel (**Alumnos → Importar Excel**, hay plantilla descargable).

## Variables de entorno
| Variable | Uso |
|---|---|
| `PP_INSTANCE` | Carpeta de datos (por defecto `./instance`) |
| `PP_SECRET_KEY` | Clave secreta de sesión (si no se define se genera en `instance/secret.key`) |
| `PP_HTTPS=1` | Activa cookies `Secure` y HSTS (usar detrás de HTTPS) |

## Pruebas automáticas
```bash
python -m unittest discover -s tests -v
```
Las pruebas usan una base temporal; no tocan sus datos.

## Respaldo y recuperación
- Desde el sistema: **Configuración → Copias de seguridad** (crear, descargar, restaurar). Cada ZIP contiene la base de datos y todos los documentos.
- Por línea de comandos (programable): `python manage.py backup --keep 30`.
- Recuperación completa en otro servidor: instale el sistema, cree un administrador, ingrese y use «Restaurar» subiendo el ZIP.
