# TrafficNotifier

Revisa el tráfico de tus rutas cada 30 min (de 07:00 a 22:00, configurable) con Google Routes API y te manda un push al celular con [ntfy](https://ntfy.sh). También puedes pedir una revisión al momento mandando `revisar` desde la app de ntfy.

```
Tráfico 08:30
Casa → Trabajo 🔴 42 min (normal 28, +14) · 18 km
Trabajo → Casa 🟢 27 min (normal 26, +1) · 18 km
```

Requiere Python 3.11+ (usa `/opt/homebrew/bin/python3.13`) y solo la librería estándar.

## Configuración

### 1. API key de Google
1. En [Google Cloud Console](https://console.cloud.google.com/), crea un proyecto y activa la facturación.
2. Habilita **Routes API** (APIs y servicios → Biblioteca).
3. Crea una API key (APIs y servicios → Credenciales) y **restríngela a Routes API**.
4. Recomendado: crea una alerta de presupuesto (Facturación → Presupuestos y alertas), por ejemplo de $1.

Costo: cada revisión es una petición por ruta. Las peticiones con tráfico cuentan como *Compute Routes Pro*, que trae unas 5,000 gratis al mes. De 07:00 a 22:00, cada 30 min son unas 930 al mes por ruta (hasta ~5 rutas gratis); cada 20 min, unas 1,400 por ruta (~3 rutas gratis). Las revisiones a demanda se suman a eso.

### 2. ntfy
Instala la app **ntfy** (iOS o Android) y suscríbete a un topic con un nombre difícil de adivinar, por ejemplo `alexis-trafico-x7k2p9`. Los topics de ntfy.sh son públicos: cualquiera que conozca el nombre puede leerlos.

### 3. config.toml
```bash
cp config.example.toml config.toml
```
Pon tu API key, el topic y tus rutas. Origen y destino aceptan una dirección en texto o `lat,lng`; para sacar las coordenadas, haz clic derecho en Google Maps sobre el punto.

## Uso
```bash
PY=/opt/homebrew/bin/python3.13
$PY -m traffic_notifier test-notify     # push de prueba
$PY -m traffic_notifier check --force   # revisar ya, ignorando el horario
$PY -m traffic_notifier serve           # lo que ejecuta launchd (queda corriendo; Ctrl+C para salir)
```

### Revisar a demanda
En la app de ntfy, abre tu topic y manda `revisar` (no importan mayúsculas). En unos segundos llega la notificación, incluso fuera de horario, y la siguiente revisión automática se recorre: si pides una a las 08:10 con intervalo de 30 min, la próxima llega a las 08:40.

Si la última revisión fue hace menos de `cooldown_minutes` (2 por defecto), no consulta a Google y responde cuánto falta. El texto, el cooldown y el intervalo se cambian en `config.toml` (`[command]` y `[schedule] interval_minutes`).

Cualquiera que conozca el topic puede mandar `revisar`; el cooldown limita cuántas peticiones a Google puede provocar.

### Ejecución automática (launchd)
```bash
./scripts/install.sh                                              # instala y deja corriendo
launchctl kickstart -k gui/$UID/com.alexislopez.trafficnotifier   # reiniciar el proceso
tail -f ~/Library/Logs/TrafficNotifier.log                         # ver el log
./scripts/uninstall.sh                                            # quitarla
```
El proceso queda corriendo y launchd lo relanza si se cae. Si mueves la carpeta del proyecto, vuelve a ejecutar `install.sh`. Los cambios en `config.toml` se aplican solos en menos de un minuto, salvo el topic y el servidor de ntfy, que requieren reiniciar el proceso.

## Tests
```bash
/opt/homebrew/bin/python3.13 -m unittest discover tests
```
