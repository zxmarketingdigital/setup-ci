#!/usr/bin/env python3
"""
Smoke test do validate.py — modo padrão e perfil opt-in nicho-dod.

Monta repos fake em diretório temporário e roda o validate.py contra eles:
  1. Repo base SEM .setup-ci.json  -> exit 0, nenhuma regra N* no output
  2. Repo base COM perfil nicho-dod mas sem entregas -> exit 1, N1..N6 no output
  3. Repo nicho-dod completo -> exit 0
  4. .setup-ci.json inválido -> exit 1 (setup_ci_json_invalido)

Uso: python3 tests/smoke_nicho_dod.py
Sem dependências externas (Python 3.9+).
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE = REPO_ROOT / "validate.py"

FAILED = []


def make_base_setup(root: Path) -> None:
    """Estrutura mínima que passa nas 12 regras originais."""
    (root / "setup").mkdir(parents=True)
    (root / "README.md").write_text("# Setup fake\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# Guia\n", encoding="utf-8")
    (root / "MASTERCLASS.md").write_text("# Masterclass\n", encoding="utf-8")
    (root / "setup" / "check_prerequisites.py").write_text(
        "print('ok')\n", encoding="utf-8")


def make_nicho_completo(root: Path) -> None:
    """Entregas completas do DoD nicho — deve passar N1..N6."""
    (root / "docs").mkdir(exist_ok=True)
    (root / "demo").mkdir(exist_ok=True)
    (root / "painel").mkdir(exist_ok=True)
    (root / "docs" / "apresentacao.html").write_text(
        "<html><body><h2>Instalacao</h2>"
        "<p>Cole no Claude Code:</p>"
        "<code>gh repo clone github.com/zxmarketingdigital/produto-fake</code>"
        "</body></html>", encoding="utf-8")
    (root / "docs" / "proposta.html").write_text(
        "<html><body><p>Investimento: R$ 1.500/mes</p></body></html>",
        encoding="utf-8")
    (root / "demo" / "server.mjs").write_text(
        "import { createServer } from 'node:http';\n"
        "createServer((req, res) => res.end('ok'));\n", encoding="utf-8")
    (root / "demo" / "data.mjs").write_text(
        "export const data = [1, 2, 3];\n", encoding="utf-8")
    (root / "painel" / "style.css").write_text(
        "body { background: #0D0D0D; color: #D97706; "
        "font-family: 'JetBrains Mono', monospace; }\n", encoding="utf-8")
    (root / "painel" / "index.html").write_text(
        "<html><body><button>+ Novo paciente</button>"
        "<button>+ Agendar consulta</button></body></html>", encoding="utf-8")


def run_validate(root: Path):
    proc = subprocess.run([sys.executable, str(VALIDATE), "--path", str(root)],
                          capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "OK " if cond else "FAIL"
    print("[{}] {}".format(status, name))
    if not cond:
        FAILED.append(name)
        if detail:
            print("       {}".format(detail[:600]))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="setupci-smoke-"))
    try:
        # 1) sem perfil -> comportamento original intacto
        r1 = tmp / "sem-perfil"
        r1.mkdir()
        make_base_setup(r1)
        code, out = run_validate(r1)
        check("sem perfil: exit 0", code == 0, out)
        check("sem perfil: nenhuma regra N* no output",
              all("(N{})".format(n) not in out for n in range(1, 7)), out)

        # 2) perfil nicho-dod sem entregas -> N1..N6 bloqueiam
        r2 = tmp / "nicho-incompleto"
        r2.mkdir()
        make_base_setup(r2)
        (r2 / ".setup-ci.json").write_text(
            json.dumps({"perfil": "nicho-dod"}), encoding="utf-8")
        code, out = run_validate(r2)
        check("nicho incompleto: exit 1", code == 1, out)
        for n in ["N1", "N2", "N3", "N4", "N5"]:
            check("nicho incompleto: regra {} reportada".format(n),
                  "({})".format(n) in out, out)
        # N6 só dispara com placeholder presente — testa de propósito:
        (r2 / "docs").mkdir(exist_ok=True)
        (r2 / "docs" / "x.md").write_text("Ola {{NOME_CLIENTE}}\n", encoding="utf-8")
        code, out = run_validate(r2)
        check("nicho incompleto: regra N6 reportada (placeholder {{)",
              "(N6)" in out, out)

        # 3) nicho-dod completo -> exit 0
        r3 = tmp / "nicho-completo"
        r3.mkdir()
        make_base_setup(r3)
        (r3 / ".setup-ci.json").write_text(
            json.dumps({"perfil": "nicho-dod"}), encoding="utf-8")
        make_nicho_completo(r3)
        code, out = run_validate(r3)
        check("nicho completo: exit 0", code == 0, out)

        # 4) .setup-ci.json inválido -> bloqueia com mensagem clara
        r4 = tmp / "json-invalido"
        r4.mkdir()
        make_base_setup(r4)
        (r4 / ".setup-ci.json").write_text("{perfil: nicho", encoding="utf-8")
        code, out = run_validate(r4)
        check("json inválido: exit 1", code == 1, out)
        check("json inválido: check setup_ci_json_invalido no output",
              "setup_ci_json_invalido" in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("-" * 50)
    if FAILED:
        print("{} check(s) falharam: {}".format(len(FAILED), ", ".join(FAILED)))
        return 1
    print("Smoke OK — todos os checks passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
