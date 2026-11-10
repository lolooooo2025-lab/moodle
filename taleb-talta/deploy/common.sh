#!/usr/bin/env bash
# Shared helpers for Taleb Talta deployment scripts.
# This file is sourced by install.sh / update.sh / rollback.sh / backup.sh.

TT_PREFIX="${TT_PREFIX:-/opt/taleb-talta}"
TT_ETC="${TT_ETC:-/etc/taleb-talta}"
TT_STATE="${TT_STATE:-/var/lib/taleb-talta}"
TT_BACKUP_DIR="${TT_BACKUP_DIR:-/var/backups/taleb-talta}"
TT_USER="${TT_USER:-taleb}"
TT_PORT="${TT_PORT:-8000}"
TT_SECRETS_FILE="${TT_SECRETS_FILE:-$TT_ETC/secrets.env}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

log() { printf '[taleb-talta] %s\n' "$*"; }
die() { printf '[taleb-talta] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "run this script as root (sudo)."
}

require_source_layout() {
  [ -d "$SOURCE_DIR/app" ] || die "app/ not found next to deploy/."
  [ -d "$SOURCE_DIR/database" ] || die "database/ not found next to deploy/."
  [ -d "$SOURCE_DIR/tools" ] || die "tools/ not found next to deploy/."
  [ -f "$SOURCE_DIR/requirements.lock.txt" ] || die "requirements.lock.txt is missing."
  [ -f "$SOURCE_DIR/config/secrets.env.example" ] || die "config/secrets.env.example is missing."
}

validate_domain() {
  local domain="$1"
  [ -n "$domain" ] || die "empty domain."
  case "$domain" in
    *[!A-Za-z0-9.-]*|.*|*.) die "invalid domain: $domain" ;;
  esac
}

ensure_user_and_dirs() {
  if ! id "$TT_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$TT_PREFIX" --shell /usr/sbin/nologin "$TT_USER"
  fi
  mkdir -p "$TT_PREFIX/releases" "$TT_STATE/storage" "$TT_BACKUP_DIR" "$TT_ETC"
  chown "$TT_USER:$TT_USER" "$TT_STATE" "$TT_STATE/storage" "$TT_BACKUP_DIR" "$TT_ETC"
  chmod 750 "$TT_STATE" "$TT_STATE/storage" "$TT_BACKUP_DIR"
  chmod 700 "$TT_ETC"
}

install_secrets_file() {
  local src="$1"
  if [ -n "$src" ]; then
    [ -f "$src" ] || die "secrets source file does not exist: $src"
    if [ ! -f "$TT_SECRETS_FILE" ] || ! cmp -s "$src" "$TT_SECRETS_FILE"; then
      install -m 600 -o "$TT_USER" -g "$TT_USER" "$src" "$TT_SECRETS_FILE"
    fi
  fi
  [ -f "$TT_SECRETS_FILE" ] || die "missing secrets file: $TT_SECRETS_FILE (pass --secrets PATH)."
  chown "$TT_USER:$TT_USER" "$TT_SECRETS_FILE"
  chmod 600 "$TT_SECRETS_FILE"
}

origin_domain_from_file() {
  local file="$1" origin domain
  origin="$(grep -E '^TT_PUBLIC_ORIGIN=' "$file" | tail -n 1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs || true)"
  domain="${origin#*://}"
  domain="${domain%%/*}"
  printf '%s' "$domain"
}

new_release_dir() {
  printf '%s/releases/%s' "$TT_PREFIX" "$(date -u +%Y%m%d%H%M%S)"
}

copy_release() {
  local release="$1"
  mkdir -p "$release/config"
  cp -a "$SOURCE_DIR/app" "$release/"
  cp -a "$SOURCE_DIR/database" "$release/"
  cp -a "$SOURCE_DIR/tools" "$release/"
  cp -a "$SOURCE_DIR/deploy" "$release/"
  cp -a "$SOURCE_DIR/config/secrets.env.example" "$release/config/"
  cp -a "$SOURCE_DIR/requirements.txt" "$release/"
  cp -a "$SOURCE_DIR/requirements.lock.txt" "$release/"
  cp -a "$SOURCE_DIR/.gitignore" "$release/"
  [ ! -f "$SOURCE_DIR/UPLOAD.md" ] || cp -a "$SOURCE_DIR/UPLOAD.md" "$release/"
  [ ! -f "$SOURCE_DIR/DELIVERY.md" ] || cp -a "$SOURCE_DIR/DELIVERY.md" "$release/"
  find "$release" -type d -name '__pycache__' -prune -exec rm -rf {} +
  find "$release" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
  ln -sfn "$TT_STATE/storage" "$release/storage"
}

