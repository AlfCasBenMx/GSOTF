#!/bin/bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
report_dir="${package_dir}/gdf-reports"
installer="${package_dir}/deploy/pi_installer.py"

finish() {
    result=$?
    if [ "$result" -eq 0 ]; then
        printf '\nProceso terminado correctamente.\n'
    else
        printf '\nLa instalacion se detuvo. Codigo: %s\n' "$result"
    fi
    printf 'Reportes: %s\n' "$report_dir"
    if [ -t 0 ]; then
        read -r -p 'Pulsa Enter para cerrar esta ventana...' || true
    fi
}
trap finish EXIT
printf 'LIPER - Instalacion en Raspberry Pi\n\n'
python3 "$installer" preflight --report-dir "$report_dir"
if [ "${1:-}" = '--check-only' ]; then
    exit 0
fi
if [ "$(id -u)" -eq 0 ]; then
    printf 'Abre este acceso desde el usuario normal del escritorio.\n'
    exit 1
fi
service_user="$(id -un)"
printf '\nSe solicitara la contrasena del usuario para instalar.\n'
sudo -v
sudo python3 "$installer" install --user "$service_user" --report-dir "$report_dir"
printf '\nComprobando configuracion, modelo y camara...\n'
sudo python3 /opt/gdf/deploy/pi_installer.py check --hardware --report-dir "$report_dir"
printf '\nArrancando lector y heartbeat...\n'
sudo python3 /opt/gdf/deploy/pi_installer.py start --report-dir "$report_dir"
printf '\nServicios instalados y habilitados. Revisar una lectura real cuando pase un vehiculo.\n'

# Launch in the existing graphical session, never from the system service.
if [ -n "${DISPLAY:-}" ]; then
    python3 /opt/gdf/deploy/open_dashboard.py >/dev/null 2>&1 &
fi
