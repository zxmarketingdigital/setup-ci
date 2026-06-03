#!/usr/bin/env bash
# novo-setup.sh — cria um Setup novo do ZERO, já protegido e com o colaborador dentro.
#
# Faz TUDO num comando:
#   1. cria o repo a partir do template (zx-control-setup-template)
#   2. aplica as proteções (branch protection + secret scanning + Actions read-only)
#   3. convida os colaboradores (lidos de ~/.zxlab-mission-control/colaboradores-setup.txt
#      + qualquer handle passado como argumento)
#
# Uso:
#   ./novo-setup.sh 10 agente-instagram
#   ./novo-setup.sh 10 agente-instagram handle-extra-do-colab
#
# Cadastre os colaboradores fixos UMA vez (um handle por linha):
#   echo "handle-do-colaborador" >> ~/.zxlab-mission-control/colaboradores-setup.txt
set -euo pipefail

N="${1:?Uso: ./novo-setup.sh <numero> <slug> [handles-extra...]}"
SLUG="${2:?Uso: ./novo-setup.sh <numero> <slug> [handles-extra...]}"
shift 2 || true

ORG="zxmarketingdigital"
REPO="zx-control-setup${N}-${SLUG}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="$HOME/.zxlab-mission-control/colaboradores-setup.txt"

echo "==> 1/3 Criando $ORG/$REPO a partir do template..."
gh repo create "$ORG/$REPO" \
  --template "$ORG/zx-control-setup-template" \
  --public \
  --description "ZX Control Setup ${N}: ${SLUG}"
sleep 4  # GitHub leva alguns segundos pra popular o repo do template

echo "==> 2/3 Aplicando proteções..."
"$DIR/bootstrap-protections.sh" "$ORG/$REPO"

echo "==> 3/3 Convidando colaboradores..."
HANDLES=()
[ -f "$CFG" ] && while IFS= read -r line; do
  line="$(echo "$line" | tr -d '[:space:]')"
  [ -n "$line" ] && [ "${line:0:1}" != "#" ] && HANDLES+=("$line")
done < "$CFG"
HANDLES+=("$@")

if [ "${#HANDLES[@]}" -eq 0 ]; then
  echo "  (nenhum colaborador cadastrado — cadastre em $CFG ou passe como argumento)"
else
  for h in "${HANDLES[@]}"; do
    [ -z "$h" ] && continue
    if gh api "repos/$ORG/$REPO/collaborators/$h" -X PUT -f permission=push >/dev/null 2>&1; then
      echo "  ✓ @$h convidado (write)"
    else
      echo "  ⚠ falha ao convidar @$h"
    fi
  done
fi

echo ""
echo "✅ Setup ${N} pronto: https://github.com/$ORG/$REPO"
echo "   Mande esse link pro colaborador abrir no claude.ai/code."
