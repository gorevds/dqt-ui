FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY dqt/ dqt/
RUN pip install --no-cache-dir -e . gunicorn

EXPOSE 8050
ENV DQT_HOST=0.0.0.0 DQT_PORT=8050

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8050", "--timeout", "180", "dqt.app.main:server"]
