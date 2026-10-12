# Conectar pgModeler a desarrollo

El despliegue de `develop` publica PostgreSQL en la red local:

- Servidor: `192.168.0.117`
- Puerto: `5434`
- Base de datos, usuario y contraseña: valores `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` de `/opt/proyectos/WEB_B2B_INFRA/config/dev.env`.

En pgModeler crea una conexión con esos valores y prueba la conexión. El Mac debe tener acceso a la red del servidor.

El puerto puede configurarse con `POSTGRES_DEV_BIND` y `POSTGRES_DEV_PORT` en `dev.env`. Son parámetros exclusivos de desarrollo. El volumen `postgres_data` existente se conserva al recrear el contenedor.

Para comprobarlo en Linux:

```sh
docker port webb2b-dev-db-1 5432
```

Resultado esperado: `192.168.0.117:5434`.
