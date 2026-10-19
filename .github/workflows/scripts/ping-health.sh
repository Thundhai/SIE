#!/usr/bin/env bash
# Shared keep-alive ping logic for render-health-check.yml.
#
# Pings one liveness URL with a small, bounded retry policy (never
# indefinite), sensible connect/total timeouts, and follows redirects.
# Logs only the service name, URL, HTTP status, and elapsed time --
# never headers, credentials, or the response body (the body carries no
# secret, but this stays strict regardless of which URL is passed in
# here in the future).
#
# Usage: ping-health.sh "<service name>" "<url>"
set -euo pipefail

service_name="$1"
url="$2"

max_attempts=3
retry_delay_seconds=5
connect_timeout_seconds=5
max_total_seconds=15

attempt=1
while true; do
  # -s: no progress meter. -o /dev/null: discard the body (never logged).
  # -w: emit only status code and elapsed time, nothing else.
  # -L: follow redirects. --connect-timeout/--max-time: bounded, so a
  # hung connection can't block the job indefinitely.
  result=$(curl -s -o /dev/null -L \
    --connect-timeout "$connect_timeout_seconds" \
    --max-time "$max_total_seconds" \
    -w "%{http_code} %{time_total}" \
    "$url" || echo "000 0")

  status_code="${result%% *}"
  elapsed_seconds="${result##* }"

  if [ "$status_code" = "200" ]; then
    echo "[$service_name] OK status=$status_code elapsed=${elapsed_seconds}s attempt=$attempt/$max_attempts"
    exit 0
  fi

  echo "[$service_name] unhealthy status=$status_code elapsed=${elapsed_seconds}s attempt=$attempt/$max_attempts"

  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "[$service_name] FAILED after $max_attempts attempts"
    exit 1
  fi

  attempt=$((attempt + 1))
  sleep "$retry_delay_seconds"
done
