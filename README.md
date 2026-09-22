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

Comprobaciones:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl http://127.0.0.1/
curl http://127.0.0.1:8000/health
```

Para actualizar una instalación existente:

```bash
git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
