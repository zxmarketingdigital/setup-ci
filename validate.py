#!/usr/bin/env python3
"""
validate.py — Validador de Setup ZX Control (standalone, sem dependências externas).

Porta as 12 regras invioláveis (AST Python 3.9 + greps mecânicos) que o pipeline
interno do Rafael roda no sandbox E2E, mas de forma 100% offline sobre o working
tree local — sem clone, sem credenciais, sem acesso à máquina do Rafael.

Uso:
    python3 validate.py            # valida o diretório atual
    python3 validate.py --path .   # idem, explícito
    python3 validate.py --path /caminho/do/repo

Saída: lista de problemas (file:line  regra  severidade  trecho) + exit code.
    exit 0  -> nenhuma falha bloqueante (pode ter warnings)
    exit 1  -> falha bloqueante encontrada (corrija antes de abrir o PR)

Compatível com Python 3.9+ (o próprio código respeita a regra que valida).
"""
import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# --- As 12 regras, em forma de checks mecânicos ----------------------------
# Cada check é genérico: não referencia nenhum ID/credencial/caminho interno.
GREP_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "no_str_pipe_none",
        "desc": "Type union `X | None` é Python 3.10+ — quebra em alunos com Python 3.9.",
        "pattern": r'(?:\b\w+|[\]\)])\s*\|\s*None\b',
        "include": ["*.py"],
        # Comentário e crase dentro de trecho citado são prosa, não código.
        "exclude_lines_with": ["# noqa", "from __future__ import"],
        "skip_comment_lines": True,
        "strip_inline_code": True,
        "severity": "block",
        "fix": "Use Optional[str] (from typing import Optional) ou adicione "
               "`from __future__ import annotations` no topo do arquivo.",
    },
    {
        "id": "no_match_case_python_310",
        "desc": "match/case é Python 3.10+ — quebra em macOS Monterey (3.9).",
        "pattern": r'^\s*match\b[^=:#]+:\s*(?:#.*)?$',
        "include": ["*.py"],
        "exclude_lines_with": ["from __future__ import", "# noqa"],
        "severity": "block",
        "fix": "Troque match/case por if/elif.",
    },
    {
        "id": "no_fetch_in_docs",
        "desc": "Dashboard aberto via file:// bloqueia fetch() por CORS — abre tela branca.",
        "pattern": r'\bfetch\s*\(\s*(?:[^\s)]|$)',
        "paths": ["docs"],
        "include": ["*.html", "*.js", "*.mjs", "*.cjs", "*.jsx", "*.ts", "*.tsx"],
        "ignora_se_antes_do_match": r'(?<!:)//|/\*(?!.*\*/)|<!--(?!.*-->)|^\s*\*(?:\s|$)',
        "severity": "block",
        "fix": "Injete os dados inline como `const _DATA = {...}` no HTML em tempo de build.",
    },
    {
        "id": "no_hardcoded_secrets",
        "desc": "Secret hardcoded no código.",
        # Exige um VALOR real (8+ chars sem espaço/aspas) entre aspas — evita casar
        # substrings tipo `"access_token="` ou valores vazios.
        "pattern": r'(password|passwd|pwd|senha|credential|api_key|apikey|secret|token(?!_key)|service_role|service_key|private_key|access_key|master_key)\w*["\']?'
                   r'\s*(?::\s*[\w\[\], ]+?\s*=|[:=])\s*["\'][^"\'\s]{8,}["\']',
        "include": ["*.py", "*.ts", "*.js", "*.mjs", "*.cjs", "*.jsx", "*.tsx", "*.html",
                    "*.sh", "*.yml", "*.yaml", "*.json", "*.md", "*.txt", "*.toml", "*.ini", "*.cfg",
                    "*.ipynb", "*.ps1", "*.bat", "*.sql", "*.conf", "*.xml", "*.tf"],
        "case_insensitive": True,
        "severity": "block",
        "fix": "Mova para .env (gitignored). Python: os.environ.get('VAR'). "
               "Edge Function: Deno.env.get('VAR').",
    },
    {
        "id": "no_open_tilde",
        "desc": "Python NÃO expande ~ dentro de open() — FileNotFoundError silencioso.",
        "pattern": r'open\s*\(\s*["\']~/',
        "include": ["*.py"],
        "severity": "block",
        "fix": "Use Path.home() / '...' ou os.path.expanduser('~/...').",
    },
    {
        "id": "no_product_name_ilike",
        "desc": "Filtro por product_name ILIKE é frágil — causa acessos bloqueados aleatórios.",
        "pattern": r'product_name\s+ilike',
        "include": ["*.py", "*.ts", "*.sql"],
        "case_insensitive": True,
        "severity": "block",
        "fix": "Filtre cohort por purchase_date >= 'ISO' AND purchase_date < 'ISO'.",
    },
    {
        "id": "install_sh_no_rm_rf_target",
        "desc": "install.sh com `rm -rf $DIR` apaga dados do aluno em re-execução.",
        "pattern": r'rm(?=(?:\s+-\S+)*?\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)\s)(?:\s+-\S+)*\s+["\']?\$\{?[A-Z_]*(DST|DEST|TARGET|INSTALL|DIR|PASTA|ROOT|BASE|HOME)',
        "include": ["install.sh", "*install.sh"],
        "severity": "block",
        "fix": "Use backup com timestamp: mv $DIR $DIR.bak-$(date +%s).",
    },
    {
        "id": "no_internal_infra_leak",
        "desc": "IDs/infra interna do Rafael não podem ir pro repo público. "
                "(OBS: ~/.operacao-ia/config/ e ~/.zxlab-mission-control/ são pastas "
                "do PRÓPRIO ALUNO no produto — permitidas. O que NÃO pode é ID de "
                "Supabase interno, webhook de produção ou helpers do pipeline.)",
        "pattern": r'(hjcudhxizemxepffrmbw|pnfvlszwlumetdjsuktj|'
                   r'webhook\.integracoes|\bsetup_io\b|\bversoes_io\b|'
                   r'paleta-cores-setups)',
        "include": ["*.py", "*.ts", "*.js", "*.mjs", "*.cjs", "*.jsx", "*.tsx", "*.md", "*.json",
                    "*.html", "*.sh", "*.yml", "*.yaml", "*.txt", "*.toml", "*.ini", "*.cfg",
                    "*.ipynb", "*.ps1", "*.bat", "*.sql", "*.conf", "*.xml", "*.tf"],
        "severity": "block",
        "fix": "Remova qualquer caminho/ID interno. O repo é PÚBLICO — isso vaza o "
               "mapa de produção do Rafael.",
    },
]

