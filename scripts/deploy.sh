#!/bin/zsh
# Despliega este repo (código fuente) a la copia instalada en el disco interno
# y reinicia el servicio y la app de barra de menú desde ahí.
#
# Por qué existe: macOS no deja que un servicio de launchd lea volúmenes
# externos, así que el servicio no puede correr directo desde el repo si este
# vive en un SSD externo. El repo es la fuente; la copia instalada es la que corre.
#
# Uso: scripts/deploy.sh            (destino por defecto)
#      DEST=/otra/ruta scripts/deploy.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${DEST:-$HOME/Library/Application Support/TrafficNotifier}"

[[ -f "$REPO/config.toml" ]] || { echo "Falta $REPO/config.toml (copia config.example.toml)"; exit 1; }
[[ "$REPO" != "$DEST" ]] || { echo "El repo y el destino son la misma carpeta"; exit 1; }

mkdir -p "$DEST"
# state.json es la memoria del servicio en ejecución: no se pisa ni se borra.
rsync -a --delete \
    --exclude .git --exclude tests --exclude state.json \
    --exclude .DS_Store --exclude __pycache__ \
    "$REPO/" "$DEST/"

# install.sh hace bootout y bootstrap seguidos; si el servicio aún se está
# apagando, el bootstrap falla ("Input/output error"). Se detiene aquí y se
# espera a que launchd lo suelte antes de reinstalar.
LABEL="com.alexislopez.trafficnotifier"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
for _ in {1..20}; do
    launchctl print "gui/$UID/$LABEL" &>/dev/null || break
    sleep 0.5
done

"$DEST/scripts/install.sh"
"$DEST/scripts/build-app.sh"

pkill -x TrafficNotifier 2>/dev/null || true
open "${APP_DIR:-$HOME/Applications}/TrafficNotifier.app"
echo "Desplegado desde $REPO a $DEST"
