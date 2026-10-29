# Series de pedidos de venta por empresa y delegación

Pantalla: **Parámetros → Series de pedidos**. Consulta de solo lectura a EXIT:

```sql
SELECT s.CodigoEmpresa, s.serie, s.TipoDocumento, s.DescripcionSerie
FROM Series s
WHERE s.TipoDocumento = 'PedV';
```

Se muestran empresa, serie, tipo y descripción. Al pulsar **Asociar**, se elige una delegación de la misma empresa y si la asociación debe quedar activa. La lista inferior permite buscar, filtrar por estado y activar/desactivar asociaciones. No se modifica `Series` ni se asigna automáticamente una serie a un pedido existente.

## Tabla complementaria de PostgreSQL

`sales_order_series_assignments` guarda:

- `company_code`: empresa, separada de la delegación.
- `delegation_code`: código de delegación de dos dígitos, como `00` o `02`; no guarda `1:00`.
- `document_type`: `PedV`.
- `series_code`: código de serie de EXIT, conservando ceros iniciales y admitiendo la serie vacía si existe en EXIT.
- `active`: estado booleano; la pantalla muestra **Activa / Inactiva**.
- `series_description`, `delegation_name`: descripciones de referencia tomadas de EXIT al asociar o activar.
- `version`, `updated_by` y fechas para control de cambios y auditoría.

Puede haber varias series asociadas a la misma empresa y delegación, pero un índice único parcial impide tener dos activas. Al activar una serie se desactiva la anterior **en la misma transacción**. La configuración de otras empresas/delegaciones permanece independiente. Las asociaciones no se eliminan: se conservan como inactivas.

La tabla y sus índices se crean con el bootstrap habitual de la API. No requiere modificar tablas de EXIT ni una migración manual.

## API de consulta para integraciones

```http
GET /api/v1/integrations/sales-order-series/active?company_code=1&delegation_code=00
X-Integration-Key: <clave de integración ya configurada>
```

Respuesta de ejemplo (los códigos de serie dependen de EXIT y de la configuración guardada):

```json
{
  "id": 12,
  "company_code": 1,
  "delegation_code": "00",
  "document_type": "PedV",
  "series_code": "WEB",
  "series_description": "Pedidos web",
  "delegation_name": "Almeiras",
  "active": true,
  "version": 1,
  "updated_at": "2026-10-29T10:00:00+00:00"
}
```

Se reutiliza `INTEGRATION_API_KEY`; no se crea una clave nueva ni se expone en la pantalla. La consulta solo lee la configuración local, por lo que funciona aunque EXIT no esté disponible. La autenticación es necesaria en cada petición y las respuestas no se almacenan en caché.

- `200`: existe una única asociación activa.
- `404`: no hay ninguna serie activa para esa empresa y delegación; no se elige una inactiva ni una serie de otra delegación.
- `409`: hay una configuración ambigua; no se devuelve arbitrariamente la primera fila. El índice evita este estado en el funcionamiento normal.
- `422`: parámetros incorrectos; la delegación debe tener dos dígitos.
- `401`: clave de integración incorrecta o ausente.
- `503`: la clave de integración todavía no está configurada.

## API de la web

Requiere sesión de administrador u operador:

- `GET /api/v1/store/sales-order-series/options`: series PedV y delegaciones de EXIT permitidas al usuario.
- `GET /api/v1/store/sales-order-series/assignments`: asociaciones locales; filtros opcionales `company_code`, `delegation_code`.
- `PUT /api/v1/store/sales-order-series/assignments`: crear/guardar asociación con `company_code`, `delegation_code`, `series_code`, `active`.
- `PATCH /api/v1/store/sales-order-series/assignments/{id}`: cambiar estado enviando `active` y `expected_version`.
- `GET /api/v1/store/sales-order-series/active?company_code=1&delegation_code=00`: consulta local para operadores con permiso de Pedidos o Parámetros y acceso a esa empresa/delegación.

La gestión requiere el permiso **Parámetros**, además del acceso a la delegación. Cada alta o activación valida en EXIT que tanto la delegación como la serie pertenezcan a la empresa indicada. Si EXIT no responde, las asociaciones y la consulta de la serie activa siguen disponibles; se permite desactivar una asociación, pero no activar una serie sin validar. Los cambios quedan auditados y un formulario desactualizado recibe `409`.

## Validación

Pruebas de consulta SQL parametrizada con los cuatro campos facilitados; asociación y persistencia separada de empresa/delegación; cambio de activa en ambos sentidos; aislamiento entre empresas y delegaciones; restricción de unicidad en base de datos; validación contra EXIT; estado inactivo; serie vacía; consulta y desactivación con EXIT caído; clave de integración; permisos de módulos y delegaciones; conflictos de versión. Pendiente comprobar la consulta con el SQL Server real en desarrollo.