REQUIRED_FILES = ["README.md", "CLAUDE.md", "MASTERCLASS.md", "setup/check_prerequisites.py"]

# --- Perfil opt-in "nicho-dod" (DoD de produto de nicho) -------------------
# Ativado SOMENTE quando existir `.setup-ci.json` na raiz do repo validado
# com {"perfil": "nicho-dod"}. Sem esse arquivo/perfil, o comportamento é
# 100% idêntico ao validador original — repos existentes não são afetados.

PROFILE_FILE = ".setup-ci.json"
NICHO_DOD_PROFILE = "nicho-dod"

# Opt-in {"site_publico": ["docs"]}: a pasta é um site publicado de propósito,
# não um dashboard aberto via file://. Só duas coisas mudam dentro dela:
#   - fetch() é permitido (no site publicado não há o bloqueio de CORS do file://);
#   - o project ref do Supabase é permitido, porque o front publicado precisa dele.
# Qualquer outro marcador de infra interna e o no_hardcoded_secrets seguem valendo.
# Sem a chave, nada muda.
SUPABASE_REF_RE = re.compile(r"hjcudhxizemxepffrmbw|pnfvlszwlumetdjsuktj")

# Comentario real: o marcador abre a linha. Trecho com // ou # depois de codigo nao conta,
# e /* x */ seguido de codigo tambem nao. # so e comentario em Python.
CRASE_RE = re.compile(r"`[^`]*`")
COMENTARIO_PY_RE = re.compile(r"\s*#")
COMENTARIO_JS_RE = re.compile(r"\s*(?://|/\*(?!.*\*/)|\*(?:\s|$))")
EXTENSOES_JS = {".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx"}
STRING_RE = re.compile(r"""(["'`])(?:\\.|(?!\1).)*\1""")
# Valor de exemplo no no_hardcoded_secrets: o VALOR inteiro tem de ser placeholder.
SEGREDO_VALOR_RE = re.compile(r"""["']([^"']*)["']$""")
SEGREDO_EXEMPLO_RE = re.compile(
    r"\$\{.*\}|<[^>]*>|[a-z_-]*(?:\.{3}|[xX]{3,})|your[_-][a-z_-]*|[a-z_-]*example[a-z_-]*|[a-z_-]*placeholder[a-z_-]*|(?:0123456789abcdef)+|(?-i:[A-Z0-9_]*_(?:PASSWORD|PASSWD|PWD|SENHA|TOKEN|SECRET|KEY))",
    re.IGNORECASE,
)


