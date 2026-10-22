#!/usr/bin/env bash
# Publica docs/wiki/ en la Wiki de GitHub del repositorio (E2-M9b).
#
# Clona https://github.com/tsepulvedf/Finty.wiki.git en una carpeta temporal,
# reemplaza su contenido por el de docs/wiki/ y hace un commit. Solo empuja si se
# pasa --push; sin el, deja el commit en la carpeta temporal para revisarlo.
#
#   bash tools/publish-wiki.sh            # prepara el commit y muestra el resumen
#   bash tools/publish-wiki.sh --push     # ademas lo empuja a la Wiki
#
# Requisitos: git con credenciales para el repositorio, y la Wiki ya creada
# (GitHub solo crea Finty.wiki.git despues de guardar la primera pagina desde la
# interfaz web). Antes de publicar, corre las verificaciones:
#   python tools/check_wiki_links.py && (cd tools/mermaid && node check-mermaid.mjs)
set -euo pipefail

WIKI_URL="${WIKI_URL:-https://github.com/tsepulvedf/Finty.wiki.git}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$ROOT/docs/wiki"
PUSH=0
[ "${1:-}" = "--push" ] && PUSH=1

WORK="$(mktemp -d)"
trap 'if [ "$PUSH" = 1 ]; then rm -rf "$WORK"; fi' EXIT

git clone --quiet "$WIKI_URL" "$WORK/wiki"
cd "$WORK/wiki"

# La Wiki es un espejo de docs/wiki/: lo que se borro alla tambien se borra aca.
git ls-files -z '*.md' | xargs -0 -r git rm --quiet
cp "$SOURCE"/*.md .
git add -A

if git diff --cached --quiet; then
  echo "La Wiki ya esta al dia con docs/wiki/."
  exit 0
fi

COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"
git commit --quiet -m "docs(wiki): publicar docs/wiki/ desde $COMMIT"
git show --stat --oneline HEAD

if [ "$PUSH" = 1 ]; then
  git push --quiet origin HEAD
  echo "Publicada en ${WIKI_URL%.git}"
else
  echo "Commit listo en $WORK/wiki (sin empujar). Repite con --push para publicar."
fi
