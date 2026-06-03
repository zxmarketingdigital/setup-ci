#!/usr/bin/env bash
# add-colaborador.sh — convida o colaborador (conta GitHub própria dele) como
# colaborador com permissão "write" nos repos de Setup do ZX Control.
#
# Por que "write" é seguro aqui: a branch protection impede push direto na main,
# o colaborador NÃO pode aprovar o próprio PR, e o único voto que conta é o do
# code owner (@zxmarketingdigital). Ou seja: ele propõe, só o Rafael publica.
#
# Uso:
#   ./add-colaborador.sh HANDLE_DO_COLABORADOR
#   ./add-colaborador.sh HANDLE repo1 repo2   # repos específicos
#
# Sem repos: aplica ao template + todos os repos cujo nome começa com
# "zx-control-setup". O colaborador recebe um convite por email pra aceitar.
set -euo pipefail

HANDLE="${1:?Uso: ./add-colaborador.sh handle-do-colaborador [repos...]}"
shift || true
ORG="zxmarketingdigital"

if [ "$#" -gt 0 ]; then
  REPOS=("$@")
else
  # template + todos os zx-control-setup*
  mapfile -t REPOS < <(gh repo list "$ORG" --limit 200 --json name -q '.[].name' \
    | grep -E '^(zx-control-setup|zx-control-setup-template)' || true)
  REPOS+=("zx-control-setup-template")
fi

echo "Convidando @$HANDLE (permissão write) para:"
for r in $(printf '%s\n' "${REPOS[@]}" | sort -u); do
  if gh api "repos/$ORG/$r/collaborators/$HANDLE" -X PUT -f permission=push >/dev/null 2>&1; then
    echo "  ✓ $r"
  else
    echo "  ⚠ $r (falhou — repo existe? handle correto?)"
  fi
done
echo ""
echo "Pronto. Avise @$HANDLE pra aceitar o convite no email/GitHub."
echo "A branch protection garante: ele abre PR, mas só você (@$ORG) aprova e mergeia."
