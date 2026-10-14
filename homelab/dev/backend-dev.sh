#!/bin/sh
# Homelab fork: dev-stack entrypoint for the backend container.
#
# The image's own docker/start.sh cannot be reused because it execs uvicorn
# without --reload. This does the part of it that matters in dev (create the
# data dirs) and starts uvicorn reloading on source changes. The image's
# frontend/dist/env.js is left empty, so the SPA served on :8092 uses
# same-origin API paths.
set -e

DATA=/app/backend/data
for d in user_images server_images activity_media activity_thumbnails \
         activity_files/processed activity_files/bulk_import/import_errors \
         activity_files/strava_import/activities activity_files/strava_import/media \
         activity_files/strava_import/import_errors; do
    mkdir -p "$DATA/$d"
done
mkdir -p /app/backend/logs

cd /app/backend
# Watch only the code, not the data and logs mounted beneath it.
exec uvicorn main:app --host 0.0.0.0 --port 8080 \
    --log-level "${LOG_LEVEL:-info}" \
    --reload --reload-dir /app/backend \
    --reload-exclude 'data/*' --reload-exclude 'logs/*'