ensure_venv() {
  local release="$1"
  python3 -m venv "$release/.venv"
  "$release/.venv/bin/python" -m pip install --upgrade pip
  "$release/.venv/bin/python" -m pip install -r "$release/requirements.lock.txt"
}

release_python() {
  local release="$1"
  printf '%s/.venv/bin/python' "$release"
}

config_check() {
  local release="$1" trial="$2" require_gemini="$3"
  local args=()
  [ "$trial" != "1" ] || args+=(--trial)
  [ "$require_gemini" != "1" ] || args+=(--require-gemini)
  (cd "$release" && TT_SECRETS_FILE="$TT_SECRETS_FILE" "$(release_python "$release")" tools/check_production_config.py "${args[@]}")
}

served_secrets_check() {
  local release="$1"
  (cd "$release" && TT_SECRETS_FILE="$TT_SECRETS_FILE" "$(release_python "$release")" tools/check_served_secrets.py)
}

live_schema_check() {
  local release="$1"
  (cd "$release" && TT_SECRETS_FILE="$TT_SECRETS_FILE" "$(release_python "$release")" tools/check_live_schema.py)
}

run_migrations() {
  local release="$1" py
  py="$(release_python "$release")"
  (cd "$release" && TT_SECRETS_FILE="$TT_SECRETS_FILE" "$py" tools/migrate_wave4.py)
  (cd "$release" && TT_SECRETS_FILE="$TT_SECRETS_FILE" "$py" tools/migrate_wave5.py)
  (cd "$release" && TT_SECRETS_FILE="$TT_SECRETS_FILE" "$py" tools/migrate_wave3.py)
  live_schema_check "$release"
}

render_template() {
  local src="$1" dest="$2"
  sed -e "s|__USER__|$TT_USER|g" \
      -e "s|__PREFIX__|$TT_PREFIX|g" \
      -e "s|__ETC__|$TT_ETC|g" \
      -e "s|__STATE__|$TT_STATE|g" \
      -e "s|__PORT__|$TT_PORT|g" \
      "$src" > "$dest"
}

install_units() {
  local release="$1" tmp
  tmp="$(mktemp)"
  render_template "$release/deploy/systemd/taleb-talta.service.template" "$tmp"
  install -m 644 "$tmp" /etc/systemd/system/taleb-talta.service
  render_template "$release/deploy/systemd/taleb-talta-cron.service.template" "$tmp"
  install -m 644 "$tmp" /etc/systemd/system/taleb-talta-cron.service
  rm -f "$tmp"
  systemctl daemon-reload
}

configure_nginx() {
  local release="$1" domain="$2" tmp
  validate_domain "$domain"
  [ -f "$release/deploy/nginx/taleb-talta.conf.template" ] || die "nginx template is missing."
  tmp="$(mktemp)"
  sed -e "s/__DOMAIN__/$domain/g" -e "s/__PORT__/$TT_PORT/g" \
      "$release/deploy/nginx/taleb-talta.conf.template" > "$tmp"
  install -m 644 "$tmp" /etc/nginx/sites-available/taleb-talta.conf
  rm -f "$tmp"
  ln -sfn /etc/nginx/sites-available/taleb-talta.conf /etc/nginx/sites-enabled/taleb-talta.conf
  nginx -t
  systemctl reload nginx
}

switch_current() {
  local release="$1"
  ln -sfn "$release" "$TT_PREFIX/current"
}

restart_services() {
  systemctl restart taleb-talta.service
  systemctl restart taleb-talta-cron.service
}

wait_health() {
  local i
  for i in $(seq 1 45); do
    if curl -fsS "http://127.0.0.1:$TT_PORT/healthz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

print_service_help() {
  cat <<EOF
Services:
  systemctl status taleb-talta.service
  systemctl status taleb-talta-cron.service
  journalctl -u taleb-talta.service -f
  journalctl -u taleb-talta-cron.service -f

Paths:
  current release : $TT_PREFIX/current
  secrets         : $TT_SECRETS_FILE
  uploads/storage : $TT_STATE/storage
  backups         : $TT_BACKUP_DIR
EOF
}
