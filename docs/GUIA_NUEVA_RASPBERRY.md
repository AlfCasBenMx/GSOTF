# Instalar LIPER en otra Raspberry

Guía guardada el 18 de octubre de 2026. Código: rama `fixes/runtime-reliability`.

## 1. Antes de empezar

- Raspberry Pi 4 Model B, sistema Debian/Raspberry Pi OS 11 Bullseye de 64 bits y Python 3.9.
- Cámara compatible con la configuración de referencia IMX708, conectada y funcional.
- Escritorio accesible localmente o mediante AnyDesk, internet, fecha/hora correctas y al menos 8 GiB libres.
- Usuario normal con permisos sudo; los ejemplos suponen `pi`.
- Fuente de alimentación adecuada. Si aparece bajo voltaje, revisar fuente y cable.
- Endpoint y clave de Azure OCR, clave de Genyus, nombre del equipo y token autorizado del monitor.

El mismo modelo con otro sistema operativo requiere validación aparte. Una tarjeta nueva puede necesitar preparación del sistema y de la cámara antes de estos pasos. El instalador no instala AnyDesk ni Tailscale. La primera instalación completamente limpia en otro equipo todavía requiere validación.

## 2. Si ya existe un lector funcionando

No abrir directamente el lanzador automático. Respaldar primero código, modelo, configuración y mecanismo de arranque. Conservar las imágenes originales. Revisar servicios, cron y autoinicio para evitar dos lectores.

En Caucel6 el programa anterior estaba en `/home/pi/Desktop/GDF` y corría desde Thonny. Se preparó la nueva copia con el anterior activo, se detuvo en Thonny antes de probar la cámara y se arrancaron los nuevos servicios al final. No asumir esas rutas ni ese mecanismo en otro equipo.

El instalador rechaza un `/opt/gdf` existente o sus servicios ya instalados; no es un actualizador. No borrar esas rutas para forzar una reinstalación. Una migración necesita revisar el equipo y preparar la reversión.

### Comandos de respaldo usados en Caucel6

Ejecutar en la Raspberry, como el usuario `pi`. Antes confirmar que la carpeta es realmente `~/Desktop/GDF`; cambiarla si el equipo usa otra ruta. Los comandos siguientes no detienen ni borran el lector.

```bash
hostname
cat /etc/os-release
uname -m
cat /proc/device-tree/model; echo
df -h /
systemctl list-units --all 'gdf*' --no-pager
pgrep -af 'MainPlate|MainHB|LiPER|launcher'
```

Respaldar programa, modelo y configuración, excluyendo imágenes y carpetas temporales que cambian mientras el lector trabaja:

```bash
mkdir -p ~/backups
chmod 700 ~/backups
respaldo="$HOME/backups/GDF-$(date +%Y%m%d-%H%M%S).tar.gz"

(umask 077
tar -czf "$respaldo" \
  --exclude='GDF/SavedPlates' \
  --exclude='GDF/ErrorOCR' \
  --exclude='GDF/OCREvidence' \
  --exclude='GDF/Logs' \
  --exclude='GDF/TempImages' \
  --exclude='GDF/TempSavedImages' \
  --exclude='GDF/PlateRegionImage' \
  --exclude='GDF/__pycache__' \
  -C "$HOME/Desktop" GDF
) &&
tar -tzf "$respaldo" >/dev/null &&
echo "Respaldo verificado: $respaldo"
```

Continuar solo si aparece `Respaldo verificado`. Si hay errores o avisos de archivos cambiando, revisar y repetir el respaldo antes del cambio. La verificación confirma que el archivo se puede leer; no es una prueba completa de restauración ni una copia consistente de datos en ejecución. Las fotos quedan en sus carpetas originales y no están duplicadas en este respaldo. El archivo incluye credenciales: mantenerlo privado y fuera de GitHub y del ZIP público.

Guardar el arranque del usuario y los scripts auxiliares que encontramos en Caucel6:

```bash
arranque="$HOME/backups/arranque-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$arranque"
(umask 077; crontab -l > "$arranque/crontab.txt")
for archivo in "$HOME/check_int.py" "$HOME/Bot.py"; do
  if [ -f "$archivo" ]; then
    (umask 077; cp "$archivo" "$arranque/")
    chmod 600 "$arranque/$(basename "$archivo")"
  fi
done
if [ -d "$HOME/.config/autostart" ]; then
  (umask 077; tar -czf "$arranque/autostart.tar.gz" -C "$HOME/.config" autostart)
fi
echo "Copia de arranque: $arranque"
```

