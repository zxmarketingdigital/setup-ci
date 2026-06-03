#!/usr/bin/env bash
# bootstrap-protections.sh — aplica as proteções de segurança a um repo de Setup novo.
#
# "Use this template" copia os ARQUIVOS (inclusive o CI), mas NÃO copia branch
# protection nem secret scanning (isso é configuração do repo, não arquivo).
# Rode este script UMA VEZ em cada setup novo, logo depois de criá-lo.
#
# Uso:
#   ./bootstrap-protections.sh zxmarketingdigital/zx-control-setup10-meu-tema
#
# Requer: gh autenticado com admin no repo (você é admin dos repos que cria).
set -euo pipefail

R="${1:?Uso: ./bootstrap-protections.sh org/nome-do-repo}"

echo "==> Garantindo repositório PÚBLICO (regra inviolável #1)..."
vis=$(gh repo view "$R" --json visibility -q .visibility)
if [ "$vis" != "PUBLIC" ]; then
  gh repo edit "$R" --visibility public --accept-visibility-change-consequences
fi

echo "==> Ativando secret scanning + push protection..."
gh api "repos/$R" -X PATCH \
  -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' \
  -q '.security_and_analysis.secret_scanning_push_protection.status' >/dev/null || \
  echo "   (aviso: ajuste manual pode ser necessário no painel)"

echo "==> Aplicando branch protection na main..."
cat <<'JSON' | gh api "repos/$R/branches/main/protection" -X PUT --input - >/dev/null
{
  "required_status_checks": { "strict": true, "contexts": ["validar"] },
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

echo "==> Restringindo Actions a read-only (defesa contra PR malicioso)..."
gh api "repos/$R/actions/permissions/workflow" -X PUT \
  -f 'default_workflow_permissions=read' \
  -F 'can_approve_pull_request_reviews=false' >/dev/null || \
  echo "   (aviso: ajuste manual pode ser necessário)"

echo ""
echo "OK — proteções aplicadas em $R:"
echo "  - repo público"
echo "  - secret scanning + push protection"
echo "  - branch protection: 1 aprovação + code owner + check 'validar' + sem force-push"
echo "  - Actions read-only"
echo ""
echo "LEMBRE: edite o CODEOWNERS do repo trocando @SEU-USUARIO-GITHUB pelo seu handle real."
