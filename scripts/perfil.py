"""Perfil das tabelas processadas: linhas, colunas, preenchimento e valores distintos."""
from datetime import datetime

from comum import ler_csv


def perfil_tabela(linhas):
    colunas = list(linhas[0]) if linhas else []
    out = []
    for col in colunas:
        valores = [l[col] for l in linhas]
        cheios = [v for v in valores if v != ""]
        out.append({"coluna": col, "preenchidos": len(cheios), "vazios": len(valores) - len(cheios), "distintos": len(set(cheios)), "exemplo": cheios[0] if cheios else ""})
    return out


def escrever_perfil(pasta, destino):
    L = ["# Perfil das tabelas processadas", "",
         f"Gerado por `scripts/05_validar.py` em {datetime.now():%d/%m/%Y}. Para cada tabela de `data/processed/`: quantas linhas, e por coluna quantas estão preenchidas, quantas vazias e quantos valores distintos há. Vazio nem sempre é erro (ex.: `penaltis_mandante` só existe em jogo decidido nos pênaltis); o que merece atenção vira regra em `scripts/regras.py` (A32).", ""]
    for arq in sorted(pasta.glob("*.csv")):
        if arq.stem in ("fato_inconsistencia", "resultado_regra", "ref_indicadores", "aux_config"):
            continue
        linhas = ler_csv(arq)
        L += [f"## {arq.stem} ({len(linhas)} linhas)", "", "| Coluna | Preenchidos | Vazios | Distintos | Exemplo |", "|---|---|---|---|---|"]
        for p in perfil_tabela(linhas):
            ex = "(omitido)" if p["coluna"] in ("registro", "registros") else p["exemplo"].replace("|", "/").replace("\n", " ")
            L.append(f"| {p['coluna']} | {p['preenchidos']} | {p['vazios']} | {p['distintos']} | {ex[:40]} |")
        L.append("")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
