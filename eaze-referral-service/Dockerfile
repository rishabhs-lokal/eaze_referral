# syntax=docker/dockerfile:1

# One image serves the API and the referral page it talks to. They were separate artifacts until
# now, and separate was defensible — different runtimes, and the web bundle is tier-specific
# while the Python image was not. What tipped it is that the page is called from the user's
# browser: separate hosts means a second DNS record, a second TLS cert, and CORS. Same origin
# means none of those exist to be misconfigured.
#
# The cost, stated plainly: this image is now tier-specific. EXPO_PUBLIC_REWARD_COINS is inlined
# into the JS at build time, so the 1000- and 500-coin builds are genuinely different bytes. The
# "one image, coin amount is pure config" property is gone, and tier-500 will need its own build
# as well as its own database.
#
# BUILD CONTEXT IS THE REPOSITORY ROOT, not eaze-referral-service/ — stage one needs the
# frontend, which lives in a sibling directory. Devtron: Build Context = `.`,
# Dockerfile Path = `eaze-referral-service/Dockerfile`.

FROM node:20-bookworm-slim AS web

WORKDIR /build

# Dependencies before sources, so a copy change does not reinstall node_modules.
COPY eaze-referral-app/package.json eaze-referral-app/package-lock.json ./
RUN npm ci

COPY eaze-referral-app/ ./

# EXPO_PUBLIC_* are read at build time and burned into the bundle — they cannot be changed by a
# ConfigMap afterwards. REWARD_COINS has no default on purpose: the app throws at import if it
# is missing or not a positive number, so a build that forgot it fails here rather than shipping
# a page that quietly promises the wrong amount.
ARG EXPO_PUBLIC_REWARD_COINS
# Empty means same-origin: the page is served by the very API it calls, so requests go to
# /api/referral/... relative to wherever it was loaded from. No host to keep in sync, and no
# CORS. src/api/config.ts uses ?? rather than ||, so an empty string is kept rather than
# falling through to the localhost dev default.
ARG EXPO_PUBLIC_API_BASE_URL=""
ARG EXPO_PUBLIC_DOWNLOAD_URL="https://eaze.onelink.me/x8qY/eirps9xf"

ENV EXPO_PUBLIC_REWARD_COINS=${EXPO_PUBLIC_REWARD_COINS} \
    EXPO_PUBLIC_API_BASE_URL=${EXPO_PUBLIC_API_BASE_URL} \
    EXPO_PUBLIC_DOWNLOAD_URL=${EXPO_PUBLIC_DOWNLOAD_URL}

RUN npx expo export --platform web


FROM python:3.14-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY eaze-referral-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY eaze-referral-service/app ./app
COPY eaze-referral-service/alembic ./alembic
COPY eaze-referral-service/alembic.ini .
# Operational scripts need to be runnable against a real deployment, not just a dev checkout —
# scripts/check_redash.py in particular is meant to be run wherever the REDASH_* env vars
# actually live, which is inside this image.
COPY eaze-referral-service/scripts ./scripts

# The built referral page. app/main.py mounts this at / after the API routers, so /api/referral,
# /healthz and /r/{code} still win; everything else falls through to the page.
COPY --from=web /build/dist ./web

RUN chown -R app:app /srv
USER app

EXPOSE 8000

# One process per pod — Kubernetes replicas provide horizontal scaling, so no gunicorn/multi-worker
# wrapper is needed inside the container (that would complicate graceful shutdown and logging for
# no benefit under this deployment model).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