Si `crontab -l` dice que no existe crontab, registrarlo como ausente: no restaurar después el archivo vacío. Estos comandos cubren el arranque del usuario; si hay servicios systemd u otros mecanismos, respaldar sus unidades/configuración antes de modificarlos. No restaurar cron encima de cambios posteriores sin revisarlos.

Comprobar el contenido esperado sin mostrar claves:

```bash
tar -tzf "$respaldo" | grep -E 'Config.xml|MainPlate|MainHB|saved_model|label_map'
sha256sum "$respaldo" > "$respaldo.sha256"
chmod 600 "$respaldo.sha256"
sha256sum -c "$respaldo.sha256"
```

Si la configuración real está fuera de `Desktop/GDF`, respaldarla por separado con permisos privados; por ejemplo, `runtime.env` externo no queda incluido por estos comandos. No pegar su contenido en un chat.

### Referencia de la migración realizada

En Caucel6 se obtuvo `/home/pi/backups/GDF-20261018-151221.tar.gz`, se encontró Debian 11 ARM64/Python 3.9, una Pi 4 Model B Rev 1.2 y 43 GB libres. Cron contenía `check_int.py` y `Bot.py`; no había servicios `gdf` cargados ni carpeta de autoinicio del usuario. Son observaciones de ese equipo y esa sesión, no condiciones garantizadas para otra Raspberry.

Después se instaló en `/opt/gdf`, se detuvo el lector anterior mediante **Stop en Thonny**, se ejecutó `check --hardware` y luego `start`. Se confirmó modelo, captura de cámara, primer fotograma y servicios activos/habilitados. La primera versión del instalador no pedía URL/token del monitor: se detectaron vacíos y se indicó completarlos manualmente. El paquete actual ya pide ambos. No se documentó aún confirmación de recepción de Caucel6 en el monitor ni de una placa real aceptada por Genyus.

Para recuperar archivos sin sobrescribir el programa actual, usar la ruta exacta del respaldo guardado:

```bash
respaldo="$HOME/backups/GDF-20261018-151221.tar.gz"
recuperacion="$(mktemp -d "$HOME/backups/recuperacion-XXXXXX")"
chmod 700 "$recuperacion"
tar -xzf "$respaldo" -C "$recuperacion"
echo "Archivos recuperados en: $recuperacion/GDF"
```

Ese nombre de archivo es solo el ejemplo real de Caucel6; en otro equipo usar su propio respaldo. Para volver al lector anterior hay que detener primero los nuevos servicios y evitar dos lectores sobre la cámara. La carpeta original `~/Desktop/GDF` se conserva: una reversión operativa debe revisar también su arranque y probar cámara, lectura y entrega. No borrar la instalación nueva ni restaurar automáticamente sobre la anterior.

## 3. Descargar y verificar

En una terminal de la Raspberry:

```bash
mkdir -p ~/liper-instalacion
cd ~/liper-instalacion
base="https://raw.githubusercontent.com/AlfCasBenMx/GSOTF/fixes/runtime-reliability/releases"
curl -fL "$base/GDF_instalador_pi4.tar.gz" -o GDF_instalador_pi4.tar.gz &&
curl -fL "$base/GDF_instalador_pi4.tar.gz.sha256" -o GDF_instalador_pi4.tar.gz.sha256 &&
sha256sum -c GDF_instalador_pi4.tar.gz.sha256 &&
tar -xzf GDF_instalador_pi4.tar.gz
```

Continuar solo si la suma coincide. El paquete incluye el modelo; clonar el código por sí solo no sustituye este paquete.

## 4. Instalar en un equipo nuevo

Abrir `~/liper-instalacion/gdf-installer/Instalar_LIPER.desktop` con doble clic. Si el escritorio pregunta, permitir su ejecución. Puede pedir la contraseña del usuario para sudo.

Si el escritorio no ejecuta el acceso, desde una terminal gráfica:

```bash
cd ~/liper-instalacion/gdf-installer
bash deploy/install_desktop.sh
```

El lanzador comprueba compatibilidad, instala, solicita los datos, prueba modelo/cámara y arranca los servicios. Busca un entorno compatible antes de descargar librerías nuevas.

### Datos que pide la ventana