def load_profile(root: Path) -> Optional[str]:
    """Lê .setup-ci.json na raiz do repo validado e retorna o perfil (ou None)."""
    pf = root / PROFILE_FILE
    if not pf.exists():
        return None
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
    except Exception:
        return "__invalid__"
    if not isinstance(data, dict):
        return "__invalid__"
    perfil = data.get("perfil")
    return perfil if isinstance(perfil, str) else None


def _nicho_fail(check: str, file: str, snippet: str, fix: str,
                line: int = 0, severity: str = "block") -> Dict[str, Any]:
    return {"file": file, "line": line, "check": check,
            "severity": severity, "snippet": snippet, "fix": fix}


def check_n1_apresentacao(root: Path) -> List[Dict[str, Any]]:
    """N1: docs/apresentacao.html existe, com link do repo e instrução Claude."""
    rel = "docs/apresentacao.html"
    f = root / rel
    if not f.exists():
        return [_nicho_fail("N1", rel, "arquivo ausente",
                            "Crie docs/apresentacao.html — a página de apresentação "
                            "do produto de nicho é entrega obrigatória do DoD.")]
    fails = []
    try:
        content = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [_nicho_fail("N1", rel, "arquivo ilegível (encoding)",
                            "Salve docs/apresentacao.html em UTF-8.")]
    if "github.com/zxmarketingdigital/" not in content:
        fails.append(_nicho_fail(
            "N1", rel, "sem link github.com/zxmarketingdigital/",
            "Adicione o link público do repositório "
            "(github.com/zxmarketingdigital/<repo>) na seção de instalação."))
    if "claude" not in content.lower():
        fails.append(_nicho_fail(
            "N1", rel, "sem menção a 'claude' na página",
            "A seção de instalação precisa da instrução de colar o comando "
            "no Claude (ex.: 'cole no Claude Code')."))
    return fails


def check_n2_proposta(root: Path) -> List[Dict[str, Any]]:
    """N2: docs/proposta.html existe e contém R$ (precificação preenchida)."""
    rel = "docs/proposta.html"
    f = root / rel
    if not f.exists():
        return [_nicho_fail("N2", rel, "arquivo ausente",
                            "Crie docs/proposta.html — a proposta comercial "
                            "do produto de nicho é entrega obrigatória do DoD.")]
    try:
        content = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [_nicho_fail("N2", rel, "arquivo ilegível (encoding)",
                            "Salve docs/proposta.html em UTF-8.")]
    if "R$" not in content:
        return [_nicho_fail("N2", rel, "sem 'R$' no arquivo",
                            "Preencha a precificação da proposta (valores em R$) — "
                            "proposta sem preço não está pronta pra entregar ao cliente.")]
    return []


def check_n3_demo_node(root: Path) -> List[Dict[str, Any]]:
    """N3: demo/server.mjs e demo/data.mjs existem e passam `node --check`."""
    fails = []
    targets = ["demo/server.mjs", "demo/data.mjs"]
    missing = [t for t in targets if not (root / t).exists()]
    for rel in missing:
        fails.append(_nicho_fail("N3", rel, "arquivo ausente",
                                 "Crie {} — o demo navegável faz parte do DoD "
                                 "do produto de nicho.".format(rel)))
    to_check = [t for t in targets if t not in missing]
    if not to_check:
        return fails
    node = shutil.which("node")
    if node is None:
        fails.append(_nicho_fail(
            "N3", "demo/", "node não encontrado no PATH — sintaxe não verificada",
            "Instale Node.js para validar a sintaxe de demo/*.mjs "
            "(no CI o Node já vem instalado).", severity="warn"))
        return fails
    for rel in to_check:
        try:
            proc = subprocess.run([node, "--check", str(root / rel)],
                                  capture_output=True, text=True, timeout=30)
        except Exception as e:
            fails.append(_nicho_fail("N3", rel, "node --check falhou: {}".format(e),
                                     "Rode `node --check {}` localmente e corrija.".format(rel)))
            continue
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            fails.append(_nicho_fail(
                "N3", rel, (err[0][:160] if err else "erro de sintaxe"),
                "Corrija o erro de sintaxe — `node --check {}` precisa passar.".format(rel)))
    return fails


