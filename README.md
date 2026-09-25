# TrafficNotifier

Revisa el tráfico de tus rutas cada 30 min (de 07:00 a 22:00) con Google Routes API y te manda un push al celular con [ntfy](https://ntfy.sh).

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

Costo: cada revisión es una petición por ruta, unas 930 al mes por ruta. Las peticiones con tráfico cuentan como *Compute Routes Pro*, que trae unas 5,000 gratis al mes, así que hasta unas 5 rutas no cuestan nada.

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
$PY -m traffic_notifier check           # lo que ejecuta launchd
```

### Ejecución automática (launchd)
```bash
./scripts/install.sh                                              # instala y carga la tarea
launchctl kickstart -k gui/$UID/com.alexislopez.trafficnotifier   # forzar una ejecución
tail -f ~/Library/Logs/TrafficNotifier.log                         # ver el log
./scripts/uninstall.sh                                            # quitarla
```
Si mueves la carpeta del proyecto, vuelve a ejecutar `install.sh`. Los cambios en `config.toml` se aplican solos en la siguiente revisión.

## Tests
```bash
/opt/homebrew/bin/python3.13 -m unittest discover tests
```