| Campo | Qué introducir |
|---|---|
| Endpoint de Azure OCR | URL HTTPS de tu recurso de Azure |
| Clave de Azure OCR | Clave autorizada del recurso |
| Clave de Genyus | Clave autorizada para ese equipo/proyecto |
| Nombre del equipo | Por ejemplo `Caucel6`; 3–40 letras sin acentos, números, espacios, guion o guion bajo |
| URL del monitor | Viene precargada: `https://liper-health-monitor.loftygrebe10.chatgpt.site/api/heartbeat` |
| Token del monitor | Token autorizado del receptor, que se introduce oculto |

No inventar ni publicar las claves. El token del monitor se obtiene de la configuración privada del proyecto; no está en GitHub. El nombre no cambia el hostname del sistema. La consulta de disponibilidad no reserva un nombre; si no está disponible el servidor de consulta, se advierte que la unicidad no se pudo confirmar.

Azure/Genyus se guardan en `/opt/gdf/Config.xml`; nombre, URL y token del monitor en `/opt/gdf/runtime.env`, con permisos privados. No enviar capturas de estos archivos con secretos visibles.

## 5. Alternativa: avanzar manualmente por etapas

Usar esta ruta en vez del lanzador, no después de haberlo completado:

```bash
cd ~/liper-instalacion/gdf-installer
python3 deploy/pi_installer.py preflight
sudo python3 deploy/pi_installer.py install --user pi
```

Si cualquiera de los comandos falla, detenerse y revisar el reporte. Al terminar la instalación y después de detener cualquier lector anterior que use la cámara:

```bash
sudo python3 /opt/gdf/deploy/pi_installer.py check --hardware
```

Solo si pasa:

```bash
sudo python3 /opt/gdf/deploy/pi_installer.py start
```

Cambiar `pi` por el usuario real del equipo. `install` prepara y configura; no arranca el lector. `check --hardware` requiere la cámara libre. `start` vuelve a comprobar hardware y habilita los servicios tras verificar el primer fotograma.

## 6. Avance y comprobación final

El porcentaje representa etapas, no bytes descargados ni tiempo restante: preparación hasta 5%, entorno/dependencias/configuración hasta 80%, comprobaciones hasta 90% y arranque correcto hasta 100%. En las operaciones largas se informa el tiempo cada 30 segundos sin aumentar artificialmente el porcentaje.

```bash
systemctl is-active gdf-reader.service gdf-heartbeat.service
systemctl is-enabled gdf-reader.service gdf-heartbeat.service
```

Ambos deben indicar `active` y `enabled`, respectivamente. Abrir el monitor, esperar aproximadamente un minuto y actualizar. El equipo se registra cuando el receptor acepta el primer heartbeat; un servicio activo no prueba su entrega. Si falta, comprobar que URL y token se guardaron y que hay conexión.

Después comprobar una placa real: evidencia guardada, respuesta OCR y aceptación por Genyus. Las comprobaciones TLS del instalador no certifican las claves ni una entrega real. No volver a ejecutar el lector anterior en paralelo.

La limpieza automática permanece desactivada. Las fotos históricas no se eliminan. El sistema no tiene una cola persistente que garantice reprocesar y reenviar eventos tras un corte de internet.

## 7. Corregir credenciales o pedir ayuda

Reabrir la ventana sin reinstalar:

```bash
sudo python3 /opt/gdf/deploy/pi_installer.py configure
```

Tras guardar cambios, reiniciar los servicios afectados. Si solo cambió el monitor:

```bash
sudo systemctl restart gdf-heartbeat.service
```

Si cambiaron las claves de Azure o Genyus, reiniciar ambos servicios en un momento acordado:

```bash
sudo systemctl restart gdf-reader.service gdf-heartbeat.service
```

Si se edita un archivo en nano: **Ctrl+O**, **Enter**, **Ctrl+X** para guardar y salir.

Cada comando imprime `REPORT=...json`. Conservar ese reporte y el paso que falló; no repetir `install` sobre una instalación parcial. El lanzador guarda reportes en `gdf-reports` dentro del paquete. La alternativa manual los guarda en la carpeta actual, salvo que se indique `--report-dir`.

Repositorio: https://github.com/AlfCasBenMx/GSOTF

Versión de estos pasos: https://github.com/AlfCasBenMx/GSOTF/tree/fixes/runtime-reliability

## Panel local de camara y lecturas

El paquete actualizado abre el panel en el navegador de la Raspberry: http://127.0.0.1:8765/. Muestra la captura reducida y las ultimas cinco placas distintas de la sesion. Se puede ver mediante AnyDesk. Ver [PANEL_LOCAL.md](PANEL_LOCAL.md) para recursos, arranque y limites. Es independiente del monitor publico de salud.
