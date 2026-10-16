# Clientes habilitados y limpieza demo

Accesos de clientes conserva Habilitar cliente como pantalla inicial: buscar código/nombre, seleccionar y habilitar. Clientes habilitados es una lista de consulta, sin botones para administrar cuentas. Nombres y correo se enriquecen en una consulta por lote a EXIT; si EXIT falla se conserva la información local.

El despliegue ejecuta scripts.cleanup_test_customers --apply después de arrancar la API. La copia PostgreSQL del despliegue se realiza antes de reconstruir contenedores. La limpieza elimina solo clientes con código CLI seguido de cinco cifras y correo comprasNNN@cliente.test y sus cuentas de cliente demo. No elimina operadores, administradores ni cuentas reales. Conserva pedidos e historial, desvinculando las referencias a identidades demo eliminadas. Elimina sesiones y carritos de esas cuentas. Es idempotente y se detiene si un cliente demo tiene asociada una cuenta no demo.

Previsualización sin cambios en producción, una vez desplegado el código:

```bash
docker exec web_b2b-api-1 python -m scripts.cleanup_test_customers
```

Aplicación manual, si hace falta fuera del despliegue:

```bash
docker exec web_b2b-api-1 python -m scripts.cleanup_test_customers --apply
```

SEED_PRODUCTS y SEED_CUSTOMERS deben mantenerse a 0 en los archivos privados de ambos ambientes. Sus valores por defecto son ahora 0 para no generar demostraciones por ausencia de configuración.
