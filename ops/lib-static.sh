#!/usr/bin/env bash
set -euo pipefail

CICD_WEB_ROOT="${CICD_WEB_ROOT:-/opt/cicd-web}"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

validate_environment() {
  case "${1:-}" in
    staging|production) ;;
    *) die "environment must be staging or production" ;;
  esac
}

validate_release_id() {
  [[ "${1:-}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || \
    die "release id contains unsupported characters"
}

validate_release_metadata() {
  local release_dir="$1"
  local release_id="$2"
  [[ -f "$release_dir/index.html" ]] || die "dist must contain index.html"
  [[ -f "$release_dir/release.json" ]] || die "dist must contain release.json"

  python3 - "$release_dir/release.json" "$release_id" <<'PY'
import json
import re
import sys

path, expected_id = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid release.json: {exc}")

if not isinstance(data, dict):
    raise SystemExit("release.json must contain a JSON object")
required = ("version", "commit", "builtAt", "buildId")
missing = [key for key in required if not data.get(key)]
if missing:
    raise SystemExit("release.json is missing: " + ", ".join(missing))
if data["buildId"] != expected_id:
    raise SystemExit(
        f"release.json buildId {data['buildId']!r} does not match release id {expected_id!r}"
    )
commit = str(data["commit"])
if commit not in {"dev", "local"} and not re.fullmatch(r"[0-9a-fA-F]{40}(?:-dirty)?", commit):
    raise SystemExit("release.json commit must be 'dev', 'local', a 40-character SHA, or a SHA-dirty value")
PY
}

atomic_switch() {
  local environment="$1"
  local release_dir="$2"
  local env_dir="$CICD_WEB_ROOT/environments/$environment"
  local current_tmp="$env_dir/.current.$$"

  mkdir -p "$env_dir"
  DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)" ENVIRONMENT="$environment" \
    python3 - "$env_dir/.environment.$$.json" <<'PY'
import json
import os
import sys

with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump(
        {"environment": os.environ["ENVIRONMENT"], "deployedAt": os.environ["DEPLOYED_AT"]},
        stream,
        separators=(",", ":"),
    )
    stream.write("\n")
PY
  atomic_replace "$env_dir/.environment.$$.json" "$env_dir/environment.json"
  ln -s "$release_dir" "$current_tmp"
  atomic_replace "$current_tmp" "$env_dir/current"
}

atomic_replace() {
  python3 - "$1" "$2" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
}

acquire_deploy_lock() {
  mkdir -p "$CICD_WEB_ROOT"
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$CICD_WEB_ROOT/.deploy.lock"
    flock -x 9
    return
  fi

  # macOS does not ship flock; mkdir gives the same single-writer behavior.
  DEPLOY_LOCK_DIR="$CICD_WEB_ROOT/.deploy.lock.d"
  while ! mkdir "$DEPLOY_LOCK_DIR" 2>/dev/null; do
    sleep 1
  done
  trap 'rmdir "$DEPLOY_LOCK_DIR" 2>/dev/null || true' EXIT
}

verify_live_release() {
  local environment="$1"
  local release_id="$2"
  local port=18082
  [[ "$environment" == staging ]] || port=18083

  python3 - "$port" "$environment" "$CICD_WEB_ROOT/releases/$release_id/release.json" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

port, environment, metadata_path = sys.argv[1:]
base_url = f"http://127.0.0.1:{port}"
with open(metadata_path, encoding="utf-8") as stream:
    expected = json.load(stream)

def fetch(path):
    request = urllib.request.Request(base_url + path, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.read()

for attempt in range(10):
    try:
        runtime = json.loads(fetch("/environment.json"))
        if runtime.get("environment") != environment or not runtime.get("deployedAt"):
            raise ValueError("environment.json identifies the wrong environment or has no deployment time")
        for path in ("/release.json", "/health"):
            if json.loads(fetch(path)) != expected:
                raise ValueError(f"{path} does not match the expected release")
        if b"<html" not in fetch("/").lower():
            raise ValueError("the home page is not HTML")
        print(f"Verified {environment}: {expected['version']} ({expected['buildId']})")
        break
    except (OSError, urllib.error.URLError, ValueError) as exc:
        if attempt == 9:
            raise SystemExit(f"verification failed: {exc}")
        time.sleep(1)
PY
}

switch_and_verify() {
  local environment="$1"
  local release_dir="$2"
  local release_id="$3"
  local env_dir="$CICD_WEB_ROOT/environments/$environment"
  local previous=""
  [[ ! -L "$env_dir/current" ]] || previous=$(readlink "$env_dir/current")
  atomic_switch "$environment" "$release_dir"

  # Initial installation has no container yet; verify after run-nginx.sh starts it.
  if command -v docker >/dev/null 2>&1 && \
    [[ "$(docker inspect --format '{{.State.Running}}' "cicd-web-$environment" 2>/dev/null || true)" == true ]]; then
    if ! verify_live_release "$environment" "$release_id"; then
      if [[ -n "$previous" ]]; then
        atomic_switch "$environment" "$previous"
        printf 'Restored previous release: %s\n' "$previous" >&2
      else
        rm "$env_dir/current"
      fi
      die "release failed verification"
    fi
  else
    printf 'Container is not running yet; start it, then run verify-static.sh %s %s\n' "$environment" "$release_id"
  fi
}
