#!/usr/bin/env python3
"""Smoke da regra `no_internal_infra_leak`.

Trava os DOIS lados da calibração:

  BLOQUEIA  — marcador que só existe na máquina/operação do Rafael.
  PERMITE   — coisa que o ALUNO também tem/faz. Falso positivo aqui é pior
              que buraco: faz o dono do repo parar de confiar no validador
              e passar a ignorar o CI.

Rodar: python3 tests/smoke_infra_leak.py   (exit 0 = tudo certo)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATE = ROOT / "validate.py"
RULE = "no_internal_infra_leak"

# --- devem BLOQUEAR ------------------------------------------------------
BLOQUEIA = [
    ("supabase interno",   "url = 'https://pnfvlszwlumetdjsuktj.supabase.co'"),
    ("supabase hub",       "REF = 'hjcudhxizemxepffrmbw'"),
    ("webhook producao",   "POST https://webhook.integracoes-zx-lab.uk/webhook/x"),
    ("launcher do rafael", "ln -sfn $PROJ ~/.zxlab-sites/<alias>"),
    ("workspace openclaw", "ver ~/.openclaw/workspace/scripts/bom_dia.py"),
    ("conector asaas",     "eventos em ~/.asaas-connector/events.json"),
    ("porta do launcher",  "curl http://localhost:8891/demo/scene.html"),
    ("porta da MC api",    "curl http://localhost:8790/status"),
    ("slug de memoria",    "ver `feedback_youtube_cortes_masterclass` na memoria"),
    ("slug reference",     "detalhe em reference_awesome_design_md.md"),
    ("alvo de publicacao", "wrangler pages deploy ./docs --project-name zx-control-semana1"),
    ("lib bunny",          "subir MP4 no Bunny (lib `MasterClass ZX Control`)"),
    ("skill do operador",  "usar skill `upload-aulas-hub` depois de gravar"),
    ("skill de deploy",    "publicar via `/pages-deploy` quando aprovar"),
]

# --- NÃO podem bloquear (são do aluno) -----------------------------------
PERMITE = [
    ("config do aluno",      "salve a chave em ~/.operacao-ia/config/gemini.env"),
    ("mission control dele", "abra ~/.zxlab-mission-control/dashboard.html"),
    ("backup dele",          "backup automatico da memoria em ~/.zxlab-backup/"),
    ("codex automations",    "projeto de revisao em ~/.codex/automations/project-review/"),
    ("omniroute dele",       'OMNIROUTE_DEFAULT_URL = "http://localhost:8765"'),
    ("pasta de projeto",     "PROJ=~/projetos/<slug>/<subpasta>"),
    ("projeto proprio dele", "mkdir -p ~/projetos/minha-lp-nova"),
    ("wrangler generico",    "wrangler pages deploy ./dist"),
    ("skills do aluno",      "instaladas em ~/.claude/skills/: criar-reel, gerar-carrossel"),
    ("var_com_underscores",  "resultado_do_teste_final = calcular()"),
]


def viola(conteudo: str) -> bool:
    """True se a regra no_internal_infra_leak marcar este conteúdo."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "README.md").write_text("# repo\n", encoding="utf-8")
        (d / "CLAUDE.md").write_text("# claude\n", encoding="utf-8")
        (d / "MASTERCLASS.md").write_text(conteudo + "\n", encoding="utf-8")
        (d / "setup").mkdir()
        (d / "setup" / "check_prerequisites.py").write_text("print('ok')\n",
                                                            encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(VALIDATE), "--path", str(d)],
            capture_output=True, text=True, timeout=60,
        )
        return RULE in r.stdout + r.stderr


def main() -> int:
    falhas = 0
    for nome, texto in BLOQUEIA:
        if viola(texto):
            print(f"[OK ] bloqueia: {nome}")
        else:
            print(f"[ERR] DEVERIA bloquear e passou: {nome}\n       {texto}")
            falhas += 1
    for nome, texto in PERMITE:
        if not viola(texto):
            print(f"[OK ] permite: {nome}")
        else:
            print(f"[ERR] FALSO POSITIVO — é do aluno: {nome}\n       {texto}")
            falhas += 1
    print("-" * 50)
    if falhas:
        print(f"{falhas} falha(s).")
        return 1
    print("Smoke OK — calibração de no_internal_infra_leak preservada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
