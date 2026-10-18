# Instalador GDF para Raspberry Pi 4

## Alcance y estado de validación

Referencia: Raspberry Pi 4 Model B, Raspberry Pi OS/Debian 11 Bullseye de 64 bits,
Python 3.9 y cámara IMX708 con enfoque automático, como el equipo actual.
El mismo modelo de Raspberry con Bookworm/Trixie u otro Python NO es equivalente:
el instalador se detiene para evitar instalar dependencias incompatibles.

Preparado para equipos nuevos. No actualiza instalaciones existentes ni copia sus
credenciales. No modifica cron ni instala limpieza automática. No instala AnyDesk
ni Tailscale. Requiere al menos 8 GiB libres durante instalación.

Primero busca un entorno compatible: comprueba Python, versiones de TensorFlow,
NumPy y protobuf, e importa las librerías de cámara, detección, OCR y heartbeat
como el usuario del servicio. Si pasa, reutiliza ese Python sin ejecutar apt ni
pip ni modificar sus librerías. Si no encuentra uno válido, crea el entorno nuevo
y descarga las dependencias (requiere Internet). No basta con encontrar una carpeta.
`--fresh-env` fuerza un entorno nuevo; `--python /ruta/al/python` valida uno concreto
y se detiene si no sirve. Las librerías del usuario se mantienen accesibles al
reutilizar un entorno. No se requiere que el entorno tenga credenciales cargadas.

Los paquetes principales están fijados; las dependencias transitivas y paquetes apt
todavía no forman un lock completo ni un paquete offline. La descarga depende de
los repositorios. La primera instalación puede tardar y compilar alguna librería.
Una instalación limpia en otra tarjeta/equipo sigue siendo necesaria para certificar
el conjunto. No reemplazar la Raspberry de producción para probar el instalador.

## Pasos en una Raspberry nueva

Crear primero un usuario del sistema (por ejemplo `pi`), configurar red, hora/NTP
y conectar la misma cámara. Abrir una terminal en la carpeta del paquete:

```bash
sha256sum -c GDF_instalador_pi4.tar.gz.sha256
tar -xzf GDF_instalador_pi4.tar.gz
cd gdf-installer
python3 deploy/pi_installer.py preflight
sudo python3 deploy/pi_installer.py install --user pi
sudo python3 /opt/gdf/deploy/pi_installer.py check --hardware
sudo python3 /opt/gdf/deploy/pi_installer.py start
```

Cambiar `--user pi` por el usuario real si tiene otro nombre. No usar `root` como
cuenta de servicio. El directorio predeterminado es `/opt/gdf`; si se cambia con
`--root`, pasar el mismo valor en todos los comandos posteriores.

Al terminar `install` se abre automáticamente una ventana con los tres campos:
endpoint de Azure, clave de Azure y clave de Genyus. Las claves aparecen ocultas.
Si no hay escritorio accesible, se solicitan en la terminal interactiva con las
claves ocultas. Cancelar conserva el software instalado y deja el arranque pendiente.
Para volver a abrir la ventana o cambiar las claves después:

```bash
sudo python3 /opt/gdf/deploy/pi_installer.py configure
```

`--terminal` fuerza la entrada en terminal y `install --skip-config` permite posponer
las preguntas. No se aceptan claves por entrada redirigida sin control de eco.
No se solicitan claves por chat ni se incluyen en el paquete. El número de serie se
obtiene del hardware de cada equipo. Las opciones del segundo heartbeat se ponen,
si hacen falta, en `/opt/gdf/runtime.env` (permiso 600, propiedad del usuario del
servicio). Cada equipo debe tener su etiqueta y autorización para ese receptor.
El formato env es el de systemd; no ejecutar ese archivo con `source`.

`check --hardware` importa las librerías, carga el modelo, ejecuta una inferencia
sintética y toma un fotograma en memoria. No llama al OCR, no envía placas ni
guarda esa foto. Necesita el lector detenido y no debe ejecutarse contra una
cámara que ya esté en uso por otro programa. Las conexiones de comprobación de
Azure/Genyus validan DNS/TLS, NO prueban la clave ni el contrato de la API.