def check_n4_painel_tokens(root: Path) -> List[Dict[str, Any]]:
    """N4: painel/style.css existe com os 3 tokens do design system ZX."""
    rel = "painel/style.css"
    f = root / rel
    if not f.exists():
        return [_nicho_fail("N4", rel, "arquivo ausente",
                            "Crie painel/style.css com o design system ZX "
                            "(#0D0D0D, #D97706, JetBrains Mono).")]
    try:
        content = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [_nicho_fail("N4", rel, "arquivo ilegível (encoding)",
                            "Salve painel/style.css em UTF-8.")]
    lower = content.lower()
    fails = []
    if "#0d0d0d" not in lower:
        fails.append(_nicho_fail("N4", rel, "token #0D0D0D ausente",
                                 "Use o fundo near-black #0D0D0D do design system ZX."))
    if "#d97706" not in lower:
        fails.append(_nicho_fail("N4", rel, "token #D97706 ausente",
                                 "Use o acento âmbar #D97706 do design system ZX."))
    if "JetBrains Mono" not in content:
        fails.append(_nicho_fail("N4", rel, "fonte JetBrains Mono ausente",
                                 "Use a fonte JetBrains Mono pra números/código "
                                 "conforme o design system ZX."))
    return fails


def check_n5_painel_botoes(root: Path) -> List[Dict[str, Any]]:
    """N5: painel/index.html tem pelo menos 2 botões de cadastro (+ Novo/Agendar/...)."""
    rel = "painel/index.html"
    f = root / rel
    if not f.exists():
        return [_nicho_fail("N5", rel, "arquivo ausente",
                            "Crie painel/index.html — o painel operacional faz "
                            "parte do DoD do produto de nicho.")]
    try:
        content = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [_nicho_fail("N5", rel, "arquivo ilegível (encoding)",
                            "Salve painel/index.html em UTF-8.")]
    hits = re.findall(r'\+\s*(Nov[oa]|Agendar|Adicionar|Cadastrar)', content,
                      flags=re.IGNORECASE)
    if len(hits) < 2:
        return [_nicho_fail(
            "N5", rel,
            "{} botão(ões) de cadastro encontrado(s) (mínimo 2)".format(len(hits)),
            "O painel precisa de pelo menos 2 botões de cadastro/ação "
            "(ex.: '+ Novo', '+ Agendar', '+ Adicionar', '+ Cadastrar').")]
    return []


def check_n6_sem_placeholders(root: Path) -> List[Dict[str, Any]]:
    """N6: nenhum placeholder `{{` em .html/.md/.mjs/.js de docs/, painel/ e demo/."""
    fails = []
    for sub in ["docs", "painel", "demo"]:
        base = root / sub
        if not base.exists():
            continue
        for f in _iter_files(base, ["*.html", "*.md", "*.mjs", "*.js"]):
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if "{{" in line:
                    fails.append(_nicho_fail(
                        "N6", str(f.relative_to(root)),
                        line.strip()[:160],
                        "Placeholder `{{` não preenchido — substitua pelo valor "
                        "real antes de entregar (template não renderizado).",
                        line=i))
    return fails


def collect_nicho_dod_failures(root: Path) -> List[Dict[str, Any]]:
    """Roda as regras N1..N6 do perfil nicho-dod."""
    failures: List[Dict[str, Any]] = []
    failures += check_n1_apresentacao(root)
    failures += check_n2_proposta(root)
    failures += check_n3_demo_node(root)
    failures += check_n4_painel_tokens(root)
    failures += check_n5_painel_botoes(root)
    failures += check_n6_sem_placeholders(root)
    return failures


def _iter_files(base: Path, patterns: List[str]):
    for pat in patterns:
        for f in base.rglob(pat):
            # nunca varrer .git, node_modules, nem o próprio validador
            # (ele contém os padrões que detecta — se auto-escanear, dá falso positivo)
            parts = set(f.relative_to(base).parts)
            if ".git" in parts or "node_modules" in parts:
                continue
            if f.resolve() == Path(__file__).resolve():
                continue
            yield f


