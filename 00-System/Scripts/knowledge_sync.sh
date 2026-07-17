#!/bin/zsh

set -u

AIHUB="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$AIHUB/00-System/Config/knowledge_sources.conf"
LOG_DIR="$AIHUB/00-System/Logs"
LOG_FILE="$LOG_DIR/knowledge_sync_$(date '+%Y-%m-%d_%H-%M-%S').log"

mkdir -p "$LOG_DIR"

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: No existe el archivo de configuración: $CONFIG"
  exit 1
fi

source "$CONFIG"

DRY_RUN=false

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
fi

sync_source() {
  local name="$1"
  local source="$2"
  local destination="$3"

  echo ""
  echo "========================================"
  echo "Fuente:  $name"
  echo "Origen:  $source"
  echo "Destino: $destination"
  echo "========================================"

  if [ ! -d "$source" ]; then
    echo "ERROR: No existe la fuente: $source"
    return 1
  fi

  mkdir -p "$destination"

local options=(

  -a

  -v

  --update

  --itemize-changes

  --prune-empty-dirs

  # Permitir recorrer todas las carpetas

  --include="*/"

  # Documentos Office

  --include="*.[dD][oO][cC]"

  --include="*.[dD][oO][cC][xX]"

  --include="*.[xX][lL][sS]"

  --include="*.[xX][lL][sS][xX]"

  --include="*.[xX][lL][sS][mM]"

  --include="*.[pP][pP][tT]"

  --include="*.[pP][pP][tT][xX]"

  # Documentos y texto

  --include="*.[pP][dD][fF]"

  --include="*.[tT][xX][tT]"

  --include="*.[mM][dD]"

  --include="*.[rR][tT][fF]"

  --include="*.[hH][tT][mM]"

  --include="*.[hH][tT][mM][lL]"

  # Datos estructurados

  --include="*.[cC][sS][vV]"

  --include="*.[tT][sS][vV]"

  --include="*.[jJ][sS][oO][nN]"

  --include="*.[yY][aA][mM][lL]"

  --include="*.[yY][mM][lL]"

  --include="*.[xX][mM][lL]"

  --include="*.[pP][aA][rR][qQ][uU][eE][tT]"

  # Código y analítica

  --include="*.[sS][qQ][lL]"

  --include="*.[pP][yY]"

  --include="*.[rR]"

  --include="*.[sS][cC][aA][lL][aA]"

  --include="*.[jJ][aA][vV][aA]"

  --include="*.[jJ][sS]"

  --include="*.[tT][sS]"

  --include="*.[sS][hH]"

  --include="*.[iI][pP][yY][nN][bB]"

  # Diagramas editables

  --include="*.[dD][rR][aA][wW][iI][oO]"

  --include="*.[vV][sS][dD][xX]"

  # Correos exportados

  --include="*.[eE][mM][lL]"

  --include="*.[mM][sS][gG]"

  # Excluir cualquier otro archivo

  --exclude="*"

)

  if [ "$DRY_RUN" = true ]; then
    options+=(--dry-run)
  fi

  rsync "${options[@]}" "$source/" "$destination/"
}

{
  echo "Inicio: $(date)"
  echo "AI Hub: $AIHUB"
  echo "Modo simulación: $DRY_RUN"

  sync_source \
    "Portafolio" \
    "$PORTFOLIO_SOURCE" \
    "$AIHUB/01-Ingestion/OneDrive-Portfolio"

  sync_source \
    "Propuestas" \
    "$PROPOSALS_SOURCE" \
    "$AIHUB/01-Ingestion/OneDrive-Proposals"

  #sync_source \
  #  "Proyectos" \
  #  "$PROJECTS_SOURCE" \
  #  "$AIHUB/01-Ingestion/OneDrive-Projects"

  sync_source \
    "Marketing" \
    "$MARKETING_SOURCE" \
    "$AIHUB/01-Ingestion/OneDrive-Marketing"

  echo ""
  echo "Fin: $(date)"
} 2>&1 | tee "$LOG_FILE"

echo ""
echo "Log generado en:"
echo "$LOG_FILE"


