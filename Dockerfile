FROM python:3.12.6-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --upgrade "pip==24.2" \
    && pip install .

RUN useradd --create-home --uid 10001 overlap \
    && chown -R overlap:overlap /app
USER overlap

EXPOSE 8000

CMD ["python", "-m", "overlap_calculator.api.app"]
