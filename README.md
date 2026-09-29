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

## Integración con EXITERP

EXITERP es la fuente de datos maestros de clientes, precios, stock e imágenes disponibles. PostgreSQL conserva el catálogo preparado para búsquedas, las contraseñas cifradas y la actividad propia del portal (carritos, pedidos, estados y auditoría). Los datos fiscales y comerciales del cliente no se copian a PostgreSQL.

## Despliegue en un servidor Linux

Requisitos: Git, Docker Engine y el complemento Docker Compose.

```bash
git clone https://github.com/TdigitaTel/WEB_B2B.git
cd WEB_B2B
cp .env.production.example .env
```

Edita `.env` y sustituye `POSTGRES_PASSWORD` y `JWT_SECRET` por valores largos y aleatorios. Después inicia la aplicación:

En producción mantén `SEED_CUSTOMERS=0`: las fichas de cliente proceden de EXITERP.

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

Cada tarjeta solicita `/api/v1/products/{id}/image`. La API relaciona el SKU del catálogo con `dbo.imagenes.CodigoArticulo` y devuelve el binario como JPEG, PNG, GIF, BMP o WebP. El stock se obtiene de `dbo.vis_ex_stockarticuloalmacen.UnidadSaldo`, los nombres de almacén de `dbo.almacenes` y los precios de `dbo.articulos.PrecioVentaConIVA0` y `PrecioVentaSinIVA0`.

### Clientes y contraseñas

La ficha completa de cada cliente se consulta directamente en `dbo.clientes`. PostgreSQL solo relaciona el usuario de acceso con el código de cliente EXITERP y guarda la contraseña cifrada. Para revisar la estructura disponible y dar acceso a un cliente:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.inspect_sqlserver_customers

docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.set_customer_password CODIGO_CLIENTE correo@empresa.es
```

El segundo comando solicita la contraseña de forma interactiva y valida primero que el código exista en EXITERP.

Para comprobar una referencia concreta:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.check_sqlserver_image 24664
```

### Imágenes binarias en PostgreSQL

`products.image_data` almacena la imagen binaria junto con su tipo MIME, URL de origen, proveedor y huella SHA-256. `PRODUCT_IMAGE_SOURCE` controla el origen usado por el catálogo:

- `auto`: PostgreSQL primero y SQL Server como respaldo.
- `postgres`: solamente PostgreSQL.
- `sqlserver`: solamente SQL Server.

Para copiar a PostgreSQL todas las imágenes que ya existen en EXITERP:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.sync_sqlserver_images_to_postgres
```

Las imágenes oficiales de proveedores se importan mediante un CSV con las columnas `sku,image_url,provider`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml cp imagenes.csv api:/tmp/imagenes.csv
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.import_provider_images /tmp/imagenes.csv
```

Para localizar imágenes en las webs oficiales de GEBO, IBIDE y GENEBRE se usa un proceso en dos pasos. Primero genera un CSV de revisión sin modificar la base de datos:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.scrape_official_brand_images \
  --brands GEBO IBIDE GENEBRE \
  --output /tmp/official_brand_image_candidates.csv

docker compose -f docker-compose.yml -f docker-compose.prod.yml cp \
  api:/tmp/official_brand_image_candidates.csv ./official_brand_image_candidates.csv
```

El archivo conserva la referencia, la ficha oficial, la URL de la imagen, la puntuación y el motivo de la coincidencia. Después de revisarlo, la misma búsqueda puede guardar en PostgreSQL solo las coincidencias de alta confianza:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.scrape_official_brand_images \
  --brands GEBO IBIDE GENEBRE \
  --output /tmp/official_brand_image_results.csv \
  --apply
```

La herramienta respeta `robots.txt`, limita la frecuencia de peticiones, restringe la navegación a los dominios configurados y no reemplaza imágenes existentes. Cada binario queda acompañado por URL de origen, proveedor y huella SHA-256. `--overwrite` permite sustituir imágenes existentes únicamente cuando se indica junto con `--apply`.

Consulta la cobertura obtenida con `python -m scripts.check_postgres_images`.

### Bandeja operativa unificada WEB + EXIT

La pantalla de comandas lee una proyección común en PostgreSQL. Cada pedido conserva:

- `source_system`: sistema donde nació (`WEB` o `EXIT`).
- `authority_system`: sistema que controla su estado actual. Un pedido web cambia a `EXIT` cuando recibe `exit_order_id`.
- `exit_order_id` y `exit_status`: identidad y estado originales de EXIT.
- `source_updated_at` y `last_imported_at`: control de versiones e importación.

`backend/app/exit_orders.py` define el contrato `ExitOrderInput` y las funciones idempotentes `upsert_exit_order` e `import_exit_batch`. El futuro demonio debe leer cabecera y líneas desde la tabla de EXIT, convertir los estados y almacenes al contrato y llamar `import_exit_batch`. El cursor se guarda en `integration_cursors` dentro de la misma transacción que los pedidos.

Cuando se confirme la tabla de EXIT habrá que mapear estos datos: identificador del pedido, número web cuando exista, cliente, almacén, estado, fecha de última modificación, totales y líneas (`artículo`, `descripción`, `cantidad`, `unidad`, `precio`, `descuento`, `IVA` y `total`).

Para comprobar el cursor de la integración:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.show_exit_order_cursor
```

Los cambios de estado realizados por operación generan eventos `ORDER_STATUS_CHANGED` en `integration_outbox`, listos para que el proceso de salida los escriba en EXIT cuando se defina su tabla de destino.

### Pedidos pendientes de EXIT para Operaciones

El lector usa `dbo.PedidoVentaCabecera` y `dbo.PedidoVentaLineas`. Solo proyecta cabeceras que cumplan `IdDelegacion = '00'`, `StatusPedido = 'S'` y `PorcentajePendiente <> 100`. En cada comanda separa las líneas mediante `ex_tipopedvlinkardex`: `KARDEX` aparece como preparación de Kardex y `SGA` como preparación de estantes/SGA.

Antes de importar, inspecciona diez pedidos sin modificar PostgreSQL:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.inspect_exit_pending_orders
```

Si el mapeo es correcto, sincroniza hasta mil pedidos pendientes:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m scripts.sync_exit_pending_orders
```

Ambos procesos resuelven los nombres reales de las columnas mediante `INFORMATION_SCHEMA`. La delegación `00` se asigna a la tienda interna `ALM` (Almeiras); esta consulta no utiliza un campo de almacén.

### Sincronización en línea de pedidos EXIT

El servicio `exit-order-sync` consulta EXIT cada 10 segundos y actualiza la proyección operativa en PostgreSQL. Usa un bloqueo asesor de PostgreSQL para impedir ciclos simultáneos, registra el último error y Docker lo reinicia automáticamente. La frecuencia puede cambiarse en `.env` con `EXIT_ORDER_SYNC_INTERVAL_SECONDS`; el mínimo admitido es 5 segundos.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build exit-order-sync
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=100 exit-order-sync
```

No hace falta configurar `crontab`.
