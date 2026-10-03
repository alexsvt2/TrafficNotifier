# TrafficNotifier

Revisa el tráfico de tus rutas cada 30 min (de 07:00 a 22:00, configurable) con Google Routes API y te manda un push al celular con [ntfy](https://ntfy.sh). También puedes pedir una revisión al momento mandando `revisar` desde la app de ntfy, y pausar o reanudar las automáticas con `detener` e `iniciar`.

```
Tráfico 08:30
🔴 Casa → Trabajo
42 min · +14 min de lo normal · 18 km
🟢 Trabajo → Casa
27 min · +1 min de lo normal · 18 km
– – – – – – – – – –
🟡 Casa → Escuela
15 min · +3 min de lo normal · 6 km
```

Cada ruta va junto a su regreso (la siguiente ruta de `config.toml`, si es la misma al revés) y los grupos se separan con una línea de guiones. Si una ruta falla, sale con ⚠️ y las demás se revisan igual.

Requiere Python 3.11+ (usa `/opt/homebrew/bin/python3.13`) y solo la librería estándar.

## Configuración

### 1. API key de Google
1. En [Google Cloud Console](https://console.cloud.google.com/), crea un proyecto y activa la facturación.
2. Habilita **Routes API** y **Maps Static API** (APIs y servicios → Biblioteca).
3. Crea una API key (APIs y servicios → Credenciales) y **restríngela a esas dos APIs**.
4. Recomendado: crea una alerta de presupuesto (Facturación → Presupuestos y alertas), por ejemplo de $1.
5. Recomendado: baja las cuotas (APIs y servicios → la API → Cuotas) para que un error no pueda gastar de más. La alerta de presupuesto solo avisa; las cuotas sí cortan. Con 4 rutas cada 20 min alcanza con ~350 consultas al día en Routes API (o 20 por minuto, si no hay cuota diaria) y 100 al día en Maps Static API.

Costo: cada revisión es una petición por ruta. Las peticiones con tráfico cuentan como *Compute Routes Pro*, que trae unas 5,000 gratis al mes. De 07:00 a 22:00, cada 30 min son unas 930 al mes por ruta (hasta ~5 rutas gratis); cada 20 min, unas 1,400 por ruta (~3 rutas gratis). Las revisiones a demanda se suman a eso.

El mapa de tráfico (ver abajo) suma, por cada ruta en 🔴 y como máximo una vez por hora, una petición *Compute Routes Enterprise* (1,000 gratis al mes, luego 15 USD por 1,000) y una imagen de *Static Maps* (10,000 gratis al mes).

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

### Mapa y botones
Cada notificación trae un botón **🗺️** por grupo de rutas (ida y vuelta) que abre la ruta en Google Maps, donde se ven accidentes y cierres.

Cuando alguna ruta sale en 🔴, la notificación adjunta un mapa con esas rutas: en naranja los tramos lentos y en rojo los atascos. Para no gastar de más, cada ruta sale en imagen como máximo una vez cada `[map] every_minutes` (60 por defecto); `enabled = false` lo apaga. La imagen se descarga de Google en la Mac y se sube a ntfy como archivo, así que la API key nunca llega al topic. En ntfy.sh los adjuntos se borran a las ~3 horas.

### Revisar a demanda
En la app de ntfy, abre tu topic y manda `revisar` (no importan mayúsculas). En unos segundos llega la notificación, incluso fuera de horario, y la siguiente revisión automática se recorre: si pides una a las 08:10 con intervalo de 30 min, la próxima llega a las 08:40.

Si la última revisión fue hace menos de `cooldown_minutes` (2 por defecto), no consulta a Google y responde cuánto falta. El texto, el cooldown y el intervalo se cambian en `config.toml` (`[command]` y `[schedule] interval_minutes`).

Cualquiera que conozca el topic puede mandar `revisar`; el cooldown limita cuántas peticiones a Google puede provocar.

### Detener e iniciar
Manda `detener` para pausar las revisiones automáticas (por ejemplo, un día que no vas a salir). La pausa termina sola al día siguiente, a la hora de inicio del horario (`[schedule] start`); para reanudar antes, manda `iniciar`.

Mientras está en pausa, dentro del horario llega un recordatorio cada `reminder_minutes` (60 por defecto) de que el proceso sigue conectado y cómo reactivarlo. `revisar` sigue funcionando en pausa. La pausa se guarda en `state.json`, así que sobrevive a un reinicio de la Mac. Los textos y el intervalo del recordatorio se cambian en `[command]` (`stop`, `start`, `reminder_minutes`).

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
