# Panel local de cámara y lecturas

El lector sirve el panel en **http://127.0.0.1:8765/**. Abrir esa dirección en el navegador de la propia Raspberry, o ver su escritorio mediante AnyDesk. Es independiente de la página pública de salud: las imágenes de este panel no se envían a Sites.

## Contenido

- Cámara: vista reducida a 640 píxeles de ancho de los fotogramas que ya captura el lector. La frecuencia depende del tiempo de detección; no es un vídeo a 25/30 FPS.
- Cinco placas distintas: miniatura del recorte enviado al OCR, texto normalizado y hora local de recepción de la lectura. Se muestran candidatos con la misma longitud admitida para envío a Genyus (5–7 caracteres).
- Una placa repetida se mueve al principio y actualiza su miniatura/hora; no ocupa una segunda tarjeta.
- Estado de actualización: avisa si no llegan fotogramas recientes o se desconecta el lector.

Estas tarjetas muestran resultados del OCR, no una confirmación de entrega a Genyus ni de exactitud visual. Si una imagen devuelve varios candidatos, pueden compartir el mismo recorte. La comparación de placas usa el texto normalizado: una lectura equivocada puede aparecer como otra placa.

## Uso de recursos y privacidad

No abre una segunda cámara ni ejecuta otra detección. No añade llamadas a Azure ni Genyus. La vista se codifica como máximo dos veces por segundo y solo mientras hay un navegador consultándola. Cada navegador actualiza el estado una vez por segundo. Las miniaturas se preparan una vez por resultado OCR.

Solo se conservan en memoria un fotograma y cinco miniaturas pequeñas, con un límite de tamaño por imagen. El historial visible empieza vacío después de reiniciar el lector; las evidencias originales siguen guardándose como antes. El navegador también consume recursos: el rendimiento con cámara real debe medirse en cada Raspberry.

El servidor escucha únicamente en `127.0.0.1`. Otra laptop no accede a él con la IP de la Raspberry; usar AnyDesk para ver su escritorio. No publicar este puerto en internet. No sirve archivos del disco ni credenciales.

## Apertura automática en nuevas instalaciones

El paquete actualizado incluye el servidor, la integración OCR y el lanzador del escritorio. Al terminar la instalación gráfica se abre el navegador. En el siguiente inicio de sesión gráfica se ejecuta `~/.config/autostart/liper-dashboard.desktop`, que espera al lector. También se crea el acceso `~/Desktop/LIPER-dashboard.desktop`.

Sin escritorio, el lector y el servidor funcionan igualmente; no se abre ninguna ventana. La interfaz se puede abrir manualmente en el navegador de la Raspberry. El lector ejecutado directamente desde una terminal gráfica intenta abrirla al arrancar.

Para apagar el panel, definir `GDF_DASHBOARD=0` en `/opt/gdf/runtime.env` y reiniciar el lector en un momento acordado. No cambia el OCR. El servicio de producción no depende de que haya navegador abierto. Un error al abrir el puerto o actualizar la vista se registra y el lector continúa.

## Equipos que ya están instalados

Este cambio de código no actualiza por sí solo Caucel4 ni Caucel6. No volver a ejecutar el instalador nuevo sobre `/opt/gdf`. Para desplegar hay que respaldar la versión activa, copiar los archivos correspondientes a su ruta real, conservar `Config.xml`/`runtime.env` y datos/modelo, y reiniciar de forma controlada. La integración necesita `MainPlateGSF.py`, `LiPER_NNP.py` y `local_dashboard.py` de la misma versión; el lanzador gráfico necesita `deploy/open_dashboard.py`.

Después verificar servicios, primer fotograma, panel local y una lectura real. Hasta entonces no considerar certificado el consumo de CPU, latencia ni funcionamiento de cámara real de esta versión.
