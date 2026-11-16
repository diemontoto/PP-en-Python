FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PP_INSTANCE=/data \
    TZ=America/Argentina/Buenos_Aires

WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --system --uid 10001 pp && mkdir /data && chown pp:pp /data && chmod +x docker-entrypoint.sh
USER pp
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=4).status == 200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "-w", "3", "--timeout", "120", "-b", "0.0.0.0:8000", "--access-logfile", "-", "wsgi:app"]
