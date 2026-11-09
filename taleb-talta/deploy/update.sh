#!/usr/bin/env bash
# Update an existing installation with backup + additive migrations + health rollback.
# Usage: sudo bash deploy/update.sh [--secrets PATH] [--trial] [--require-gemini]
set -euo pipefail
source "$(dirname "$0")/common.sh"

SECRETS_SRC=""
TRIAL=0
REQUIRE_GEMINI=0
SKIP_BACKUP=0
DOMAIN_OVERRIDE=""
TLS_EMAIL=""

usage() {
  cat <<EOF
Usage: sudo bash deploy/update.sh [options]

Options:
  --secrets PATH       Replace the private env file before checking/updating
  --trial              Explicitly allow trial-only owner password policy
  --require-gemini     Fail unless TT_GEMINI_API_KEY is present
  --skip-backup        Skip the pre-update PostgreSQL dump (not recommended)
  --domain HOST        Reconfigure nginx for this domain after a successful update
  --tls-email EMAIL    Request/renew Let's Encrypt certificate when --domain is used
  -h, --help           Show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --secrets) SECRETS_SRC="${2:-}"; shift 2 ;;
    --trial) TRIAL=1; shift ;;
    --require-gemini) REQUIRE_GEMINI=1; shift ;;
    --skip-backup) SKIP_BACKUP=1; shift ;;
    --domain) DOMAIN_OVERRIDE="${2:-}"; shift 2 ;;
    --tls-email) TLS_EMAIL="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

require_root
require_source_layout
PREVIOUS="$(readlink -f "$TT_PREFIX/current" 2>/dev/null || true)"
[ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ] || die "no existing installation found; run deploy/install.sh first."

install_secrets_file "$SECRETS_SRC"

if [ "$SKIP_BACKUP" != "1" ]; then
  bash "$SOURCE_DIR/deploy/backup.sh"
fi

RELEASE="$(new_release_dir)"
log "preparing release: $RELEASE"
copy_release "$RELEASE"
ensure_venv "$RELEASE"
config_check "$RELEASE" "$TRIAL" "$REQUIRE_GEMINI"
served_secrets_check "$RELEASE"
run_migrations "$RELEASE"
chown -R "$TT_USER:$TT_USER" "$RELEASE"
chmod -R u+rwX,g+rX,o-rwx "$RELEASE"

install_units "$RELEASE"
switch_current "$RELEASE"
restart_services

if ! wait_health; then
  log "new release failed health check; rolling back to $PREVIOUS"
  switch_current "$PREVIOUS"
  restart_services
  wait_health || true
  journalctl -u taleb-talta.service -n 80 --no-pager || true
  die "update failed and was rolled back."
fi

if [ -n "$DOMAIN_OVERRIDE" ]; then
  configure_nginx "$RELEASE" "$DOMAIN_OVERRIDE"
  if [ -n "$TLS_EMAIL" ]; then
    command -v certbot >/dev/null 2>&1 || die "certbot is missing."
    certbot --nginx -d "$DOMAIN_OVERRIDE" --non-interactive --agree-tos -m "$TLS_EMAIL" --redirect
  fi
fi

log "update completed: $RELEASE"
print_service_help
