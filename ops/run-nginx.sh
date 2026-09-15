#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
environment="${1:-}"
[[ $# -ge 1 && $# -le 2 ]] || {
  printf 'Usage: %s staging|production [nginx-image]\n' "$(basename "$0")" >&2
  exit 2
}
validate_environment() {
  case "$1" in staging|production) ;; *) printf 'Usage: %s staging|production [nginx-image]\n' "$(basename "$0")" >&2; exit 2 ;; esac
}
validate_environment "$environment"

image="${2:-${NGINX_IMAGE:-}}"
[[ "$image" == *@sha256:* ]] || {
  printf 'Set NGINX_IMAGE to a digest-pinned image, for example nginx:alpine@sha256:<digest>\n' >&2
  exit 1
}
[[ -f "/opt/cicd-web/environments/$environment/current/index.html" ]] || {
  printf 'Deploy a release to %s before starting nginx.\n' "$environment" >&2
  exit 1
}

case "$environment" in
  staging) port=18082; container=cicd-web-staging; config=nginx-staging.conf ;;
  production) port=18083; container=cicd-web-production; config=nginx-production.conf ;;
esac

docker rm -f "$container" >/dev/null 2>&1 || true
exec docker run --detach \
  --name "$container" \
  --restart unless-stopped \
  --memory 32m \
  --cpus 0.10 \
  --pids-limit 32 \
  --security-opt no-new-privileges:true \
  --log-opt max-size=1m \
  --log-opt max-file=2 \
  --read-only \
  --tmpfs /var/cache/nginx:size=8m \
  --tmpfs /var/run:size=1m \
  --publish "127.0.0.1:${port}:80" \
  --volume "/opt/cicd-web:/opt/cicd-web:ro" \
  --volume "$script_dir/$config:/etc/nginx/nginx.conf:ro" \
  "$image" nginx -g 'daemon off;'
