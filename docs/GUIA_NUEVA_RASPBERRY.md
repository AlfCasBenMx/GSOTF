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
