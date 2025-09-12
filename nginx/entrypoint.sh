#!/usr/bin/env sh
set -e

: "${UPSTREAM_HOST:?Need UPSTREAM_HOST}"
: "${UPSTREAM_PORT:=8000}"
: "${DEVICE_TOKEN:=disabled}"

# Render template
envsubst '${UPSTREAM_HOST} ${UPSTREAM_PORT} ${DEVICE_TOKEN}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/nginx.conf

exec nginx -g 'daemon off;'
