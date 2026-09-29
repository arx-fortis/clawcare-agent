FROM python:3.14-slim
WORKDIR /app
COPY clawcare.py /app/clawcare.py
RUN useradd --uid 10001 --create-home clawcare && mkdir /data && chown clawcare:clawcare /data
USER clawcare
ENV CLAWCARE_DB=/data/clawcare.sqlite3 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
VOLUME /data
ENTRYPOINT ["python", "/app/clawcare.py"]
CMD ["worker"]
