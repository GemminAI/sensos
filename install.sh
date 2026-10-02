#!/usr/bin/env bash
# SensOS installer entry point (repository root).
#
# This is a thin wrapper: it runs `sensos/install.sh` unchanged, passing every
# argument through, so that `git clone <repo> && cd <repo> && ./install.sh`
# works from the repository root. All installation logic lives in
# `sensos/install.sh`; nothing is duplicated here.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT_DIR/sensos/install.sh" "$@"
