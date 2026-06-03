# setup-ci — Validador central dos Setups ZX Control

GitHub Action reutilizável que valida qualquer repo de **Setup do ZX Control** contra as
**12 regras invioláveis** — sem precisar da máquina do Rafael, sem credenciais, sem segredos.

É a **fonte única de verdade** das regras: quando uma regra muda, muda aqui (uma vez), e
todos os repos de setup que usam `@v1` herdam automaticamente no próximo Pull Request.

## O que ele checa

| # | Regra | Severidade |
|---|-------|------------|
| 1 | Sem `X \| None` (type union Python 3.10+) | bloqueia |
| 2 | Sem `match/case` (Python 3.10+) | bloqueia |
| 3 | Sem `fetch()` em `docs/` (quebra dashboard em `file://`) | bloqueia |
| 4 | Sem secret hardcoded | bloqueia |
| 5 | Sem `open("~/...")` (Python não expande `~`) | bloqueia |
| 6 | Sem `product_name ILIKE` (filtro de cohort frágil) | bloqueia |
| 7 | `install.sh` sem `rm -rf $DIR` (apaga dados do aluno) | bloqueia |
| 8 | Sem vazamento de infra interna do Rafael | bloqueia |
| 9 | Sintaxe Python 3.9 válida (AST) em todo `.py` | bloqueia |
| 10 | Estrutura mínima (README, CLAUDE.md, MASTERCLASS.md, setup/check_prerequisites.py) | bloqueia |
| 11 | `.env` nunca commitado no histórico git | bloqueia |

## Como usar num repo de setup

Crie `.github/workflows/pr.yml` no repo do setup:

```yaml
name: Validar Setup
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
```

Pronto. Todo PR roda os 11 checks e fica vermelho se algo violar uma regra.

## Rodar localmente (antes de abrir o PR)

```bash
python3 validate.py --path .
```

Não tem dependências — só Python 3.9+ da biblioteca padrão.

---
_Mantido por ZX LAB. Para mudar uma regra, edite `validate.py` e suba a tag `v1`._
