#!/bin/zsh

set -u

AIHUB="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$AIHUB/00-System/Config/knowledge_sources.conf"

source "$CONFIG"

echo ""
echo "=============================="
echo "KNOWLEDGE DISCOVERY"
echo "=============================="

inventory() {

    NAME="$1"
    ROOT="$2"

    echo ""
    echo "===== $NAME ====="

    echo ""
    echo "Tamaño total"

    du -sh "$ROOT"

    echo ""
    echo "Top 20 extensiones"

    find "$ROOT" -type f \
        | awk -F. '
            NF>1 {
                ext=tolower($NF)
                count[ext]++
            }
            END{
                for(i in count)
                    print count[i],i
            }' \
        | sort -rn \
        | head -20

    echo ""
    echo "Solo documentos"

    find "$ROOT" \
        \( \
            -iname "*.pdf" \
            -o -iname "*.docx" \
            -o -iname "*.pptx" \
            -o -iname "*.xlsx" \
            -o -iname "*.md" \
            -o -iname "*.txt" \
            -o -iname "*.csv" \
            -o -iname "*.json" \
            -o -iname "*.yaml" \
            -o -iname "*.sql" \
            -o -iname "*.py" \
        \) \
        -print0 \
        | du -ch --files0-from=- \
        | tail -1
}

inventory "Portfolio" "$PORTFOLIO_SOURCE"

inventory "Proposals" "$PROPOSALS_SOURCE"

inventory "Projects" "$PROJECTS_SOURCE"

inventory "Marketing" "$MARKETING_SOURCE"
