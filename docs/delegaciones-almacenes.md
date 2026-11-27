# Delegaciones y almacenes

Parámetros → Delegaciones y almacenes permite configurar relaciones locales sin escribir en EXIT.
Administración y operadores con permiso de Parámetros pueden sincronizar y guardar. Los operadores solo consultan y configuran sus delegaciones autorizadas.

## Tabla intermedia

`delegation_warehouses` se crea al ejecutar el arranque habitual `python -m app.bootstrap`, mediante `Base.metadata.create_all`, también en instalaciones existentes. Su clave primaria es:

- `company_code`: `delegaciones.CodigoEmpresa`.
- `delegation_code`: `delegaciones.IdDelegacion`.
- `warehouse_code`: `almacenes.CodigoAlmacen`, siempre de la misma empresa.

La delegación se referencia por **empresa y código**, nunca solo por IdDelegacion. No hay una FK física entre PostgreSQL y SQL Server: cada alta y modificación se valida con las tablas vivas de EXIT.

Se guardan los nombres de delegación y almacén como datos informativos actualizables, los indicadores `is_primary`, `active`, `use_for_stock`, la versión y las fechas. Las modificaciones quedan registradas en auditoría. La clave compuesta impide duplicados; un índice único parcial garantiza como máximo un principal por empresa y delegación.

## Sincronización

La pantalla consulta `delegaciones` y `almacenes` de EXIT. Al abrirla un usuario autorizado, o al pulsar Actualizar desde EXIT, se sincroniza el principal de cada delegación a partir de `delegaciones.CodigoAlmacen`. No se realiza esta escritura en los GET de la API.

El principal se inserta inicialmente activo y marcado para stock. Las siguientes sincronizaciones conservan ambos indicadores. Si cambia el principal en EXIT, el anterior se conserva como adicional con sus indicadores y se incorpora/promueve el nuevo. Los principales aparecen primero. La sincronización es transaccional; si EXIT falla, se conserva la configuración local.

Los adicionales se seleccionan de `almacenes`, filtrados por `CodigoEmpresa`, sin límite fijo por delegación. El mismo almacén puede asociarse a varias delegaciones si se configura así; no hay unicidad global por almacén.

## API

Prefijo `/api/v1/store/delegation-warehouses`:

- GET `/options`: delegaciones y almacenes de EXIT, y `can_edit`.
- POST `/sync`: sincronizar principales (permiso de Parámetros).
- GET `/assignments`: relaciones guardadas, principal primero. Acepta `company_code`, `delegation_code` y `stock_only`.
- PUT `/assignments`: alta o cambio de indicadores; para actualizar se exige `expected_version`.

`stock_only=true` devuelve exclusivamente relaciones con **active=true y use_for_stock=true**. Las consultas existentes de reposición siguen usando su vista por delegación; esta entrega añade la configuración y su consulta, sin cambiar la agregación de existencias ni duplicar stock entre vistas y almacenes.
