#!/usr/bin/env bash
# First production install on Ubuntu/Debian (systemd + nginx + PostgreSQL client).
# Usage:
#   sudo bash deploy/install.sh --secrets /root/taleb-talta.env [--domain example.com] [--tls-email admin@example.com]
# Add --trial only for an explicitly temporary/trial deployment.
set -euo pipefail
source "$(dirname "$0")/common.sh"

SECRETS_SRC=""
DOMAIN_OVERRIDE=""
TLS_EMAIL=""
TRIAL=0
REQUIRE_GEMINI=0
SKIP_APT=0
SKIP_NGINX=0

usage() {
  cat <<EOF
Usage: sudo bash deploy/install.sh --secrets PATH [options]

Options:
  --secrets PATH       Private env file to install as $TT_SECRETS_FILE (required on first install)
  --domain HOST        Override hostname (default: TT_PUBLIC_ORIGIN hostname from secrets)
  --tls-email EMAIL    Request Let's Encrypt certificate via certbot/nginx
  --trial              Explicitly allow trial-only owner password policy
  --require-gemini     Fail unless TT_GEMINI_API_KEY is present
  --skip-apt           Do not install OS packages
  --skip-nginx         Do not configure nginx
  -h, --help           Show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --secrets) SECRETS_SRC="${2:-}"; shift 2 ;;
    --domain) DOMAIN_OVERRIDE="${2:-}"; shift 2 ;;
    --tls-email) TLS_EMAIL="${2:-}"; shift 2 ;;
    --trial) TRIAL=1; shift ;;
    --require-gemini) REQUIRE_GEMINI=1; shift ;;
    --skip-apt) SKIP_APT=1; shift ;;
    --skip-nginx) SKIP_NGINX=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

require_root
require_source_layout

if [ "$SKIP_APT" != "1" ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y python3 python3-venv python3-pip postgresql-client nginx curl ca-certificates
  if [ -n "$TLS_EMAIL" ]; then
    apt-get install -y certbot python3-certbot-nginx
  fi
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PY
command -v pg_dump >/dev/null 2>&1 || die "pg_dump is missing (install postgresql-client)."

ensure_user_and_dirs
install_secrets_file "$SECRETS_SRC"

DOMAIN="$DOMAIN_OVERRIDE"
if [ -z "$DOMAIN" ]; then
  DOMAIN="$(origin_domain_from_file "$TT_SECRETS_FILE")"
fi
[ -n "$DOMAIN" ] || die "could not determine domain; pass --domain HOST."

RELEASE="$(new_release_dir)"
log "preparing release: $RELEASE"
copy_release "$RELEASE"
ensure_venv "$RELEASE"
config_check "$RELEASE" "$TRIAL" "$REQUIRE_GEMINI"
served_secrets_check "$RELEASE"
chown -R "$TT_USER:$TT_USER" "$RELEASE"
chmod -R u+rwX,g+rX,o-rwx "$RELEASE"

install_units "$RELEASE"
switch_current "$RELEASE"
systemctl enable --now taleb-talta.service taleb-talta-cron.service

if ! wait_health; then
  journalctl -u taleb-talta.service -n 80 --no-pager || true
  die "application did not become healthy on 127.0.0.1:$TT_PORT."
fi
live_schema_check "$RELEASE"

if [ "$SKIP_NGINX" != "1" ]; then
  configure_nginx "$RELEASE" "$DOMAIN"
  if [ -n "$TLS_EMAIL" ]; then
    command -v certbot >/dev/null 2>&1 || die "certbot is missing."
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$TLS_EMAIL" --redirect
  else
    log "WARNING: HTTPS is not configured yet. Run certbot before using the site: certbot --nginx -d $DOMAIN --redirect"
  fi
fi

log "install completed: https://$DOMAIN"
print_service_help
