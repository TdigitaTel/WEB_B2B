# Planificación de líneas

Los pedidos WEB nuevos guardan su planificación inicial al enviarse. Los borradores lo hacen al convertirse en pendientes. Consultar un pedido solo lee la planificación persistida; no consulta stock en EXIT ni recalcula fechas. Las modificaciones del operador se realizan desde Editar fechas y observaciones. El cliente solo puede consultar.

El stock mostrado es el consultado al generar la planificación, no una reserva ni un saldo actualizado en directo. Las actualizaciones automáticas posteriores quedan pendientes de definir.

## Pedidos WEB anteriores

El despliegue inicializa los pedidos WEB pendientes que aún no tienen planificación, después de confirmar que la web y la API están saludables. Si EXIT no está disponible, muestra un aviso sin retirar el servicio. Para repetir manualmente la inicialización: El proceso se ejecuta en bloques de 20 pedidos y consultas de hasta 500 códigos; no sobrescribe ninguna línea existente. Ante un fallo EXIT se detiene y se puede repetir conservando los bloques ya confirmados.

```bash
docker exec web_b2b-api-1 python -m app.initialize_line_planning --apply
```

Para desarrollo, sustituir el contenedor por webb2b-dev-api-1. Sin --apply solo informa del número de pedidos pendientes. No crea tareas periódicas ni modifica EXIT.
