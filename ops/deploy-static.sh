#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib-static.sh
source "$script_dir/lib-static.sh"

usage() {
  printf 'Usage: %s DIST_DIR BUILD_ID staging|production\n' "$(basename "$0")" >&2
  exit 2
}

[[ $# -eq 3 ]] || usage
source_dir=$(CDPATH= cd -- "$1" && pwd) || die "dist directory does not exist: $1"
release_id="$2"
environment="$3"
validate_release_id "$release_id"
validate_environment "$environment"

acquire_deploy_lock
releases_dir="$CICD_WEB_ROOT/releases"
env_dir="$CICD_WEB_ROOT/environments/$environment"
release_dir="$releases_dir/$release_id"
mkdir -p "$releases_dir" "$env_dir"
validate_release_metadata "$source_dir" "$release_id"
[[ -z "$(find "$source_dir" -type l -print -quit)" ]] || die "dist must not contain symlinks"

if [[ -e "$release_dir" ]]; then
  [[ -d "$release_dir" ]] || die "release path exists and is not a directory: $release_id"
  diff -qr "$source_dir" "$release_dir" >/dev/null ||
    die "release $release_id already exists with different contents"
else
  temporary_release="$releases_dir/.incoming-$release_id.$$"
  rm -rf "$temporary_release"
  mkdir "$temporary_release"
  cp -a "$source_dir/." "$temporary_release/"
  validate_release_metadata "$temporary_release" "$release_id"
  mv "$temporary_release" "$release_dir"
fi

switch_and_verify "$environment" "$release_dir" "$release_id"
printf 'Deployed %s to %s\n' "$release_id" "$environment"