def _git_ignored(root: Path, relpath: str) -> bool:
    """True se o arquivo é gitignored (logo nunca existe no checkout do CI)."""
    try:
        # O .gitignore de um repo PAI não vale aqui: o CI faz checkout só deste repo.
        topo = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
        if not topo or Path(topo).resolve() != root.resolve():
            return False
        r = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", relpath],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def load_site_publico(root: Path) -> List[str]:
    """Pastas declaradas em site_publico no .setup-ci.json.

    Valor malformado não relaxa nada: a regra continua bloqueando e o erro
    aparece no CI. Só vale para docs/ e subpastas: é onde o site é publicado.
    """
    pf = root / PROFILE_FILE
    if not pf.exists():
        return []
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = data.get("site_publico") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    pastas = []
    for item in raw:
        if not isinstance(item, str) or item.startswith("/") or "\\" in item:
            continue
        partes = [x for x in item.split("/") if x]
        if not partes or partes[0] != "docs" or any(x in (".", "..") for x in partes):
            continue
        pastas.append("/".join(partes))
    return pastas


def _no_site_publico(rel: str, pastas: List[str]) -> bool:
    return any(rel.startswith(p + "/") for p in pastas)


def _match_liberado(check_id: str, trecho: str, no_site: bool) -> bool:
    """True quando o trecho casado nao conta como violacao."""
    if check_id == "no_hardcoded_secrets":
        valor = SEGREDO_VALOR_RE.search(trecho)
        return bool(valor and SEGREDO_EXEMPLO_RE.fullmatch(valor.group(1)))
    if check_id == "no_internal_infra_leak" and no_site:
        return bool(SUPABASE_REF_RE.fullmatch(trecho))
    return False


# Arquivos exigidos só em setup de ENSINO (zx-control-setupN); produto de
# nicho (perfil nicho-dod) não tem masterclass embutida nem check_prerequisites.
ENSINO_ONLY_REQUIRED = {"MASTERCLASS.md", "setup/check_prerequisites.py"}


