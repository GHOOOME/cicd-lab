#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib-static.sh
source "$script_dir/lib-static.sh"

[[ $# -eq 2 ]] || die "usage: verify-static.sh staging|production BUILD_ID"
validate_environment "$1"
validate_release_id "$2"
verify_live_release "$1" "$2"
