#!/usr/bin/env bash
# Levanta el panel del inventario en local con una base SQLite temporal y datos de ejemplo.
# Uso:  bash levantar_panel.sh          -> inicia en http://127.0.0.1:${PANEL_PORT:-5055}
#       bash levantar_panel.sh stop     -> detiene el servidor
set -euo pipefail

RAIZ="$(git rev-parse --show-toplevel)"
DIR="$RAIZ/.claude/skills/revisar-panel"
PUERTO="${PANEL_PORT:-5055}"
PIDFILE="$DIR/.panel.pid"
DB="$DIR/.panel.db"

if [[ "${1:-}" == "stop" ]]; then
  if [[ -f "$PIDFILE" ]]; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; fi
  echo "Panel detenido."
  exit 0
fi

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "El panel ya está corriendo en http://127.0.0.1:$PUERTO"
  exit 0
fi

python -c "import flask, sqlalchemy" 2>/dev/null || {
  echo "Faltan dependencias. Instala con: pip install -r inventory-service/requirements.txt" >&2; exit 1; }

rm -f "$DB"
cd "$RAIZ/inventory-service"
DATABASE_URL="sqlite:///$DB" HOST=127.0.0.1 PORT="$PUERTO" nohup python app.py >"$DIR/.panel.log" 2>&1 &
echo $! > "$PIDFILE"

for _ in $(seq 1 40); do
  if curl -fs "http://127.0.0.1:$PUERTO/api/usuarios" >/dev/null 2>&1; then
    echo "Panel listo en http://127.0.0.1:$PUERTO (log: $DIR/.panel.log)"
    exit 0
  fi
  sleep 0.5
done
echo "El panel no respondió. Revisa $DIR/.panel.log" >&2
exit 1
