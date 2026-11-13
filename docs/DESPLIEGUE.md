# Despliegue en un servidor

Ejemplo para Ubuntu/Debian con **nginx + gunicorn + systemd**. En Windows Server use `waitress-serve --listen=127.0.0.1:8000 wsgi:app` como servicio (NSSM) detrás de IIS o nginx.

## 1. Preparar
```bash
sudo adduser --system --group pp
sudo mkdir -p /opt/practicas-pp && sudo chown pp: /opt/practicas-pp
sudo -u pp bash -c 'cd /opt/practicas-pp && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt'
# copie aquí el código y luego:
sudo -u pp /opt/practicas-pp/venv/bin/python manage.py create-admin admin
```

## 2. Servicio systemd — `/etc/systemd/system/practicas-pp.service`
```ini
[Unit]
Description=Practicas Profesionalizantes
After=network.target

[Service]
User=pp
WorkingDirectory=/opt/practicas-pp
Environment=PP_HTTPS=1
Environment=PP_INSTANCE=/var/lib/practicas-pp
ExecStart=/opt/practicas-pp/venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo mkdir -p /var/lib/practicas-pp && sudo chown pp: /var/lib/practicas-pp
sudo systemctl enable --now practicas-pp
```

## 3. nginx con HTTPS — `/etc/nginx/sites-available/practicas-pp`
```nginx
server {
    listen 80;
    server_name practicas.miescuela.edu.ar;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name practicas.miescuela.edu.ar;
    ssl_certificate     /etc/letsencrypt/live/practicas.miescuela.edu.ar/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/practicas.miescuela.edu.ar/privkey.pem;
    client_max_body_size 20m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Certificado gratuito: `sudo certbot --nginx -d practicas.miescuela.edu.ar`.

## 4. Copias de seguridad automáticas
`sudo crontab -u pp -e`:
```
30 2 * * *  PP_INSTANCE=/var/lib/practicas-pp /opt/practicas-pp/venv/bin/python /opt/practicas-pp/manage.py backup --keep 30
```
Copie además `/var/lib/practicas-pp/backups/` a otro equipo o a la nube (rsync, rclone) con una frecuencia al menos semanal.

## 5. Docker (alternativa)
```bash
docker build -t practicas-pp .
docker run --rm -v pp_data:/data practicas-pp python manage.py create-admin admin
docker run -d --name pp -p 8000:8000 -v pp_data:/data -e PP_HTTPS=1 practicas-pp
```

## 6. Actualizaciones
Haga un respaldo, reemplace el código (no toque `instance/`), `pip install -r requirements.txt`, reinicie el servicio y ejecute las pruebas.

## 7. Lista de verificación de seguridad
- [ ] HTTPS activo y `PP_HTTPS=1`.
- [ ] Contraseñas de demostración eliminadas (o no cargó datos de demostración).
- [ ] `instance/` fuera del alcance público y con permisos sólo para el usuario del servicio.
- [ ] Respaldos diarios y copia externa semanal; restauración probada al menos una vez.
- [ ] Cada persona con su usuario y el perfil mínimo necesario.
- [ ] Revisión periódica de **Configuración → Historial**.
