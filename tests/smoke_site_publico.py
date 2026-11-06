#!/usr/bin/env python3
"""Smoke do opt-in `site_publico`: o que libera, o que continua bloqueando e o
que acontece sem a chave ou com valor malformado.

Rodar: python3 tests/smoke_site_publico.py   (exit 0 = tudo certo)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "validate.py"

REF = "const U = 'https://pnfvlszwlumetdjsuktj.supabase.co/functions/v1/x';"
FETCH = "fetch(url).then(r => r.json());"
WEBHOOK = "const W = 'https://webhook.integracoes-zx-lab.uk/webhook/x';"
AMBOS = "const U = 'https://pnfvlszwlumetdjsuktj.supabase.co', W = 'https://webhook.integracoes-zx-lab.uk/x';"
SEGREDO = "const api_key = 'abcdefghijkl0123456789';"


def roda(arquivos, config):
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for nome in ("README.md", "CLAUDE.md", "MASTERCLASS.md"):
            (d / nome).write_text("# x\n", encoding="utf-8")
        (d / "setup").mkdir()
        (d / "setup" / "check_prerequisites.py").write_text("print('ok')\n", encoding="utf-8")
        if config is not None:
            texto = config if isinstance(config, str) else json.dumps(config)
            (d / ".setup-ci.json").write_text(texto, encoding="utf-8")
        for rel, conteudo in arquivos.items():
            alvo = d / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(conteudo + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(VALIDATE), "--path", str(d)],
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout + r.stderr


ON = {"site_publico": ["docs"]}
LEAK, F, SEC = "no_internal_infra_leak", "no_fetch_in_docs", "no_hardcoded_secrets"
CASOS = [
    # nome, arquivos, config, regra, deve_bloquear
    ("sem chave: ref bloqueia",        {"docs/a.js": REF},       None, LEAK, True),
    ("sem chave: fetch bloqueia",      {"docs/a.js": FETCH},     None, F, True),
    ("com chave: ref passa",           {"docs/a.js": REF},       ON, LEAK, False),
    ("com chave: fetch passa",         {"docs/a.js": FETCH},     ON, F, False),
    ("com chave: webhook bloqueia",    {"docs/a.js": WEBHOOK},   ON, LEAK, True),
    ("com chave: ref+webhook bloqueia", {"docs/a.js": AMBOS},    ON, LEAK, True),
    ("com chave: segredo bloqueia",    {"docs/a.js": SEGREDO},   ON, SEC, True),
    ("com chave: ref fora da pasta",   {"setup/a.py": REF},      ON, LEAK, True),
    ("prefixo parecido nao casa",      {"docs2/a.js": REF},      ON, LEAK, True),
    ("raiz nao relaxa",                {"docs/a.js": REF},       {"site_publico": ["."]}, LEAK, True),
    ("barra nao relaxa",               {"docs/a.js": REF},       {"site_publico": ["/"]}, LEAK, True),
    ("absoluto nao relaxa",            {"docs/a.js": REF},       {"site_publico": ["/docs"]}, LEAK, True),
    ("pontos nao relaxam",             {"docs/a.js": REF},       {"site_publico": ["x/../docs"]}, LEAK, True),
    ("string nao relaxa",              {"docs/a.js": REF},       {"site_publico": "docs"}, LEAK, True),
    ("json quebrado nao relaxa",       {"docs/a.js": REF},       "{quebrado", LEAK, True),
    ("sem chave: segredo com // bloqueia", {"a.js": SEGREDO + " // TODO"}, None, SEC, True),
    ("sem chave: segredo com # bloqueia", {"a.py": "api_key = 'abcdefghijkl012345'  # local"}, None, SEC, True),
    ("sem chave: segredo com < bloqueia", {"a.js": "if (a < b) x = {token: 'abcdefghijkl012345'};"}, None, SEC, True),
    ("segredo em comentario bloqueia", {"a.js": "// " + SEGREDO}, None, SEC, True),
    ("comentario com valor de exemplo passa", {"a.js": "// const token = 'your_token_here';"}, None, SEC, False),
    ("webhook em mjs bloqueia",        {"demo/server.mjs": WEBHOOK}, None, LEAK, True),
    ("webhook em yml bloqueia",        {"ci.yml": "url: https://webhook.integracoes-zx-lab.uk/x"}, None, LEAK, True),
    ("segredo em ipynb bloqueia",      {"a.ipynb": "api_key = 'abcdefgh12345678'"}, None, SEC, True),
    ("segredo em sql bloqueia",        {"a.sql": "-- password = 'abcdefgh12345678'"}, None, SEC, True),
    ("url em texto nao esconde fetch", {"docs/a.html": "<p>https://exemplo.com</p><script>fetch(u);</script>"}, None, F, True),
    ("pasta fora de docs nao relaxa",  {"setup/a.py": REF},      {"site_publico": ["setup"]}, LEAK, True),
    ("subpasta de docs relaxa",        {"docs/app/a.js": REF},   {"site_publico": ["docs/app"]}, LEAK, False),
    ("comentario antes de codigo bloqueia", {"a.js": "/* cfg */ " + SEGREDO}, None, SEC, True),
    ("valor com example no meio bloqueia", {"a.py": "password = 'Example2024!SenhaReal'"}, None, SEC, True),
    ("valor com xxx no meio bloqueia", {"a.py": "api_key = 'sk_live_xxx9f8e7d6c5b4'"}, None, SEC, True),
    ("chave entre aspas bloqueia",     {"a.py": "c = {'api_key': 'abcdefgh12345678'}"}, None, SEC, True),
    ("segredo com process.env na linha bloqueia", {"a.js": SEGREDO + " const u = process.env.URL;"}, None, SEC, True),
    ("referencia de env passa",        {"a.js": "const token = process.env.TOKEN;"}, None, SEC, False),
    ("template passa",                 {"a.js": "const token = '${TOKEN_REAL}';"}, None, SEC, False),
    ("sufixo _KEY bloqueia",           {"a.py": "STRIPE_SECRET_KEY = 'abcdefgh12345678'"}, None, SEC, True),
    ("anotacao de tipo bloqueia",      {"a.py": "API_KEY: str = 'abcdefgh12345678'"}, None, SEC, True),
    ("exemplo com digito bloqueia",    {"a.py": "password = 'Example2024SenhaReal'"}, None, SEC, True),
    ("exemplo em chave real bloqueia", {"a.py": "api_key = 'sk-example-9f8e7d6c5b4a3210'"}, None, SEC, True),
    ("list | None bloqueia",           {"a.py": "def f(x: list[str] | None = None): pass"}, None, "no_str_pipe_none", True),
    ("crase nao libera | None",        {"a.py": "def f(x: int | None = None): return f'`{x}`'"}, None, "no_str_pipe_none", True),
    ("comentario de | None passa",     {"a.py": "# use int | None so no 3.10"}, None, "no_str_pipe_none", False),
    ("match com atributo bloqueia",    {"a.py": "def f(s):\n    match s.estado:\n        case 1: pass"}, None, "no_match_case_python_310", True),
    ("rm -fr bloqueia",                {"install.sh": 'rm -fr "$DIR"'}, None, "install_sh_no_rm_rf_target", True),
    ("rm -r -f bloqueia",              {"install.sh": 'rm -r -f "$TARGET"'}, None, "install_sh_no_rm_rf_target", True),
    ("rm -f de arquivo passa",         {"install.sh": 'rm -f "$DIR/x.txt"'}, None, "install_sh_no_rm_rf_target", False),
    ("rm --force passa",               {"install.sh": 'rm --force "$DIR/x.txt"'}, None, "install_sh_no_rm_rf_target", False),
    ("rm --recursive bloqueia",        {"install.sh": 'rm --recursive --force "$DIR"'}, None, "install_sh_no_rm_rf_target", True),
    ("citacao em crase passa",         {"a.py": 'doc = "nao use `str | None` aqui"'}, None, "no_str_pipe_none", False),
    ("git quebrado bloqueia",          {".git/HEAD": "x"}, None, "env_no_historico", True),
    ("nome de chave de storage passa", {"a.js": 'var TOKEN_KEY = "app_consumo_tok_v1";'}, None, SEC, False),
    ("service key generica bloqueia",  {"a.js": "const SUPABASE_SERVICE_KEY = 'abcdefgh12345678';"}, None, SEC, True),
    ("rm -rf em DEST bloqueia",        {"install.sh": 'rm -rf "$DEST"'}, None, "install_sh_no_rm_rf_target", True),
    ("fetch com URL bloqueia",         {"docs/a.js": "fetch('https://api.exemplo.com/d');"}, None, F, True),
    ("fetch com nota depois bloqueia", {"docs/a.js": "fetch(x); // nota"}, None, F, True),
    ("nota sem argumento passa",       {"docs/a.html": "DADOS INLINE (NUNCA fetch() - abre via file://)"}, None, F, False),
    ("fetch depois de URL bloqueia",   {"docs/a.js": "const B = 'https://x.com/d'; fetch(B);"}, None, F, True),
    ("fetch depois de produto bloqueia", {"docs/a.js": "n = 2 * 3; fetch(u);"}, None, F, True),
    ("fetch com argumento na outra linha bloqueia", {"docs/a.js": "const r = await fetch(\n  'd.json');"}, None, F, True),
    ("fetch em comentario de fim de linha passa", {"docs/a.js": "x(); // fetch(u)"}, None, F, False),
    ("fetch em comentario html passa", {"docs/a.html": "<!-- fetch(u) -->"}, None, F, False),
    ("fetch depois de bloco fechado bloqueia", {"docs/a.js": "/* carrega */ fetch(u);"}, None, F, True),
    ("fetch depois de html fechado bloqueia", {"docs/a.html": "<!-- x --><script>fetch(u)</script>"}, None, F, True),
    ("fetch depois de */ bloqueia",    {"docs/a.js": "*/ fetch(u);"}, None, F, True),
    ("fetch dentro de bloco aberto passa", {"docs/a.js": "/* fetch(u)"}, None, F, False),
    ("fetch em mjs bloqueia",          {"docs/a.mjs": "const d = await fetch(u);"}, None, F, True),
    ("senha bloqueia",                 {"a.py": "senha = 'minhasenha123'"}, None, SEC, True),
    ("segredo em md bloqueia",         {"a.md": 'export OPENAI_API_KEY="abcdefgh12345678"'}, None, SEC, True),
    ("segredo em toml bloqueia",       {"a.toml": 'api_key = "abcdefgh12345678"'}, None, SEC, True),
    ("nome de variavel como valor passa", {"a.md": "f(password='NEO4J_PASSWORD')"}, None, SEC, False),
    ("maiusculas sem sufixo bloqueiam", {"a.py": "api_key = 'SK_LIVE_ABC123'"}, None, SEC, True),
    ("minusculas com sufixo bloqueiam", {"a.py": "api_key = 'abc_def_key'"}, None, SEC, True),
    ("segredo em bullet de md bloqueia", {"a.md": '* OPENAI_API_KEY="abcdefgh12345678"'}, None, SEC, True),
    ("segredo depois de // em html bloqueia", {"a.html": "// token = 'abcdefgh12345678'"}, None, SEC, True),
    ("segredo em metodo gerador bloqueia", {"a.js": "*g() { return {token: 'abcdefgh12345678'}; }"}, None, SEC, True),
    ("fetch depois de glob em string bloqueia", {"docs/a.js": "const G = 'data/*.json'; const r = fetch(G);"}, None, F, True),
    ("fetch depois de // em string bloqueia", {"docs/a.js": "const u = 'a//b'; fetch(u);"}, None, F, True),
    ("fetch em metodo gerador bloqueia", {"docs/a.js": "*g() { return fetch(u); }"}, None, F, True),
    ("fetch em comentario com string passa", {"docs/a.js": "// 'x' fetch(u)"}, None, F, False),
    ("fetch em linha de jsdoc passa",  {"docs/a.js": " * item fetch(u)"}, None, F, False),
    ("placeholder sequencial passa",   {"a.json": '{"lp_token": "0123456789abcdef0123456789abcdef"}'}, None, SEC, False),
    ("sequencia alterada bloqueia",    {"a.json": '{"lp_token": "0123456789abcdef0123456789abcde9"}'}, None, SEC, True),
    ("segredo em html bloqueia",       {"docs/a.html": "<script>const SUPABASE_SERVICE_ROLE_KEY = 'eyJhbGciOiJIUzI1';</script>"}, None, SEC, True),
    ("segredo em mjs bloqueia",        {"demo/a.mjs": "const api_key = 'abcdefgh12345678';"}, None, SEC, True),
    ("segredo em json bloqueia",       {"a.json": '{"api_key": "abcdefgh12345678"}'}, None, SEC, True),
    ("fetch em comentario passa",      {"docs/a.js": "// fetch(x)"}, None, F, False),
    ("fetch em bloco de comentario passa", {"docs/a.js": " * fetch(x)"}, None, F, False),
    ("match sem espaco bloqueia",      {"a.py": "def f(s):\n    match(s):\n        case 1: pass"}, None, "no_match_case_python_310", True),
    ("variavel match passa",           {"a.py": "match = f(a)"}, None, "no_match_case_python_310", False),
    ("sem chave: valor de exemplo passa", {"a.js": "const token = 'your_token_here';"}, None, SEC, False),
    ("validate.py do repo e varrido",  {"setup/validate.py": SEGREDO.replace("const ", "")}, None, SEC, True),
    ("webhook com citacao ao validate.py bloqueia", {"a.js": WEBHOOK + " // validate.py"}, None, LEAK, True),
]


def caso_env_no_historico():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for nome in ("README.md", "CLAUDE.md", "MASTERCLASS.md"):
            (d / nome).write_text("# x\n", encoding="utf-8")
        (d / "setup").mkdir()
        (d / "setup" / "check_prerequisites.py").write_text("print('ok')\n", encoding="utf-8")
        (d / ".env.production").write_text("X=1\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A", "-f"],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)
        r = subprocess.run([sys.executable, str(VALIDATE), "--path", str(d)],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 1 and "env_no_historico" in r.stdout + r.stderr


def caso_pasta_pai_node_modules():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "node_modules" / "setup"
        (d / "setup").mkdir(parents=True)
        for nome in ("README.md", "CLAUDE.md", "MASTERCLASS.md"):
            (d / nome).write_text("# x\n", encoding="utf-8")
        (d / "setup" / "check_prerequisites.py").write_text("print('ok')\n", encoding="utf-8")
        (d / "a.py").write_text("api_key = 'abcdefgh12345678'\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(VALIDATE), "--path", str(d)],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 1 and "no_hardcoded_secrets" in r.stdout + r.stderr


def caso_env_example_no_historico():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for nome in ("README.md", "CLAUDE.md", "MASTERCLASS.md"):
            (d / nome).write_text("# x\n", encoding="utf-8")
        (d / "setup").mkdir()
        (d / "setup" / "check_prerequisites.py").write_text("print('ok')\n", encoding="utf-8")
        (d / ".env.example").write_text("X=\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A", "-f"],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)
        r = subprocess.run([sys.executable, str(VALIDATE), "--path", str(d)],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and "env_no_historico" not in r.stdout + r.stderr


def caso_repo_pai_que_ignora_tudo():
    with tempfile.TemporaryDirectory() as tmp:
        pai = Path(tmp)
        subprocess.run(["git", "-C", str(pai), "init", "-q"], check=True, capture_output=True)
        (pai / ".gitignore").write_text("*\n", encoding="utf-8")
        d = pai / "extraido"
        (d / "setup").mkdir(parents=True)
        for nome in ("README.md", "CLAUDE.md", "MASTERCLASS.md"):
            (d / nome).write_text("# x\n", encoding="utf-8")
        (d / "setup" / "check_prerequisites.py").write_text("print('ok')\n", encoding="utf-8")
        (d / "a.py").write_text("api_key = 'abcdefgh12345678'\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(VALIDATE), "--path", str(d)],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 1 and "no_hardcoded_secrets" in r.stdout + r.stderr


def caso_nicho_dod_repo_pai_ignora():
    with tempfile.TemporaryDirectory() as tmp:
        pai = Path(tmp)
        subprocess.run(["git", "-C", str(pai), "init", "-q"], check=True, capture_output=True)
        (pai / ".gitignore").write_text("*\n", encoding="utf-8")
        d = pai / "setup-x"
        (d / "src").mkdir(parents=True)
        (d / ".setup-ci.json").write_text('{"perfil": "nicho-dod"}', encoding="utf-8")
        (d / "src" / "config.py").write_text("api_key = 'abcdefgh12345678'\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(VALIDATE), "--path", str(d)],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 1 and "no_hardcoded_secrets" in r.stdout + r.stderr


def main() -> int:
    falhas = 0
    for nome, arquivos, config, regra, bloqueia in CASOS:
        rc, saida = roda(arquivos, config)
        ok = (regra in saida) == bloqueia and rc == (1 if bloqueia else 0) \
            and "Traceback" not in saida
        print(f"[{'OK ' if ok else 'ERR'}] {nome}")
        if not ok:
            falhas += 1
            print(saida[:600])
    for nome, caso in (("env.production no historico bloqueia", caso_env_no_historico),
                       ("env.example no historico passa", caso_env_example_no_historico),
                       ("pasta pai node_modules nao esconde o repo", caso_pasta_pai_node_modules),
                       ("nicho-dod: repo pai nao esconde segredo", caso_nicho_dod_repo_pai_ignora),
                       ("repo pai que ignora tudo nao esconde o setup", caso_repo_pai_que_ignora_tudo)):
        ok = caso()
        print(f"[{'OK ' if ok else 'ERR'}] {nome}")
        falhas += 0 if ok else 1
    print("-" * 50)
    if falhas:
        print(f"{falhas} falha(s).")
        return 1
    print("Smoke OK: site_publico libera só o previsto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
