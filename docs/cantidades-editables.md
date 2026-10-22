# Cantidades editables en móvil

Catálogo y carrito usan un campo que conserva el texto mientras se escribe. Se puede borrar el 1 y escribir otra cantidad. Un vacío temporal no envía cero a la API y no elimina artículos del carrito. Las flechas nativas y la edición con teclado se conservan.

Al salir del campo o pulsar Intro se valida el valor: mínimo 1 y máximo 99999. El carrito ordena las actualizaciones para evitar que una respuesta antigua sobrescriba la última cantidad y espera a que terminen antes de enviar el pedido. El botón de eliminar sigue siendo la acción explícita para quitar artículos.

Sin cambios de backend ni migración. Se verifican con React y DOM simulado el borrado temporal, sustitución, flechas, límites y respuestas externas mientras se escribe. La prueba no sustituye una validación física en Android.