`start` repite comprobaciones de hardware, arranca servicios y espera hasta 180 s
por un fotograma reciente del PID actual. Si no llega, detiene los dos servicios.
Solo tras ese control los habilita al arrancar el sistema. Un heartbeat activo
todavía no confirma que Genyus haya aceptado una placa real.

## Si hay un error

Cada etapa muestra su nombre al comenzar, el tiempo transcurrido cada 30 segundos
y el resultado al terminar. El archivo `gdf-reports/installer-status.json` conserva
el ultimo estado (o la carpeta indicada con `--report-dir`). El tiempo no es un
porcentaje estimado de descarga. La entrada de claves se identifica como espera
de credenciales; el progreso no contiene comandos, claves ni salida cruda de pip.

Cada comando escribe `REPORT=...json`, incluso si falla. El JSON incluye etapa,
código, resultado, categoría conocida y acción sugerida. **Pásame ese archivo**.
No contiene claves, Config.xml, IP, fotos, placas, serial del dispositivo ni logs
crudos. Los archivos se crean con permiso 600 y nunca se envían automáticamente.
Para generar un diagnóstico posterior sin detener los servicios:

```bash
sudo python3 /opt/gdf/deploy/pi_installer.py diagnose
```

Si la instalación falló antes de copiar `/opt/gdf`, ejecutar `diagnose` desde el
paquete extraído. El reporte puede tener errores de servicios/modelo porque aún
no están instalados. Si hace falta detalle local, ejecutar el paso fallido en la
terminal o consultar `sudo journalctl -u gdf-reader -n 50`; esos logs pueden tener
lecturas, por lo que no se agregan al reporte compartible.

La instalación rechaza un directorio destino o unidades existentes. Tras un fallo
no borra archivos: conservar el reporte y revisar `/opt/gdf/installation.json`.
Antes de reintentar, revisar y renombrar manualmente solo ese destino incompleto
y retirar únicamente las unidades creadas por este intento, si las hubiera.
No aplicar ese procedimiento a un equipo que ya está operando.

## Prueba aislada en un equipo que ya funciona

`install --isolated-test --root /opt/gdf-test --skip-config` crea un entorno de
Python y copia el programa/modelo en ese directorio nuevo. Reutiliza las librerías
del sistema, omite apt, grupos y registro de servicios. No equivale a una instalación
limpia del sistema operativo. El comando `start` rechaza estas instalaciones para
evitar interferir con los servicios de producción. No probar la cámara mientras
el lector actual la utiliza. Después se puede ejecutar `configure --root /opt/gdf-test`
para introducir credenciales solo en la copia de prueba.

## Diferencias deliberadas frente al entorno antiguo

Para instalaciones nuevas se usa protobuf 3.20.3 (satisface el mínimo declarado
por TensorFlow) y Pillow 9.5.0. Estas versiones deben pasar la prueba del modelo
en la instalación nueva; no se cambian las de producción. La API antigua de
Object Detection se instala sin sus dependencias de notebooks/publicación y se
prueban sus utilidades de ejecución. `pip check` puede reportar esas dependencias
opcionales omitidas; la prueba de imports/modelo es el control específico.

## Construir otro paquete desde el código

```bash
python3 deploy/build_release.py --model-root /ruta/GDF --output GDF_instalador_pi4.tar.gz
```

El constructor usa una lista explícita de módulos y archivos. Excluye credenciales,
fotografías, logs y archivos de ejecución, genera hashes por archivo y un SHA256
del archivo comprimido. Verificar el SHA256 por un canal de confianza; un manifiesto
de hashes comprueba integridad, no sustituye una firma del autor.

## Instalacion con doble clic mediante AnyDesk

Extrae el paquete y abre `Instalar_LIPER.desktop` en la Raspberry. Si el escritorio lo solicita, permite su ejecucion. El lanzador muestra el avance en una terminal y pide autorizacion de administrador. La ventana solicita el endpoint y la clave de Azure, la clave de Genyus y el nombre del equipo para el monitor; este nombre no cambia el hostname del sistema. Luego comprueba el hardware y arranca los servicios.

El nombre admite de 3 a 40 caracteres. El instalador consulta su disponibilidad en el monitor. Si la consulta no esta disponible, muestra una advertencia y solo permite continuar mediante confirmacion explicita; en ese caso la unicidad no queda verificada. La consulta no reserva un nombre.
