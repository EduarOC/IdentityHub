#!/usr/bin/env bash
# Verificación local antes de subir un cambio de IdentityHub.
# Falla si la rama es main, si fallan las pruebas o si la cobertura total baja de la meta.
set -uo pipefail

META="${COBERTURA_MINIMA:-80}"
RAIZ="$(git rev-parse --show-toplevel)"
cd "$RAIZ"
fallos=0

rama="$(git branch --show-current)"
if [[ "$rama" == "main" || -z "$rama" ]]; then
  echo "✗ Estás en '${rama:-HEAD separado}'. Crea una rama antes de seguir (GitHub Flow)."
  exit 1
fi
echo "✓ Rama: $rama"

echo "… Ejecutando pruebas con cobertura"
salida="$(python -m pytest --cov --cov-config=.coveragerc -q -p no:cacheprovider 2>&1)"
codigo=$?
echo "$salida" | grep -E '^(TOTAL|[a-z-]+/.*\.py)|passed|failed|error' | sed 's/^/  /'
if [[ $codigo -ne 0 ]]; then
  echo "✗ Las pruebas fallaron."; fallos=1
fi
total="$(echo "$salida" | awk '/^TOTAL/ {gsub("%","",$NF); print $NF}')"
if [[ -n "$total" && "$total" -lt "$META" ]]; then
  echo "✗ Cobertura total ${total}% por debajo de la meta (${META}%)."; fallos=1
elif [[ -n "$total" ]]; then
  echo "✓ Cobertura total ${total}% (meta ${META}%)"
fi

git fetch -q origin main 2>/dev/null || true
base="$(git merge-base HEAD origin/main 2>/dev/null || echo origin/main)"
diff="$(git diff "$base" -- . ':(exclude).claude/skills/**' ':(exclude)**/tests/**' ':(exclude)*.md' 2>/dev/null | grep '^+' | grep -v '^+++')"

revisar() {  # $1 = descripción, $2 = patrón, $3 = bloquea (1) o solo avisa (0)
  local hallazgos
  hallazgos="$(echo "$diff" | grep -inE "$2" | head -5)"
  if [[ -n "$hallazgos" ]]; then
    if [[ "$3" == "1" ]]; then echo "✗ $1:"; fallos=1; else echo "⚠ $1:"; fi
    echo "$hallazgos" | sed 's/^/    /'
  fi
}
revisar "Posible secreto escrito en el código" '(password|passwd|secret|token|api[_-]?key)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"'$]{6,}' 1
revisar "Llave privada en el diff" 'BEGIN [A-Z ]*PRIVATE KEY' 1
revisar "Verificación TLS desactivada" 'verify[[:space:]]*=[[:space:]]*False' 1
revisar "Modo debug activado" 'debug[[:space:]]*=[[:space:]]*True' 1
revisar "innerHTML nuevo (escapa los datos del servidor)" 'innerHTML' 0
revisar "Rutas nuevas: pásalas por la skill ruta-segura-inventario" '@app\.route' 0
revisar "Borrado de datos (¿toca la auditoría?)" '\.delete\(\)|DELETE FROM|drop_all' 0

if [[ $fallos -ne 0 ]]; then
  echo; echo "Verificación con fallos: corrige lo marcado con ✗ antes de subir."; exit 1
fi
echo; echo "Verificación local correcta. Sube la rama y abre el PR."
