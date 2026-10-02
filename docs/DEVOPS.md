# Desarrollo y producción en el mismo servidor

La aplicación utiliza dos proyectos Docker completamente independientes:

| Ambiente | Proyecto Compose | Web | API local | PostgreSQL |
|---|---|---:|---:|---|
| Desarrollo | `webb2b-dev` | `8081` | `8002` | volumen propio de desarrollo |
| Producción | `webb2b-prod` | `8080` | `8001` | volumen propio de producción |

Los puertos se pueden cambiar en los archivos privados del servidor. No se comparte la base PostgreSQL entre ambientes. Ambos pueden consultar EXIT con credenciales de solo lectura.

Si producción ya existía antes de implantar este flujo, `COMPOSE_PROJECT_NAME` en `prod.env` debe conservar el nombre del proyecto Compose anterior. Esto permite reutilizar sus contenedores y su volumen PostgreSQL. Se obtiene con `docker inspect NOMBRE_CONTENEDOR_DB --format '{{ index .Config.Labels "com.docker.compose.project" }}'`. No se debe cambiar este valor después de poner producción en servicio.

## Preparación única del servidor

Crear las carpetas que usa el despliegue y dar acceso al usuario del runner:

```bash
sudo mkdir -p /opt/webb2b/config /opt/webb2b/releases /opt/webb2b/backups
sudo chown -R github-runner:github-runner /opt/webb2b
```

Sustituye `github-runner` por el usuario real que ejecutará GitHub Actions. Ese usuario debe pertenecer al grupo `docker`:

```bash
sudo usermod -aG docker github-runner
```

Cerrar y volver a abrir su sesión para aplicar el grupo.

Crear los archivos privados, que nunca se guardan en Git:

```bash
sudo -u github-runner cp .env.development.example /opt/webb2b/config/dev.env
sudo -u github-runner cp .env.production.example /opt/webb2b/config/prod.env
sudo -u github-runner nano /opt/webb2b/config/dev.env
sudo -u github-runner nano /opt/webb2b/config/prod.env
chmod 600 /opt/webb2b/config/dev.env /opt/webb2b/config/prod.env
```

Usa contraseñas, secretos JWT y claves de integración diferentes en cada ambiente.

## Instalación del runner

En GitHub abre **Settings → Actions → Runners → New self-hosted runner**, selecciona Linux y ejecuta en el servidor los comandos que GitHub muestra. Al configurarlo, añade la etiqueta `webb2b` e instálalo como servicio:

```bash
sudo ./svc.sh install github-runner
sudo ./svc.sh start
sudo ./svc.sh status
```

En **Settings → Environments** crea:

- `development`, sin aprobación obligatoria.
- `production`, con aprobación obligatoria del responsable que publica.

## Flujo diario

Este procedimiento se aplica a cada modificación:

1. Actualizar `develop` y crear una rama con prefijo `codex/`:

   ```bash
   git switch develop
   git pull --ff-only
   git switch -c codex/descripcion-del-cambio
   ```

2. Realizar el cambio, comprobarlo localmente y publicar la rama:

   ```bash
   git add ARCHIVOS_MODIFICADOS
   git commit -m "Descripción concreta del cambio"
   git push -u origin codex/descripcion-del-cambio
   ```

3. Crear un pull request hacia `develop`. GitHub ejecuta la compilación de Next.js, las pruebas de FastAPI y la validación de los dos ambientes Docker.
4. Integrar el pull request únicamente cuando todas las comprobaciones estén verdes.
5. La actualización de `develop` despliega automáticamente el ambiente de desarrollo.
6. Validar la web en `http://SERVIDOR:8081`, incluyendo el caso modificado y las funciones relacionadas.
7. Crear un pull request de `develop` hacia `main` usando la plantilla de publicación.
8. Al integrarlo, GitHub espera la aprobación configurada para `production`.
9. Después de aprobar, el servidor crea una copia de PostgreSQL, construye la versión exacta del commit y la publica en `http://SERVIDOR:8080`.
10. El script comprueba `/health` y la portada. Si cualquiera falla, vuelve automáticamente a las imágenes de la versión anterior.

No se debe programar directamente sobre `main` ni `develop`.

## Reglas que deben configurarse en GitHub

En **Settings → Branches → Add branch protection rule**:

### Rama `develop`

- Exigir pull request antes de integrar.
- Exigir que terminen correctamente `frontend`, `backend` y `compose`.
- Bloquear `force push` y eliminación de la rama.

### Rama `main`

- Exigir pull request antes de integrar.
- Exigir al menos una aprobación.
- Exigir que terminen correctamente `frontend`, `backend` y `compose`.
- Exigir que la rama esté actualizada antes de integrar.
- Bloquear `force push` y eliminación de la rama.

En **Settings → Environments → production**, añadir un revisor obligatorio. Esta aprobación es la última barrera antes de modificar producción.

## Primer despliegue manual

Antes de activar GitHub Actions se pueden probar los dos ambientes desde el repositorio:

```bash
./ops/deploy.sh dev prueba-inicial
./ops/deploy.sh prod prueba-inicial
```

El script valida la configuración, construye imágenes con la versión del commit, levanta los servicios y comprueba la API y la web. En producción crea primero una copia comprimida de PostgreSQL en `/opt/webb2b/backups`. Si la comprobación falla, vuelve a levantar la versión anterior registrada.

## Operación

```bash
docker compose --project-name webb2b-dev --env-file /opt/webb2b/config/dev.env \
  -f docker-compose.yml -f docker-compose.dev.yml ps

docker compose --project-name webb2b-prod --env-file /opt/webb2b/config/prod.env \
  -f docker-compose.yml -f docker-compose.prod.yml ps
```

Los registros se consultan cambiando `ps` por `logs -f api` o `logs -f web`.

Para detener desarrollo sin afectar producción:

```bash
docker compose --project-name webb2b-dev --env-file /opt/webb2b/config/dev.env \
  -f docker-compose.yml -f docker-compose.dev.yml down
```

No añadas `-v`, porque borraría el volumen PostgreSQL del ambiente seleccionado.
