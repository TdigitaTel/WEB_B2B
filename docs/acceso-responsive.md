# Acceso responsive de la extranet

La pantalla conserva usuario y contraseña como acceso principal. «Acceso con QR» despliega debajo las opciones existentes, incluido enlace, archivo y cámara. El acceso mediante enlace QR sigue funcionando aunque el panel esté cerrado.

## Distribuciones

- Hasta 720 px de ancho: cabecera compacta (34 % de la altura estable, entre 170 y 340 px), formulario a todo el ancho y controles de al menos 52 px. El titular y el edificio se mantienen dentro del gráfico, sin recortes ni deformación.
- Escritorio: dos columnas, imagen completa a la izquierda y formulario a la derecha. Una ventana horizontal pequeña utiliza dos columnas compactas cuando dispone de hasta 900 px de ancho y 600 px de alto.
- Kiosco: abrir la URL habitual con `?kiosk=1` (o añadir `&kiosk=1` si ya hay parámetros). Reutiliza la opción existente; no activa el kiosco de acceso por agente de navegador ni por detectar una tableta táctil. Por encima de 720 px utiliza una columna con la imagen en el 32 % de la altura estable (máximo 660 px), formulario amplio debajo y controles de 72/76 px. En ventanas de hasta 1100 px de alto se compactan a 58/60 px.

La configuración explícita evita que el teclado, al cambiar la proporción de la ventana, devuelva el kiosco a dos columnas. Las reglas de ancho, altura y orientación adaptan la composición restante. No hay altura fija ni bloqueo de desplazamiento. `visualViewport.resize` acerca el campo activo cuando se abre el teclado. Se conserva autocompletado, Enter avanza de usuario a contraseña y el botón sigue accesible mediante desplazamiento o tabulación.

## Imágenes y avisos

Se reutiliza la imagen configurada en Imagen de acceso. No se modifica ni se sustituye el recurso guardado. No hay capas de texto adicionales sobre la imagen. El titular de la imagen actual está integrado en el gráfico; no existe una versión por capas en el repositorio, por lo que no se separa ni se duplica. `object-fit: contain` conserva todos los elementos y deja fondo de marca cuando las proporciones no coinciden. Si falla la imagen, se conservan logotipo, titular y texto originales como alternativa.

La comprobación inicial de cuenta sin sesión no muestra «La sesión ha finalizado». Una sesión que sí estaba identificada conserva ese aviso al caducar. Se retira al iniciar otro acceso y los errores nuevos de credenciales tienen prioridad. No cambia ningún endpoint, validación o mecanismo de autenticación.

## Validación

Pruebas locales con respuestas de API simuladas y una captura del gráfico original solo para previsualización (no incluida en la aplicación). Revisadas ventanas de 390 × 844, 320 × 568, 768 × 1024, 1080 × 1920 y escritorio 1440 × 900. Altura reducida a 390 × 440 y 768 × 520 para simular el espacio del teclado; campo activo y botón accesibles por desplazamiento. Las pruebas automáticas cubren foco, credenciales, errores, QR secundario, imagen fallida y avisos inicial/real de sesión. No se dispone del kiosco físico: pendiente contrastar reflejos, distancia de lectura y teclado nativo en el dispositivo instalado.
