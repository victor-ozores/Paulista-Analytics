"""Confere a planilha no Excel de verdade.

Abre o xlsx no Excel instalado (Windows, por COM), recalcula tudo, procura células com erro e linhas
que não deram OK. Com --salvar, grava a planilha recalculada (os valores passam a ficar guardados no
arquivo, para visualizadores que não calculam fórmulas).

Uso: python scripts/verificar_excel.py [--arquivo CAMINHO] [--salvar]
Saída: 0 = tudo confere; 1 = erro de fórmula ou divergência; 3 = Excel indisponível.
"""
import json
import subprocess
import sys
from pathlib import Path

from comum import RAIZ

PADRAO = RAIZ / "excel" / "Paulista_Analytics_conferencia_A1_2026.xlsx"
PS1 = Path(__file__).resolve().parent / "verificar_excel.ps1"


def excel_disponivel():
    if sys.platform != "win32":
        return False
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Excel.Application"))
        return True
    except OSError:
        return False


def verificar(arquivo=PADRAO, salvar=False):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1), "-Arquivo", str(arquivo)] + (["-Salvar"] if salvar else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    linhas = [l.lstrip("﻿") for l in (r.stdout or "").strip().splitlines() if l.lstrip("﻿").startswith("{")]
    if not linhas:
        raise RuntimeError(f"o Excel não devolveu resultado (código {r.returncode}): {(r.stdout or '')[-300:]} {(r.stderr or '')[-300:]}")
    res = json.loads(linhas[-1])
    if "falha" in res:
        raise RuntimeError(f"falha ao abrir ou calcular no Excel: {res['falha']}")
    for k in ("erros", "fora_do_ok"):
        if isinstance(res[k], str):
            res[k] = [res[k]]
    return res


def principal():
    arquivo = Path(sys.argv[sys.argv.index("--arquivo") + 1]) if "--arquivo" in sys.argv else PADRAO
    if not excel_disponivel():
        print("Excel não encontrado neste computador (precisa do Windows com Excel instalado).")
        return 3
    res = verificar(arquivo, "--salvar" in sys.argv)
    print(f"Excel {res['excel']} | conferências: {res['total']} | OK: {res['ok']} | erros de fórmula: {len(res['erros'])} | fora do OK: {len(res['fora_do_ok'])} | salvo: {res['salvo']}")
    for e in res["erros"][:20]:
        print("  ERRO", e)
    for e in res["fora_do_ok"][:20]:
        print("  FORA DO OK", e)
    return 0 if not res["erros"] and not res["fora_do_ok"] and res["total"] == res["ok"] else 1


if __name__ == "__main__":
    sys.exit(principal())
