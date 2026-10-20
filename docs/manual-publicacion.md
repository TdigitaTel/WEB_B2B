# Quiero publicar una mejora de WEB B2B

Manual de trabajo · 13 de octubre de 2026

Este documento explica cómo modificar la aplicación, probarla y publicarla. Los comandos indican dónde ejecutarlos. Los valores como `RUTA_DEL_REPOSITORIO` y `SHA_VALIDADO` deben sustituirse por los valores reales. No ejecutes comandos que aún tengan esos nombres de ejemplo.

## 1. ¿Cómo pasa una mejora a producción?

**Mejora → rama de trabajo → PR hacia develop → pruebas → desarrollo → validación funcional → PR de develop hacia main → producción → comprobación.**

| Rama | Para qué sirve | Qué sucede al actualizarla |
|---|---|---|
| `codex/nombre-de-la-mejora` | Preparar y revisar cambios | No despliega mediante el workflow de despliegue |
| `develop` | Validar cambios en desarrollo | GitHub Actions ejecuta el despliegue de desarrollo |
| `main` | Versión de producción | GitHub Actions ejecuta el despliegue de producción |

Crear un PR no despliega. Fusionarlo en `develop` o `main` sí provoca un despliegue. La aprobación de producción depende de cómo esté configurado el entorno `production` en GitHub; este manual no presupone que esté activada.

## 2. Quiero definir la mejora

Anota antes de programar:

- Qué hace hoy y qué debe hacer después.
- Qué pantalla, API o tabla interviene.
- Un caso concreto con el que comprobar el resultado.
- Si necesita cambiar el esquema PostgreSQL o sus datos.

Ejemplo: «En Pedidos WEB el operador debe consultar todas las delegaciones. El filtro abrirá en Almeiras y tendrá una opción Todas».

## 3. Quiero empezar una rama de trabajo

En la terminal del **Mac**, entra en tu checkout del repositorio:

```bash
cd "RUTA_DEL_REPOSITORIO"
git status --short
git fetch origin
git switch develop
git pull --ff-only origin develop
git switch -c codex/mi-mejora
```

Antes de cambiar de rama, `git status --short` debe estar vacío o debes haber guardado conscientemente tus cambios. Si aparece trabajo pendiente, no uses `git reset --hard` para quitarlo: guarda ese trabajo o usa otro checkout limpio. El repositorio principal puede contener cambios de otras tareas.

## 4. Quiero modificar el código

| Parte | Archivos habituales |
|---|---|
| Pantallas y acciones | `frontend/app/page.tsx` |
| Estilos | Archivos CSS de `frontend/app/` |
| Rutas de API y consultas locales | `backend/app/main.py` |
| Modelos PostgreSQL | `backend/app/models.py` |
| Preparación y cambios de esquema | `backend/app/bootstrap.py` |
| Consultas de EXIT | `backend/app/erp_db.py`, `backend/app/exit_db.py` |
| Despliegue | `ops/deploy.sh`, `.github/workflows/deploy.yml` |

Ejemplo de un filtro correcto de fechas en SQLAlchemy:

```python
# date_from y date_to son objetos datetime.date.
query = select(Order).where(Order.origen_pedido == "B2B")
if date_from:
    query = query.where(func.date(Order.created_at) >= date_from)
if date_to:
    query = query.where(func.date(Order.created_at) <= date_to)
```

En PostgreSQL no conviertas esos parámetros a texto con `.isoformat()` al compararlos con una columna de tipo fecha. Esto provocó el error `date >= character varying` en Pedidos WEB.

## 5. Quiero comprobar mi cambio

Necesitas Python 3.12, Node.js 22, Git y Docker Compose para reproducir las comprobaciones de GitHub. Ejecuta cada bloque desde la raíz del repositorio.

