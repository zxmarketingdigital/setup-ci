#!/usr/bin/env bash
# retrofit-existentes.sh — aplica CI + proteção + colaborador a setups que JÁ existem.
#
# Diferença pro bootstrap (repos novos): aqui o CI é INFORMATIVO (não obrigatório),
# porque setups antigos podem ter violações pré-existentes que travariam todo PR.
# O Rafael continua sendo o gate do merge (1 aprovação obrigatória).
#
# Por repo: commita CODEOWNERS + workflow de CI, aplica branch protection
# (PR + 1 aprovação + code owner + sem force-push), liga secret scanning,
# deixa Actions read-only, e adiciona os colaboradores cadastrados.
#
# Uso:
#   ./retrofit-existentes.sh repo1 [repo2 ...]
set -euo pipefail

ORG="zxmarketingdigital"
CFG="$HOME/.zxlab-mission-control/colaboradores-setup.txt"
[ "$#" -ge 1 ] || { echo "Uso: ./retrofit-existentes.sh repo1 [repo2 ...]"; exit 1; }

CODEOWNERS_CONTENT='# Todo PR precisa da aprovação do dono (@zxmarketingdigital) antes do merge.
* @zxmarketingdigital
/.github/ @zxmarketingdigital
'
PRYML_CONTENT='name: Validar Setup
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  validar:
    runs-on: ubuntu-latest
    steps:
      - uses: zxmarketingdigital/setup-ci@v1
'

put_file() {  # repo path content msg
  local repo="$1" path="$2" content="$3" msg="$4"
  local b64 sha
  b64=$(printf '%s' "$content" | base64)
  sha=$(gh api "repos/$ORG/$repo/contents/$path" -q .sha 2>/dev/null || echo "")
  if [ -n "$sha" ]; then
    gh api "repos/$ORG/$repo/contents/$path" -X PUT -f message="$msg" \
      -f content="$b64" -f sha="$sha" >/dev/null && echo "    ~ $path (atualizado)"
  else
    gh api "repos/$ORG/$repo/contents/$path" -X PUT -f message="$msg" \
      -f content="$b64" >/dev/null && echo "    + $path (criado)"
  fi
}

protect() {  # repo  — branch protection SEM required status check
  cat <<'JSON' | gh api "repos/$ORG/$1/branches/main/protection" -X PUT --input - >/dev/null
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
}

# colaboradores cadastrados
HANDLES=()
[ -f "$CFG" ] && while IFS= read -r line; do
  line="$(echo "$line" | tr -d '[:space:]')"
  [ -n "$line" ] && [ "${line:0:1}" != "#" ] && HANDLES+=("$line")
done < "$CFG"

for repo in "$@"; do
  echo "==> $repo"
  put_file "$repo" "CODEOWNERS" "$CODEOWNERS_CONTENT" "chore: CODEOWNERS (dono aprova PRs)"
  put_file "$repo" ".github/workflows/pr.yml" "$PRYML_CONTENT" "ci: validar setup em PR (informativo)"
  protect "$repo" && echo "    ✓ branch protection (PR + 1 aprovação, sem travar CI)"
  gh api "repos/$ORG/$repo" -X PATCH \
    -f 'security_and_analysis[secret_scanning][status]=enabled' \
    -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' >/dev/null 2>&1 \
    && echo "    ✓ secret scanning + push protection" || echo "    ⚠ secret scanning (ajuste manual?)"
  gh api "repos/$ORG/$repo/actions/permissions/workflow" -X PUT \
    -f 'default_workflow_permissions=read' -F 'can_approve_pull_request_reviews=false' >/dev/null 2>&1 \
    && echo "    ✓ Actions read-only" || true
  for h in "${HANDLES[@]}"; do
    gh api "repos/$ORG/$repo/collaborators/$h" -X PUT -f permission=push >/dev/null 2>&1 \
      && echo "    ✓ colaborador @$h (write)" || echo "    ⚠ falha @$h"
  done
done
echo ""
echo "Retrofit concluído."
