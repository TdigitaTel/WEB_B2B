#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="${WEBB2B_CONFIG_DIR:-/opt/webb2b/config}"
dev_env="$config_dir/dev.env"
production_env="${1:-/opt/proyectos/WEB_B2B/.env}"

for command_name in docker openssl curl awk; do
  command -v "$command_name" >/dev/null || { echo "Falta el comando $command_name" >&2; exit 2; }
done

mkdir -p "$config_dir" "${WEBB2B_STATE_DIR:-/opt/webb2b/releases}" "${WEBB2B_BACKUP_DIR:-/opt/webb2b/backups}"

env_value() {
  local file="$1" key="$2"
  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$file" | tr -d '\r'
}

if [[ ! -f "$dev_env" ]]; then
  if [[ ! -f "$production_env" ]]; then
    echo "No existe $production_env; no se puede copiar la conexión de solo lectura a EXIT." >&2
    exit 3
  fi
  sql_host="$(env_value "$production_env" SQLSERVER_HOST)"
  sql_port="$(env_value "$production_env" SQLSERVER_PORT)"
  sql_database="$(env_value "$production_env" SQLSERVER_DATABASE)"
  sql_user="$(env_value "$production_env" SQLSERVER_USER)"
  sql_password="$(env_value "$production_env" SQLSERVER_PASSWORD)"
  excluded_warehouses="$(env_value "$production_env" SQLSERVER_STOCK_EXCLUDED_WAREHOUSES)"
  if [[ -z "$sql_host" || -z "$sql_database" || -z "$sql_user" || -z "$sql_password" ]]; then
    echo "La conexión SQLSERVER_* de $production_env está incompleta." >&2
    exit 4
  fi
  umask 077
  cat > "$dev_env" <<EOF
COMPOSE_PROJECT_NAME=webb2b-dev
POSTGRES_DB=bermudez_b2b_dev
POSTGRES_USER=bermudez_dev
POSTGRES_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 64)
INTEGRATION_API_KEY=$(openssl rand -hex 32)
SHOW_ORDER_STATUS_HISTORY=true
CUSTOMER_SYNC_INTERVAL_SECONDS=30
CUSTOMER_SYNC_BATCH_SIZE=30
SEED_PRODUCTS=0
SEED_CUSTOMERS=0
API_BIND=127.0.0.1
API_PORT=8002
WEB_BIND=0.0.0.0
WEB_PORT=8081
SQLSERVER_HOST=$sql_host
SQLSERVER_PORT=${sql_port:-1433}
SQLSERVER_DATABASE=$sql_database
SQLSERVER_USER=$sql_user
SQLSERVER_PASSWORD=$sql_password
SQLSERVER_STOCK_EXCLUDED_WAREHOUSES=${excluded_warehouses:-97,98}
PRODUCT_IMAGE_SOURCE=auto
EOF
  chmod 600 "$dev_env"
  echo "Configuración privada creada en $dev_env"
else
  echo "Se conserva la configuración existente $dev_env"
fi

"$root_dir/ops/deploy.sh" dev "$(git -C "$root_dir" rev-parse HEAD)"

compose=(docker compose --project-name webb2b-dev --env-file "$dev_env" -f "$root_dir/docker-compose.yml" -f "$root_dir/docker-compose.dev.yml")

echo "Cargando catálogo de desarrollo..."
"${compose[@]}" exec -T api python -m app.import_materials /app/data/materials_classified.csv

integration_key="$(env_value "$dev_env" INTEGRATION_API_KEY)"
echo "Creando acceso de prueba para el cliente EXIT 00004..."
if ! curl --fail --silent --show-error -X PUT http://127.0.0.1:8002/api/v1/integrations/customer-access \
  -H 'Content-Type: application/json' \
  -H "X-Integration-Key: $integration_key" \
  -d '{"customer_code":"00004","new_password":"123456"}' >/dev/null; then
  echo "La aplicación funciona, pero no se pudo crear el usuario 00004. Revisa la conexión EXIT." >&2
fi

echo
echo "DESARROLLO PREPARADO"
echo "Web: http://$(hostname -I | awk '{print $1}'):8081"
echo "API: http://127.0.0.1:8002/health"
echo "Usuario de prueba: pumaresdavid@gmail.com"
echo "Contraseña de prueba: 123456"
echo
"${compose[@]}" ps
