#!/usr/bin/env bash
set -Eeuo pipefail

target="${1:-}"
release="${2:-$(git rev-parse HEAD)}"

case "$target" in
  dev)
    default_project="webb2b-dev"
    override="docker-compose.dev.yml"
    ;;
  prod)
    default_project="webb2b-prod"
    override="docker-compose.prod.yml"
    ;;
  *)
    echo "Uso: $0 dev|prod [version]" >&2
    exit 2
    ;;
esac

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="${WEBB2B_CONFIG_DIR:-/opt/webb2b/config}"
state_dir="${WEBB2B_STATE_DIR:-/opt/webb2b/releases}"
backup_dir="${WEBB2B_BACKUP_DIR:-/opt/webb2b/backups}"
env_file="$config_dir/$target.env"
state_file="$state_dir/$target.current"

if [[ ! -f "$env_file" ]]; then
  echo "Falta el archivo privado $env_file" >&2
  exit 3
fi

mkdir -p "$state_dir"

env_value() {
  local key="$1" fallback="$2" value
  value="$(awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$env_file" | tr -d '\r')"
  printf '%s' "${value:-$fallback}"
}

API_PORT="$(env_value API_PORT 8000)"
WEB_PORT="$(env_value WEB_PORT 3000)"
project="$(env_value COMPOSE_PROJECT_NAME "$default_project")"

export IMAGE_TAG="${release//[^a-zA-Z0-9_.-]/-}"
compose=(docker compose --project-name "$project" --env-file "$env_file" -f "$root_dir/docker-compose.yml" -f "$root_dir/$override")
previous="$(cat "$state_file" 2>/dev/null || true)"

"${compose[@]}" config --quiet

if "${compose[@]}" ps --status running --services | grep -qx db; then
  mkdir -p "$backup_dir"
  backup_file="$backup_dir/postgres-$target-$(date +%Y%m%d-%H%M%S).sql.gz"
  "${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > "$backup_file"
  echo "Copia PostgreSQL: $backup_file"
fi

rollback() {
  echo "El despliegue $target no superó la comprobación de salud." >&2
  if [[ -n "$previous" ]]; then
    echo "Restaurando versión $previous..." >&2
    IMAGE_TAG="$previous" "${compose[@]}" up -d --no-build --remove-orphans
  fi
}
trap rollback ERR

"${compose[@]}" build
"${compose[@]}" up -d --remove-orphans

for _ in $(seq 1 36); do
  if curl --fail --silent "http://127.0.0.1:${API_PORT}/health" >/dev/null \
    && curl --fail --silent "http://127.0.0.1:${WEB_PORT}/" >/dev/null; then
    "${compose[@]}" exec -T api python -m app.reclassify_materials
    printf '%s' "$IMAGE_TAG" > "$state_file"
    trap - ERR
    echo "Despliegue $target completado: $IMAGE_TAG"
    exit 0
  fi
  sleep 5
done

false
