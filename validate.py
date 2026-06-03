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
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any

# --- As 12 regras, em forma de checks mecânicos ----------------------------
# Cada check é genérico: não referencia nenhum ID/credencial/caminho interno.
GREP_CHECKS: List[Dict[str, Any]] = [
    {
        "id": "no_str_pipe_none",
        "desc": "Type union `X | None` é Python 3.10+ — quebra em alunos com Python 3.9.",
        "pattern": r'\b\w+\s*\|\s*None\b',
        "include": ["*.py"],
        "exclude_lines_with": ["# noqa", "from __future__ import"],
        "severity": "block",
        "fix": "Use Optional[str] (from typing import Optional) ou adicione "
               "`from __future__ import annotations` no topo do arquivo.",
    },
    {
        "id": "no_match_case_python_310",
        "desc": "match/case é Python 3.10+ — quebra em macOS Monterey (3.9).",
        "pattern": r'^\s*match\s+\w+\s*:',
        "include": ["*.py"],
        "exclude_lines_with": ["from __future__ import", "# noqa"],
        "severity": "block",
        "fix": "Troque match/case por if/elif.",
    },
    {
        "id": "no_fetch_in_docs",
        "desc": "Dashboard aberto via file:// bloqueia fetch() por CORS — abre tela branca.",
        "pattern": r'\bfetch\s*\(',
        "paths": ["docs"],
        "include": ["*.html", "*.js"],
        "exclude_lines_with": ["//", "/*", "*"],
        "severity": "block",
        "fix": "Injete os dados inline como `const _DATA = {...}` no HTML em tempo de build.",
    },
    {
        "id": "no_hardcoded_secrets",
        "desc": "Secret hardcoded no código.",
        # Exige um VALOR real (8+ chars sem espaço/aspas) entre aspas — evita casar
        # substrings tipo `"access_token="` ou valores vazios.
        "pattern": r'(password|api_key|apikey|secret|token|service_role)'
                   r'\s*[:=]\s*["\'][^"\'\s]{8,}["\']',
        "include": ["*.py", "*.ts", "*.js"],
        "case_insensitive": True,
        "exclude_lines_with": ["os.environ", "Deno.env", "process.env", "${",
                               "getenv", "config(", "#", "//", "*", "example",
                               "EXAMPLE", "Example", "your_", "<", "placeholder",
                               "os.getenv", "YOUR_", "xxx", "XXX", "..."],
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
        "pattern": r'rm\s+-rf\s+["\']?\$\{?[A-Z_]*(DST|TARGET|INSTALL|DIR)',
        "include": ["install.sh", "*install.sh"],
        "severity": "block",
        "fix": "Use backup com timestamp: mv $DIR $DIR.bak-$(date +%s).",
    },
    {
        "id": "no_internal_infra_leak",
        "desc": "Referência a infraestrutura interna do Rafael não pode ir pro repo público. "
                "(OBS: ~/.operacao-ia/config/ é o diretório LOCAL do aluno — permitido.)",
        "pattern": r'(zxlab-mission-control|hjcudhxizemxepffrmbw|'
                   r'pnfvlszwlumetdjsuktj|webhook\.integracoes|'
                   r'\bsetup_io\b|\bversoes_io\b|paleta-cores-setups)',
        "include": ["*.py", "*.ts", "*.js", "*.md", "*.json", "*.html"],
        "exclude_lines_with": ["validate.py", "no_internal_infra_leak"],
        "severity": "block",
        "fix": "Remova qualquer caminho/ID interno. O repo é PÚBLICO — isso vaza o "
               "mapa de produção do Rafael.",
    },
]

REQUIRED_FILES = ["README.md", "CLAUDE.md", "MASTERCLASS.md", "setup/check_prerequisites.py"]


def _iter_files(base: Path, patterns: List[str]):
    for pat in patterns:
        for f in base.rglob(pat):
            # nunca varrer .git, node_modules, nem o próprio validador
            # (ele contém os padrões que detecta — se auto-escanear, dá falso positivo)
            parts = set(f.parts)
            if ".git" in parts or "node_modules" in parts:
                continue
            if f.name == "validate.py":
                continue
            yield f


def collect_failures(root: Path) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []

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

    # 2) estrutura mínima
    for req in REQUIRED_FILES:
        if not (root / req).exists():
            failures.append({
                "file": req, "line": 0, "check": "estrutura_minima",
                "severity": "block", "snippet": "arquivo obrigatório ausente",
                "fix": "Todo setup precisa de README.md, CLAUDE.md, MASTERCLASS.md "
                       "e setup/check_prerequisites.py.",
            })

    # 3) .env nunca commitado no histórico
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--all", "--diff-filter=A",
             "--name-only", "--", "*.env", "*credentials*", "*secrets*"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        if out:
            for fname in out.splitlines():
                if fname.strip().endswith((".example", ".template")):
                    continue
                if not fname.strip():
                    continue
                failures.append({
                    "file": fname.strip(), "line": 0, "check": "env_no_historico",
                    "severity": "block", "snippet": "arquivo sensível no git history",
                    "fix": "Remova do histórico (BFG / git filter-repo) e adicione ao .gitignore.",
                })
    except Exception:
        pass  # sem git (ex.: zip baixado) — pula este check

    # 4) greps mecânicos
    for chk in GREP_CHECKS:
        flags = re.IGNORECASE if chk.get("case_insensitive") else 0
        pattern = re.compile(chk["pattern"], flags)
        bases = [root / p for p in chk.get("paths", ["."])]
        excludes = chk.get("exclude_lines_with", [])
        for base in bases:
            if not base.exists():
                continue
            for f in _iter_files(base, chk.get("include", ["*"])):
                try:
                    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue
                for i, line in enumerate(lines, 1):
                    if any(ex in line for ex in excludes):
                        continue
                    if pattern.search(line):
                        failures.append({
                            "file": str(f.relative_to(root)),
                            "line": i,
                            "check": chk["id"],
                            "severity": chk["severity"],
                            "snippet": line.strip()[:160],
                            "fix": chk.get("fix", ""),
                        })
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