### Backend

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd backend
../.venv/bin/python -m pytest -q
cd ..
```

Las pruebas actuales preparan una base SQLite temporal. Que pasen no garantiza compatibilidad PostgreSQL: si cambias SQL, tipos de fecha, índices o migraciones, compruébalos además en PostgreSQL de desarrollo.

### Frontend

```bash
cd frontend
npm ci
npm run build
cd ..
```

### Configuración Docker

```bash
docker compose --project-name webb2b-dev --env-file .env.development.example -f docker-compose.yml -f docker-compose.dev.yml config --quiet
docker compose --project-name webb2b-prod --env-file .env.production.example -f docker-compose.yml -f docker-compose.prod.yml config --quiet
git diff --check
```

Estos dos comandos `config --quiet` validan los archivos; no arrancan ni despliegan contenedores.

## 6. Quiero subir el cambio a GitHub

```bash
git diff --stat
git diff
git add backend/app/main.py frontend/app/page.tsx
git commit -m "Describe el problema corregido y el resultado"
git push -u origin codex/mi-mejora
```

El `git add` es un ejemplo: selecciona los archivos que realmente modificaste, incluidas las pruebas. No subas `.env`, contraseñas, datos de clientes ni copias de bases de datos.

Abre GitHub → `TdigitaTel/WEB_B2B` → **Pull requests → New pull request**.

Selecciona:

- **base: develop**
- **compare: codex/mi-mejora**

Describe el problema, la solución, las pruebas y cualquier migración pendiente. Revisa el destino antes de crear el PR.

## 7. Quiero probarlo en desarrollo

1. Espera los checks de **Validar Web B2B**: backend, frontend y compose.
2. Revisa los archivos y fusiona el PR hacia `develop`.
3. En **Actions → Desplegar Web B2B**, abre el run del commit fusionado.
4. Comprueba que el trabajo `development` termina correctamente.
5. Abre `http://192.168.0.117:8081/` y reproduce el caso de la mejora.
6. Comprueba también una función relacionada que pudiera verse afectada.

En un run de `develop`, `production` aparece **Skipped**: es el comportamiento esperado. En un run de `main`, ocurre lo contrario.

En **Linux**, puedes consultar los contenedores y errores:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
docker logs --since 10m --tail 100 webb2b-dev-api-1
docker logs --since 10m --tail 100 webb2b-dev-web-1
```

Los nombres indicados son los observados en este servidor; si cambian, usa los nombres que devuelve `docker ps`.

## 8. Quiero pasar a producción

En GitHub crea otro PR:

- **base: main**
- **compare: develop**

Revisa **todos** los cambios de ese PR: puede contener otras mejoras que también estén en `develop`. No lo fusiones si incluye trabajo aún sin validar.

Tras revisar los checks y validar desarrollo:

1. Fusiona el PR de `develop` hacia `main`.
2. Abre su run de **Desplegar Web B2B**.
3. Si el entorno solicita aprobación, revisa el commit y aprueba el despliegue.
4. Espera el resultado correcto de `production`.
5. Abre `https://extranet.bermudezulloa.es/` y comprueba la mejora con el perfil apropiado.

El workflow utiliza un runner Linux con etiquetas `self-hosted`, `linux`, `webb2b`. Si aparece Queued, comprueba en GitHub que ese runner esté conectado. No repitas despliegues mientras haya otro ejecutándose.

## 9. ¿Qué hace el despliegue con PostgreSQL?

El script `ops/deploy.sh` valida Compose, realiza un `pg_dump` si la base ya está ejecutándose, construye las imágenes, levanta los contenedores y verifica API y portada. El arranque de la API ejecuta `python -m app.bootstrap` antes de iniciar el servicio.

Después de las comprobaciones, el script ejecuta la reclasificación de materiales. En desarrollo también importa las imágenes iniciales de categorías. Por eso un despliegue puede ejecutar tareas sobre los datos además de cambiar el código.

Desarrollo y producción tienen bases y volúmenes independientes. Fusionar código **no copia los datos de desarrollo a producción**. Si una mejora necesita configuración, clasificaciones, imágenes o datos iniciales, documenta cómo se aplican en producción.

Para comprobar campos en PostgreSQL de producción, en **Linux**:

```bash
docker exec -i web_b2b-db-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('orders', 'users')
ORDER BY table_name, ordinal_position;
SQL
```

SQL se ejecuta dentro de `psql` o DBeaver; escribir `UPDATE` directamente en `root@NestorIA:~#` produce `command not found`.

## 10. ¿Dónde están los parámetros privados?

En **Linux**:

```text
/opt/proyectos/WEB_B2B_INFRA/config/dev.env
/opt/proyectos/WEB_B2B_INFRA/config/prod.env
```

Para editar producción:

```bash
nano /opt/proyectos/WEB_B2B_INFRA/config/prod.env
```

Un cambio en ese archivo requiere recrear los servicios afectados para aplicarse. No cambies `COMPOSE_PROJECT_NAME`: debe conservar el proyecto y volumen existentes. Tampoco confundas el cambio de `POSTGRES_PASSWORD` en el archivo con un cambio de contraseña dentro de una base ya inicializada.

| Recurso observado | Desarrollo | Producción |
|---|---|---|
| Web en LAN | `192.168.0.117:8081` | `192.168.0.117:8080` |
| Contenedor PostgreSQL | `webb2b-dev-db-1` | `web_b2b-db-1` |
| PostgreSQL en LAN | `192.168.0.117:5434` | `192.168.0.117:5433` |

Los valores reales de los archivos privados prevalecen sobre los ejemplos del repositorio.

## 11. Quiero desplegar manualmente desde Linux

