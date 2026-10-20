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

Publicar este cambio de código no actualiza por sí solo los equipos. Caucel1, Caucel4 y Caucel6 se actualizaron de forma controlada el 20 de octubre de 2026 (ver registros debajo). No volver a ejecutar el instalador nuevo sobre `/opt/gdf`. Para desplegar hay que respaldar la versión activa, copiar los archivos correspondientes a su ruta real, conservar `Config.xml`/`runtime.env` y datos/modelo, y reiniciar de forma controlada. La integración necesita `MainPlateGSF.py`, `LiPER_NNP.py` y `local_dashboard.py` de la misma versión; el lanzador gráfico necesita `deploy/open_dashboard.py`.

Después verificar servicios, primer fotograma, panel local y una lectura real. Hasta entonces no considerar certificado el consumo de CPU, latencia ni funcionamiento de cámara real de esta versión.

## Registro de actualización de Caucel4 — 20 de octubre de 2026

- Aplicación activa: `/opt/gdf`, versión del panel `24d47c1`. Antes estaba en `/opt/gdf-test-reuse-20261018`.
- Se conservaron el modelo, `Config.xml` y `runtime.env` del equipo. Se habilitó `GDF_DASHBOARD=1`.
- Fotos y evidencia siguen en `/home/pi/Desktop/GDF/{SavedPlates,ErrorOCR,OCREvidence}`, enlazadas desde la aplicación activa. Limpieza automática desactivada.
- Respaldo privado: `/home/pi/backups/dashboard-update-20261020-111925`. Incluye unidades de servicio anteriores, archivo de código/configuración y `previous-installation` (la instalación retirada). `legacy-desktop-code` contiene los 27 elementos de código/modelo retirados del antiguo directorio del escritorio; las carpetas de imágenes permanecieron allí.
- Servicios del lector y heartbeat activos, habilitados y sin reinicios durante la comprobación. Solo un proceso lector.
- Cámara real: fotograma reciente verificado; vista JPEG y API del panel respondieron HTTP 200 por loopback. El navegador Chromium arrancó en la sesión gráfica.
- Iconos creados: `/home/pi/Desktop/LIPER-dashboard.desktop` y `/home/pi/.config/autostart/liper-dashboard.desktop`, propiedad de `pi`, ejecutables. El cliente abre el icono **LIPER - Camara y lecturas** con doble clic.
- Al terminar, el panel tenía cero lecturas en la nueva sesión. Quedan pendientes una nueva placa real, su tarjeta y la entrega a Genyus; no se reenviaron placas históricas para esta prueba. No se certificó aún consumo sostenido de CPU.

El respaldo contiene secretos: no publicarlo ni adjuntarlo a paquetes públicos. Para revertir, detener ambos servicios, devolver `previous-installation` a su ruta anterior y restaurar las unidades guardadas; antes revisar rutas y estado actual. Restaurar el lanzador del escritorio según la versión que quede activa. No arrancar simultáneamente los dos lectores ni borrar las carpetas de fotos.

## Registro de actualización de Caucel6 — 20 de octubre de 2026

- Acceso por SSH desde la laptop mediante Caucel4, con clave pública autorizada por el usuario en Caucel6. No se copió la clave privada al puente. La identidad SSH del destino se verificó contra la huella observada previamente.
- Se respaldó y sustituyó `/opt/gdf` por la versión con panel `24d47c1`, manteniendo modelo, claves y configuración del monitor del equipo. Los servicios anteriores se detuvieron durante el cambio.
- Respaldo privado: `/home/pi/backups/dashboard-update-20261020-170812`, con unidades anteriores, código/configuración y `previous-installation`.
- Las carpetas activas SavedPlates, ErrorOCR y OCREvidence se movieron sin copiar ni borrar imágenes a `/home/pi/.local/share/liper-data/`, con enlaces desde la aplicación nueva y la copia anterior. Los datos quedan separados del programa. El directorio histórico del escritorio no se eliminó.
- Lector y heartbeat activos, habilitados y sin reinicios durante la comprobación; un solo proceso lector. Cámara real reciente y JPEG del panel verificados con HTTP 200. Chromium abierto en la sesión gráfica.
- Acceso `/home/pi/Desktop/LIPER-dashboard.desktop` y autoinicio gráfico instalados. El cliente usa doble clic en **LIPER - Camara y lecturas**.
- El log de la nueva sesión confirmó tres heartbeats aceptados por el monitor y cero fallos de destino al comprobarlo. Las tarjetas empezaron vacías; falta comprobar una placa real de esta sesión y su entrega a Genyus.
- No se realizó una prueba de corte físico de energía ni de desconexión de internet durante la actualización.

