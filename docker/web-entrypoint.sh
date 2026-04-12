#!/bin/sh

set -eu

API_BASE_URL="${SIGNALARK_WEB_API_BASE_URL:-http://localhost:8000}"
API_BASE_URL="${API_BASE_URL%/}"

printf 'window.__SIGNALARK_RUNTIME_CONFIG__ = { apiBaseUrl: "%s" };\n' "$API_BASE_URL" \
  > /usr/share/nginx/html/runtime-config.js