Esta alternativa ejecuta el mismo script que Actions. Úsala solo cuando no haya un despliegue automático en curso. Si Actions ya publicó ese commit, no hace falta ejecutarlo de nuevo.

Necesitas un checkout Git limpio y dedicado en el servidor, con acceso al repositorio y permiso para utilizar Docker. Entra en su ruta real:

```bash
cd "RUTA_DEL_CHECKOUT_LINUX"
git status --short
git fetch origin
```

### Desarrollo

```bash
git switch --detach origin/develop
export WEBB2B_CONFIG_DIR=/opt/proyectos/WEB_B2B_INFRA/config
export WEBB2B_BACKUP_DIR=/opt/proyectos/WEB_B2B_INFRA/backups
export WEBB2B_STATE_DIR=/opt/proyectos/WEB_B2B_INFRA/releases
bash ./ops/deploy.sh dev "$(git rev-parse HEAD)"
```

### Producción

Primero verifica que el commit está en `main` y que se validó en desarrollo. Guarda la versión actualmente publicada antes de ejecutar el despliegue:

```bash
cat /opt/proyectos/WEB_B2B_INFRA/releases/prod.current
git switch --detach origin/main
git log -1 --oneline
export WEBB2B_CONFIG_DIR=/opt/proyectos/WEB_B2B_INFRA/config
export WEBB2B_BACKUP_DIR=/opt/proyectos/WEB_B2B_INFRA/backups
export WEBB2B_STATE_DIR=/opt/proyectos/WEB_B2B_INFRA/releases
bash ./ops/deploy.sh prod "$(git rev-parse HEAD)"
```

Es necesario indicar estas carpetas: sin las variables, el script utiliza sus rutas genéricas `/opt/webb2b/...`, que son distintas de las configuradas en Actions.

Comprueba el resultado:

```bash
cat /opt/proyectos/WEB_B2B_INFRA/releases/prod.current
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker logs --since 10m --tail 100 web_b2b-api-1
```

## 12. Quiero volver a una versión anterior

Si falla la comprobación de salud durante el despliegue, el script intenta restaurar las imágenes anteriores. Esto **no revierte el esquema ni los cambios de datos**. La disponibilidad de API y portada tampoco garantiza que todas las funciones estén correctas.

Para corregir una mejora funcional, el flujo habitual es preparar una reversión en una rama, probarla y pasarla por `develop` y `main`. En la terminal de un checkout limpio:

```bash
git fetch origin
git switch -c codex/revertir-mejora origin/develop
git revert SHA_DEL_COMMIT_DE_LA_MEJORA
git push -u origin codex/revertir-mejora
```

Si el commit que reviertes es un merge, examina primero sus padres; `git revert` requiere elegir el padre principal con `-m`. No uses esa opción sin revisar qué cambios revertirá.

En una recuperación urgente, puedes desplegar un SHA conocido y compatible con el esquema actual desde el checkout Linux:

```bash
git switch --detach SHA_VALIDADO
bash ./ops/deploy.sh prod "$(git rev-parse HEAD)"
```

Mantén las variables de carpetas del paso 11. Este despliegue no mueve `main`: deja documentada la recuperación y regulariza después la rama para que un futuro despliegue automático no vuelva a publicar el fallo. Restaurar una copia PostgreSQL es otra operación y debe planificarse considerando los pedidos y cambios posteriores a esa copia.

## 13. Quiero saber por qué no aparecen pedidos

1. Comprueba si la pantalla muestra un error o un listado vacío.
2. Revisa fechas, estado y delegación.
3. Comprueba el usuario y el pedido con SQL de solo lectura.
4. Consulta los logs de API inmediatamente después de reproducir el problema.

En DBeaver conectado a PostgreSQL del ambiente afectado:

```sql
SELECT order_number, nro_pedido_exit, origen_pedido,
       estado_registro_exit, company_code, delegation_code, created_at
FROM orders
WHERE order_number = 'WEB-2026-0000242';

SELECT id, email, role, company_code, delegation_code, active
FROM users
WHERE role = 'OPERADOR_TIENDA';
```

En Linux, tras pulsar Consultar:

```bash
docker logs --since 2m --tail 100 web_b2b-api-1
```

`Pedidos WEB` debe partir de los pedidos locales con origen `B2B`; el número EXIT permite vincular datos externos. No debe añadir pedidos normales de EXIT por el hecho de existir en esa base.

## 14. Quiero actualizar este manual

Archivo versionado: `docs/manual-publicacion.md`. Modifícalo en una rama de trabajo y crea un PR hacia `develop`, igual que cualquier cambio. Si cambian las rutas, comandos o pasos de la aplicación, actualiza el manual en el mismo PR de la mejora.

Antes de dar una publicación por terminada, deja registrado: PR, commit, resultado de las pruebas, run de despliegue y resultado de la validación funcional.
