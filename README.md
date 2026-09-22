# Bermúdez Profesional — Portal B2B

Aplicación B2B mobile-first para que instaladores busquen material, consulten precio y stock por delegación, creen pedidos y seleccionen una tienda de recogida.

## Incluye

- Next.js + TypeScript, diseño blanco y mobile-first.
- FastAPI con API versionada y Swagger.
- PostgreSQL 17.
- 15.000 referencias sintéticas realistas.
- 100 clientes profesionales de prueba.
- Stock en Almeiras, A Coruña, Sanxenxo, Ferrol y Santiago.
- Precio profesional calculado según el cliente.
- Carrito persistente y pedido rápido por varias líneas.
- Pedidos, snapshots históricos y repetición.
- Albaranes y facturas sintéticos.
- Panel de tienda con transiciones de estado.
- Aislamiento de datos entre clientes, auditoría y outbox para el futuro ERP.

## Inicio en macOS, Windows o Linux

1. Copia `.env.example` como `.env`.
2. Cambia `POSTGRES_PASSWORD` y `JWT_SECRET`.
3. Ejecuta:

```bash
docker compose up --build
```

El primer arranque genera los datos y puede tardar entre uno y varios minutos según el equipo.

Abre:

- Portal: http://localhost:3000
- Swagger: http://localhost:8000/docs

## Usuarios de demostración

| Tipo | Usuario | Contraseña |
|---|---|---|
| Cliente 1 | `compras001@cliente.test` | `123456` |
| Cliente 2 | `compras002@cliente.test` | `123456` |
| Operador | `operador@bermudez.test` | `123456` |
| Administrador | `admin@bermudez.test` | `123456` |

Los cien clientes usan el patrón `compras001@cliente.test` hasta `compras100@cliente.test`.

## Comandos útiles

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f web
docker compose exec db psql -U bermudez -d bermudez_b2b
```

Detener sin borrar datos:

```bash
docker compose down
```

Solo para reiniciar completamente los datos sintéticos:

```bash
docker compose down -v
docker compose up --build
```

## Pruebas backend sin Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=sqlite+pysqlite:///./test.db SEED_PRODUCTS=300 SEED_CUSTOMERS=5 pytest -q
```

## Integración ERP futura

La interfaz consume servicios de catálogo, precio y stock. PostgreSQL es la fuente del MVP. La tabla `integration_outbox` conserva los pedidos pendientes de sincronización y permite incorporar posteriormente adaptadores ERP sin modificar el frontend.

## Despliegue en un servidor Linux

Requisitos: Git, Docker Engine y el complemento Docker Compose.

```bash
git clone https://github.com/TdigitaTel/WEB_B2B.git
cd WEB_B2B
cp .env.production.example .env
```

Edita `.env` y sustituye `POSTGRES_PASSWORD` y `JWT_SECRET` por valores largos y aleatorios. Después inicia la aplicación:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

La web queda disponible en el puerto definido por `WEB_PORT`, inicialmente el puerto 80. PostgreSQL no se publica en Internet y la API sigue accesible únicamente desde el propio servidor y la red interna de Docker.

En la primera instalación, carga el catálogo clasificado del Excel en PostgreSQL:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m app.import_materials /app/data/materials_classified.csv
```

Esta operación crea y relaciona departamentos, familias, subfamilias y tipos de producto; conserva la descripción original y carga la descripción normalizada utilizada por el buscador. El importador es repetible: actualiza los materiales por código y conserva una copia auditable de cada fila del archivo.

Comprobaciones:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl http://127.0.0.1/
curl http://127.0.0.1:${API_PORT:-8001}/health
```

Comprueba la carga del catálogo:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec db \
  psql -U bermudez -d bermudez_b2b -c \
  "SELECT source_system, active, count(*) FROM products GROUP BY source_system, active ORDER BY source_system, active;"
```

Para actualizar una instalación existente:

```bash
git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Conexión de solo lectura al ERP SQL Server

La conexión al ERP es independiente de PostgreSQL. Configura estas variables únicamente en el `.env` privado del servidor:

```env
SQLSERVER_HOST=WSRV25BBDD
SQLSERVER_PORT=1433
SQLSERVER_DATABASE=EXITERP
SQLSERVER_USER=SBU
SQLSERVER_PASSWORD=CLAVE_REAL
```

Reconstruye la API y prueba la conexión:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build api
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.test_sqlserver
```

La prueba solo consulta el nombre del servidor y de la base de datos. Si `WSRV25BBDD` no se resuelve desde Linux, usa su dirección IP en `SQLSERVER_HOST`.

### Integración del catálogo con SQL Server

La API concentra el acceso al ERP en `backend/app/erp_db.py`. La estructura conocida de EXITERP se mantiene en `backend/app/erp_schema.py`; allí se registran las tablas y columnas de imágenes, artículos, stock y almacenes. Por este motivo, los nombres de tablas no se guardan en `.env`.

El `.env` privado contiene solamente las credenciales de conexión y parámetros de operación. Los almacenes que no participan en el stock comercial se configuran así:

```env
SQLSERVER_STOCK_EXCLUDED_WAREHOUSES=97,98
```

Para inspeccionar las imágenes disponibles:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.inspect_sqlserver_images
```

Cada tarjeta solicita `/api/v1/products/{id}/image`. La API relaciona el SKU del catálogo con `dbo.imagenes.CodigoArticulo` y devuelve el binario como JPEG, PNG, GIF, BMP o WebP. El stock se obtiene de `dbo.tempstockarticulo.UnidadSaldo`, los nombres de almacén de `dbo.almacenes` y los precios de `dbo.articulos`.

Para comprobar una referencia concreta:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.check_sqlserver_image 24664
```
