#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib-static.sh
source "$script_dir/lib-static.sh"

usage() {
  printf 'Usage: %s staging|production BUILD_ID\n' "$(basename "$0")" >&2
  exit 2
}

[[ $# -eq 2 ]] || usage
environment="$1"
release_id="$2"
validate_environment "$environment"
validate_release_id "$release_id"
acquire_deploy_lock

release_dir="$CICD_WEB_ROOT/releases/$release_id"
[[ -d "$release_dir" ]] || die "release does not exist: $release_id"
validate_release_metadata "$release_dir" "$release_id"
switch_and_verify "$environment" "$release_dir" "$release_id"
printf 'Rolled back %s to %s\n' "$environment" "$release_id"
