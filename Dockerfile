FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PP_INSTANCE=/data
WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -r pp && mkdir /data && chown pp /data
USER pp
VOLUME /data
EXPOSE 8000
# Primer uso:  docker run --rm -v pp_data:/data IMAGEN python manage.py create-admin admin
CMD ["gunicorn", "-w", "3", "-b", "0.0.0.0:8000", "wsgi:app"]