Para revertir Caucel6, detener los dos servicios y conservar aparte la aplicación nueva antes de devolver `previous-installation` a `/opt/gdf`. Mantener la carpeta de datos permanente y sus enlaces: restaurar solo el archivo de código no reconstruye por sí solo el estado de las imágenes. Revisar también las unidades y accesos del escritorio antes de arrancar.

## Cortes de energía o internet

Los servicios habilitados intentan arrancar automáticamente cuando la Raspberry vuelve a encender. Durante un corte de energía no hay captura. El panel gráfico se abre al iniciar sesión en el escritorio; el lector no necesita navegador para operar.

Sin internet, la captura/detección y el panel local pueden continuar, pero el OCR de Azure, la entrega a Genyus y el monitor remoto requieren conectividad. El heartbeat vuelve a intentar en sus ciclos posteriores; las nuevas lecturas vuelven a intentar los servicios cuando hay conexión. No hay cola persistente para garantizar el reprocesamiento y la entrega de eventos fallidos. Guardar una imagen de error no implica que después se reenvíe automáticamente.

## Registro de migración de Caucel1 — 20 de octubre de 2026

- Acceso SSH mediante Caucel4, usando la clave pública autorizada por el usuario. El lector anterior corría en el backend de Thonny desde `/home/pi/Desktop/GDF`; no existía `/opt/gdf` ni servicios GDF instalados.
- Respaldo privado `/home/pi/backups/dashboard-update-20261020-171741`: código, modelo, configuración XML, cron y archivos retirados en `legacy-desktop-code`. Las imágenes históricas no se copiaron ni eliminaron.
- Instalación con panel `24d47c1` en `/opt/gdf`, reutilizando explícitamente `/usr/bin/python3` después de validar su entorno; no hubo apt/pip ni descarga nueva de TensorFlow.
- Se preservaron el modelo y todo el Config.xml original. Los valores literales SMTP se trasladaron al runtime privado sin imprimirlos; no se probó el envío de correo. Los endpoints efectivos de Genyus coincidían con la versión actual; el identificador siguió tomándose del hardware, como hacía el lector anterior.
- Se configuró el monitor con token autorizado y etiqueta `Caucel1`. Tras preparar la copia, se detuvo el backend anterior de Thonny y se arrancaron los servicios nuevos. El editor puede seguir abierto, pero no se debe ejecutar la versión antigua desde él.
- SavedPlates, ErrorOCR y OCREvidence de `/opt/gdf` apuntan a las carpetas de datos de `/home/pi/Desktop/GDF`. El código/modelo anterior se retiró a la carpeta privada de respaldo después de verificar el arranque nuevo.
- Verificado: un lector activo, dos servicios habilitados y sin reinicios, fotograma de cámara reciente, JPEG/API HTTP 200, icono del escritorio y Chromium abiertos. El monitor aceptó cuatro heartbeats al comprobarlo, sin fallos de destino registrados.
- El historial de tarjetas empezó vacío; falta una nueva placa real y verificar su tarjeta y aceptación por Genyus. No se reprocesaron placas históricas para probarlo.

Para revertir Caucel1, detener los servicios nuevos, restaurar los archivos de `legacy-desktop-code` a su carpeta original y revisar el mecanismo de arranque anterior. Conservar las carpetas de imágenes y sus enlaces. No ejecutar dos lectores sobre la misma cámara. El archivo de respaldo contiene secretos y queda fuera del repositorio.
