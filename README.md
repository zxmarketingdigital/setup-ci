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

## Perfil nicho-dod (opt-in)

Para repos de **produto de nicho** (Clínica Cheia, Corretor ZX Control, etc.) existe um
perfil extra com regras de **DoD (Definition of Done)** das entregas comerciais.

**Como ativar:** crie `.setup-ci.json` na raiz do repo do produto:

```json
{"perfil": "nicho-dod"}
```

> **Repos sem o arquivo não são afetados** — o comportamento segue 100% idêntico ao
> validador original. Os setups existentes que usam `@v1` continuam passando como antes.

Regras adicionais (todas bloqueiam):

| # | Regra |
|---|-------|
| N1 | `docs/apresentacao.html` existe, com link `github.com/zxmarketingdigital/` e instrução de colar no Claude na seção de instalação |
| N2 | `docs/proposta.html` existe e contém `R$` (precificação preenchida) |
| N3 | `demo/server.mjs` e `demo/data.mjs` existem e passam `node --check` |
| N4 | `painel/style.css` contém os tokens do design system ZX: `#0D0D0D`, `#D97706` e `JetBrains Mono` |
| N5 | `painel/index.html` tem pelo menos 2 botões de cadastro (`+ Novo`, `+ Agendar`, `+ Adicionar`, `+ Cadastrar`) |
| N6 | Nenhum placeholder `{{` em `.html/.md/.mjs/.js` dentro de `docs/`, `painel/` e `demo/` (template não renderizado) |

`.setup-ci.json` inválido (JSON quebrado) também bloqueia, com mensagem clara — pra
não falhar silencioso achando que o perfil está ativo.

## Rodar localmente (antes de abrir o PR)

```bash
python3 validate.py --path .
```

Não tem dependências — só Python 3.9+ da biblioteca padrão.

Smoke test do validador (dois modos, com e sem perfil):

```bash
python3 tests/smoke_nicho_dod.py
```

---
_Mantido por ZX LAB. Para mudar uma regra, edite `validate.py` e suba a tag `v1`._
