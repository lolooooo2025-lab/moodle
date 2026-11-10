#!/usr/bin/env bash
# Roll back the current symlink to a previous release and restart services.
# Usage: sudo bash deploy/rollback.sh [RELEASE_NAME]
set -euo pipefail
source "$(dirname "$0")/common.sh"

TARGET_ARG="${1:-}"
require_root
CURRENT="$(readlink -f "$TT_PREFIX/current" 2>/dev/null || true)"
[ -n "$CURRENT" ] && [ -d "$CURRENT" ] || die "no current release found."

if [ -n "$TARGET_ARG" ]; then
  if [ -d "$TT_PREFIX/releases/$TARGET_ARG" ]; then
    TARGET="$TT_PREFIX/releases/$TARGET_ARG"
  elif [ -d "$TARGET_ARG" ]; then
    TARGET="$(readlink -f "$TARGET_ARG")"
  else
    die "release not found: $TARGET_ARG"
  fi
else
  CURRENT_NAME="$(basename "$CURRENT")"
  PREVIOUS_NAME=""
  while IFS= read -r name; do
    [ "$name" != "$CURRENT_NAME" ] || break
    PREVIOUS_NAME="$name"
  done < <(find "$TT_PREFIX/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
  [ -n "$PREVIOUS_NAME" ] || die "no previous release found."
  TARGET="$TT_PREFIX/releases/$PREVIOUS_NAME"
fi

[ -x "$TARGET/.venv/bin/python" ] || die "target release has no virtualenv: $TARGET"
[ "$TARGET" != "$CURRENT" ] || die "target is already current."

log "rolling back: $CURRENT -> $TARGET"
switch_current "$TARGET"
restart_services
if ! wait_health; then
  journalctl -u taleb-talta.service -n 80 --no-pager || true
  die "rollback target did not become healthy."
fi
log "rollback completed: $TARGET"
