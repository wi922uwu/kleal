# One parametric image for every Kleal service. Build arg SERVICE selects which one.
# shared/ is COPIED into each image (never a runtime mount) so services stay decoupled.
FROM python:3.12-slim

ARG SERVICE
ENV SERVICE=${SERVICE}
WORKDIR /app

# stdlib-only services — no pip install needed. Copy the shared lib next to the service so the
# app's sys.path fallback (./shared) finds it inside the container.
COPY shared/ /app/shared/
COPY services/${SERVICE}/ /app/

# Each app.py reads its own *_PORT env; the compose file sets ports + LLM_URL/HUB_* wiring.
CMD ["python", "-u", "app.py"]
