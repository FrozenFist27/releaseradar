FROM python:3.12-slim

# Run as non-root; keep the image small and boring.
RUN useradd --create-home --shell /bin/bash radar
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Runtime state lives in a mounted volume.
RUN mkdir -p /app/data && chown -R radar:radar /app/data
USER radar
ENV RADAR_DB_PATH=/app/data/radar.db

CMD ["radar", "run"]
