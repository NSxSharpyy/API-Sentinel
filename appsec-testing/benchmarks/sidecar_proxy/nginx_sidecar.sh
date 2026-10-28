#!/usr/bin/env bash
set -Eeuo pipefail

: "${UPSTREAM_URL:?UPSTREAM_URL is required}"
: "${LISTEN_PORT:?LISTEN_PORT is required}"

# This launcher is for the zero-artificial-delay performance experiment only.
python - "$UPSTREAM_URL" "$LISTEN_PORT" "${SIDECAR_OVERHEAD_MS:-0}" <<'PY'
import math
import re
import sys

upstream, listen_port, delay = sys.argv[1:]
if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", upstream):
    raise SystemExit("UPSTREAM_URL must be http://127.0.0.1:PORT")
if not listen_port.isdigit() or not 1 <= int(listen_port) <= 65535:
    raise SystemExit("LISTEN_PORT must be between 1 and 65535")
try:
    delay_value = float(delay)
except ValueError:
    raise SystemExit("SIDECAR_OVERHEAD_MS must be numeric")
if not math.isfinite(delay_value) or delay_value != 0:
    raise SystemExit("Nginx test launcher requires SIDECAR_OVERHEAD_MS=0")
PY

command -v nginx >/dev/null 2>&1 || {
    echo "ERROR: nginx is not installed." >&2
    exit 1
}

UPSTREAM_PORT="${UPSTREAM_URL##*:}"
WORK_DIR="$(mktemp -d "/tmp/api-sentinel-nginx-${LISTEN_PORT}.XXXXXX")"
CONFIG="$WORK_DIR/nginx.conf"

# Keep all temporary request/proxy files writable by the current user.
mkdir -p "$WORK_DIR"/{client_body,proxy,fastcgi,uwsgi,scgi}

cat > "$CONFIG" <<NGINX
worker_processes 1;
pid $WORK_DIR/nginx.pid;
error_log stderr warn;

events {
    worker_connections 1024;
}

http {
    client_body_temp_path $WORK_DIR/client_body;
    proxy_temp_path       $WORK_DIR/proxy;
    fastcgi_temp_path     $WORK_DIR/fastcgi;
    uwsgi_temp_path       $WORK_DIR/uwsgi;
    scgi_temp_path        $WORK_DIR/scgi;

    access_log off;
    keepalive_timeout 30s;

    upstream api_upstream {
        server 127.0.0.1:$UPSTREAM_PORT;
        keepalive 32;
    }

    server {
        listen 127.0.0.1:$LISTEN_PORT;

        location = /health {
            default_type application/json;
            return 200 '{"service":"nginx-mock-sidecar","status":"ok","mock":true,"overhead_ms":0,"upstream":"$UPSTREAM_URL"}';
        }

        location / {
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host "127.0.0.1:$UPSTREAM_PORT";
            proxy_connect_timeout 2s;
            proxy_send_timeout 10s;
            proxy_read_timeout 10s;
            proxy_pass http://api_upstream;
        }
    }
}
NGINX

cleanup() {
    if [[ -n "${NGINX_PID:-}" ]]; then
        kill -TERM "$NGINX_PID" 2>/dev/null || true
        wait "$NGINX_PID" 2>/dev/null || true
    fi
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

nginx -t -c "$CONFIG" || exit 1
nginx -c "$CONFIG" -g 'daemon off;' &
NGINX_PID=$!
wait "$NGINX_PID"