def collect_failures(root: Path) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    perfil = load_profile(root)
    nicho = perfil == NICHO_DOD_PROFILE
    site_publico = load_site_publico(root)

    # 1) AST 3.9 em todos os .py
    for py in _iter_files(root, ["*.py"]):
        try:
            code = py.read_text(encoding="utf-8")
        except Exception:
            continue
        try:
            ast.parse(code, feature_version=(3, 9))
        except SyntaxError as e:
            failures.append({
                "file": str(py.relative_to(root)),
                "line": e.lineno or 0,
                "check": "ast_py39",
                "severity": "block",
                "snippet": (e.text or "").strip()[:160],
                "fix": "Sintaxe incompatível com Python 3.9.",
            })

    # 2) estrutura mínima (perfil nicho-dod dispensa os arquivos de ensino)
    for req in REQUIRED_FILES:
        if nicho and req in ENSINO_ONLY_REQUIRED:
            continue
        if not (root / req).exists():
            failures.append({
                "file": req, "line": 0, "check": "estrutura_minima",
                "severity": "block", "snippet": "arquivo obrigatório ausente",
                "fix": "Todo setup precisa de README.md, CLAUDE.md, MASTERCLASS.md "
                       "e setup/check_prerequisites.py.",
            })

    # 3) .env nunca commitado no histórico
    historico_err = ""
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "log", "--all", "--diff-filter=A", "--format=",
             "--name-only", "--", "*.env", ".env.*", "*/.env.*", "*credentials*", "*secrets*"],
            capture_output=True, text=True, timeout=30,
        )
        out = res.stdout.strip()
        if res.returncode != 0:
            historico_err = (res.stderr.strip().splitlines() or ["git log falhou"])[-1]
        if out:
            for fname in out.splitlines():
                if fname.strip().endswith((".example", ".template", ".sample")):
                    continue
                if not fname.strip():
                    continue
                failures.append({
                    "file": fname.strip(), "line": 0, "check": "env_no_historico",
                    "severity": "block", "snippet": "arquivo sensível no git history",
                    "fix": "Remova do histórico (BFG / git filter-repo) e adicione ao .gitignore.",
                })
    except Exception as exc:
        historico_err = str(exc)
    # Sem .git (zip baixado) o check não se aplica. Com .git, não verificar não é passar.
    if historico_err and (root / ".git").exists():
        failures.append({
            "file": ".git", "line": 0, "check": "env_no_historico",
            "severity": "block", "snippet": f"não foi possível verificar o histórico: {historico_err}"[:200],
            "fix": "Rode o validador num clone git íntegro, com permissão de leitura no repositório.",
        })

    # 4) greps mecânicos
    for chk in GREP_CHECKS:
        flags = re.IGNORECASE if chk.get("case_insensitive") else 0
        pattern = re.compile(chk["pattern"], flags)
        bases = [root / p for p in chk.get("paths", ["."])]
        excludes = chk.get("exclude_lines_with", [])
        antes_do_match = chk.get("ignora_se_antes_do_match")
        for base in bases:
            if not base.exists():
                continue
            for f in _iter_files(base, chk.get("include", ["*"])):
                try:
                    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue
                no_site = _no_site_publico(
                    f.relative_to(root).as_posix(), site_publico)
                if no_site and chk["id"] == "no_fetch_in_docs":
                    continue
                for i, line in enumerate(lines, 1):
                    # Em md, html, json e yml o "*" é bullet e "//" é texto: não existe comentário a pular.
                    comentario = (COMENTARIO_PY_RE if f.suffix == ".py"
                                  else COMENTARIO_JS_RE if f.suffix in EXTENSOES_JS else None)
                    if chk.get("skip_comment_lines") and comentario and comentario.match(line):
                        continue
                    if any(ex in line for ex in excludes):
                        continue
                    alvo = CRASE_RE.sub("", line) if chk.get("strip_inline_code") else line
                    if any(not _match_liberado(chk["id"], m.group(0), no_site)
                           and not (antes_do_match and re.search(antes_do_match, STRING_RE.sub('""', alvo[:m.start()])))
                           for m in pattern.finditer(alvo)):
                        failures.append({
                            "file": str(f.relative_to(root)),
                            "line": i,
                            "check": chk["id"],
                            "severity": chk["severity"],
                            "snippet": line.strip()[:160],
                            "fix": chk.get("fix", ""),
                        })

    # 4b) perfil nicho-dod: fixtures de teste e arquivos gitignored não são
    #     vazamento real de segredo (gitignored nem existe no checkout do CI).
    if nicho:
        failures = [
            f for f in failures
            if not (
                f["check"] == "no_hardcoded_secrets"
                and (f["file"].startswith("tests/") or _git_ignored(root, f["file"]))
            )
        ]

    # 5) perfil opt-in nicho-dod (regras N1..N6) — só roda se .setup-ci.json
    #    declarar {"perfil": "nicho-dod"}. Sem o arquivo, nada muda.
    if perfil == "__invalid__":
        failures.append(_nicho_fail(
            "setup_ci_json_invalido", PROFILE_FILE,
            "JSON inválido ou formato inesperado",
            'O arquivo .setup-ci.json precisa ser um JSON tipo '
            '{"perfil": "nicho-dod"}. Corrija ou remova o arquivo.'))
    elif perfil == NICHO_DOD_PROFILE:
        failures += collect_nicho_dod_failures(root)

    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida um repo de Setup ZX Control.")
    ap.add_argument("--path", default=".", help="Diretório do repo (default: atual)")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print("ERRO: caminho nao existe: {}".format(root))
        return 2

    failures = collect_failures(root)
    blocks = [f for f in failures if f["severity"] == "block"]
    warns = [f for f in failures if f["severity"] != "block"]

    if not failures:
        print("OK — nenhuma regra violada. Pode abrir o Pull Request. ✅")
        return 0

    print("Resultado da validacao do setup:\n")
    for f in failures:
        icon = "BLOQUEIA" if f["severity"] == "block" else "aviso"
        loc = "{}:{}".format(f["file"], f["line"]) if f["line"] else f["file"]
        print("  [{}] {}  ({})".format(icon, loc, f["check"]))
        if f.get("snippet"):
            print("      trecho: {}".format(f["snippet"]))
        if f.get("fix"):
            print("      como corrigir: {}".format(f["fix"]))
        print("")

    print("-" * 60)
    print("{} bloqueante(s), {} aviso(s).".format(len(blocks), len(warns)))
    if blocks:
        print("Corrija os itens BLOQUEIA antes de abrir o PR.")
        return 1
    print("Só avisos — pode abrir o PR, mas vale revisar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
