"""Roda as regras de conferência e grava o log de inconsistências.

Entradas : data/processed/, data/referencia/ e data/raw/espn/
Decisões : data/referencia/inconsistencias_decisoes.csv (status e explicação, versionado)
Saídas   : data/processed/fato_inconsistencia.csv, resultado_regra.csv e ref_indicadores.csv,
           docs/auditoria/auditoria_a1_2026.md e docs/auditoria/perfil_tabelas.md

Uso: python scripts/05_validar.py [--estrito]   (--estrito: sai com erro se restar inconsistência aberta)
"""
import csv
import sys
from collections import Counter
from datetime import datetime

from comum import RAIZ, REF, ler_csv
from indicadores import calcular, gravar
from perfil import escrever_perfil
from regras import PROC, REGRAS, Contexto

DECISOES = REF / "inconsistencias_decisoes.csv"
AUDITORIA = RAIZ / "docs" / "auditoria"
STATUS = ("aberta", "explicada", "corrigida", "aceita")
SEVERIDADES = ("alta", "media", "baixa")
COLUNAS_LOG = ["id_inconsistencia", "codigo_regra", "titulo_regra", "id_partida", "numero_jogo", "id_clube", "fonte_a", "valor_a", "fonte_b", "valor_b", "detalhe", "severidade", "status", "explicacao"]


def ler_decisoes():
    if not DECISOES.exists():
        return []
    ds = ler_csv(DECISOES)
    colunas = {"codigo_regra", "id_partida", "id_clube", "fonte_a", "status", "severidade", "explicacao"}
    if ds and set(ds[0]) != colunas:
        raise ValueError(f"{DECISOES.name}: colunas esperadas {sorted(colunas)}, encontradas {sorted(ds[0])}")
    for i, d in enumerate(ds, start=2):
        if d["status"] not in STATUS:
            raise ValueError(f"{DECISOES.name} linha {i}: status '{d['status']}' inválido (use {STATUS})")
        if d["severidade"] and d["severidade"] not in SEVERIDADES:
            raise ValueError(f"{DECISOES.name} linha {i}: severidade '{d['severidade']}' inválida (use {SEVERIDADES})")
        if d["status"] != "aberta" and not d["explicacao"].strip():
            raise ValueError(f"{DECISOES.name} linha {i}: decisão '{d['status']}' sem explicação")
    return ds


def casa(decisao, oc, codigo):
    """Pontuação de especificidade da decisão para a ocorrência (None se não se aplica)."""
    if decisao["codigo_regra"] != codigo:
        return None
    pontos = 0
    for campo in ("id_partida", "id_clube", "fonte_a"):
        v = decisao[campo]
        if v in ("*", ""):
            continue
        if str(oc[campo] if oc[campo] is not None else "") != v:
            return None
        pontos += 1
    return pontos


def validar():
    c = Contexto()
    decisoes = ler_decisoes()
    usadas = Counter()
    log, resultados = [], []
    for r in REGRAS:
        verificados, ocorrencias, resumo = r["funcao"](c)
        for seq, oc in enumerate(ocorrencias, start=1):
            melhor = None
            for i, d in enumerate(decisoes):
                p = casa(d, oc, r["codigo"])
                if p is not None and (melhor is None or p > melhor[0]):
                    melhor = (p, i, d)
            status, explicacao, severidade = "aberta", "", r["severidade"]
            if melhor:
                usadas[melhor[1]] += 1
                _, _, d = melhor
                status, explicacao, severidade = d["status"], d["explicacao"], d["severidade"] or severidade
            log.append({"id_inconsistencia": f"{r['codigo']}-{seq:03d}", "codigo_regra": r["codigo"], "titulo_regra": r["titulo"], **{k: ("" if oc[k] is None else oc[k]) for k in ("id_partida", "numero_jogo", "id_clube", "fonte_a", "valor_a", "fonte_b", "valor_b", "detalhe")}, "severidade": severidade, "status": status, "explicacao": explicacao})
        do_codigo = [x for x in log if x["codigo_regra"] == r["codigo"]]
        cont = Counter(x["status"] for x in do_codigo)
        if r["info"]:
            res = "info"
        elif not do_codigo:
            res = "ok"
        elif cont["aberta"]:
            res = "aberta"
        else:
            res = "explicada"
        resultados.append({"codigo": r["codigo"], "titulo": r["titulo"], "severidade": r["severidade"], "verificados": verificados, "ocorrencias": len(do_codigo), "abertas": cont["aberta"], "explicadas": cont["explicada"], "corrigidas": cont["corrigida"], "aceitas": cont["aceita"], "resultado": res, "resumo": resumo})
    sem_uso = [d for i, d in enumerate(decisoes) if usadas[i] == 0]
    return log, resultados, sem_uso


def gravar_csv(arq, colunas, linhas):
    with open(arq, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas, delimiter=";", lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)


def texto(v):
    return str(v).replace("|", "/").replace("\n", " ")


def escrever_relatorio(log, resultados, sem_uso):
    cont = Counter(r["resultado"] for r in resultados)
    rot = {"ok": "OK", "explicada": "EXPLICADA", "aberta": "ABERTA", "info": "INFO"}
    L = ["# Auditoria e validação: Paulistão A1 2026", "",
         f"Gerado por `scripts/05_validar.py` em {datetime.now():%d/%m/%Y}. Cada regra compara duas fontes ou checa uma propriedade dos dados e registra cada ocorrência em `data/processed/fato_inconsistencia.csv`. As decisões do autor ficam em `data/referencia/inconsistencias_decisoes.csv`.", "",
         f"**Resumo:** {len(resultados)} regras: {cont['ok']} ok, {cont['explicada']} com divergência explicada, {cont['aberta']} com divergência aberta, {cont['info']} informativa(s). {len(log)} ocorrência(s) no log, {sum(1 for x in log if x['status'] == 'aberta')} aberta(s).", "",
         "| Código | Verificação | Resultado | Ocorrências | Detalhe |", "|---|---|---|---|---|"]
    for r in resultados:
        L.append(f"| {r['codigo']} | {texto(r['titulo'])} | {rot[r['resultado']]} | {r['ocorrencias']} | {texto(r['resumo'])} |")
    L.append("")
    por_regra = {}
    for x in log:
        por_regra.setdefault(x["codigo_regra"], []).append(x)
    for r in resultados:
        itens = por_regra.get(r["codigo"], [])
        if not itens:
            continue
        L += [f"## {r['codigo']}: {r['titulo']}", ""]
        for expl in sorted({x["explicacao"] for x in itens if x["explicacao"]}):
            L += [f"**Decisão:** {expl}", ""]
        for x in itens[:40]:
            quem = f"jogo {x['numero_jogo']}" if x["numero_jogo"] != "" else (f"clube {x['id_clube']}" if x["id_clube"] != "" else "geral")
            L.append(f"- `{x['id_inconsistencia']}` [{x['status']}] {quem}: {texto(x['fonte_a'])} = {texto(x['valor_a'])}; {texto(x['fonte_b'])} = {texto(x['valor_b'])}" + (f" ({texto(x['detalhe'])})" if x["detalhe"] != "" else ""))
        if len(itens) > 40:
            L.append(f"- ... e mais {len(itens) - 40} (ver `fato_inconsistencia.csv`)")
        L.append("")
    if sem_uso:
        L += ["## Decisões sem ocorrência", "", "Estas decisões de `inconsistencias_decisoes.csv` não casam com nenhuma ocorrência atual (o dado pode ter sido corrigido). Revise e remova se não valerem mais:", ""]
        L += [f"- {d['codigo_regra']} partida={d['id_partida']} clube={d['id_clube']} fonte_a={d['fonte_a']} [{d['status']}]" for d in sem_uso]
        L.append("")
    AUDITORIA.mkdir(parents=True, exist_ok=True)
    (AUDITORIA / "auditoria_a1_2026.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


def principal():
    log, resultados, sem_uso = validar()
    gravar_csv(PROC / "fato_inconsistencia.csv", COLUNAS_LOG, log)
    gravar_csv(PROC / "resultado_regra.csv", list(resultados[0]), resultados)
    escrever_relatorio(log, resultados, sem_uso)
    ref = calcular(PROC)
    gravar(ref, PROC / "ref_indicadores.csv")
    escrever_perfil(PROC, AUDITORIA / "perfil_tabelas.md")
    rot = {"ok": "OK  ", "explicada": "EXPL", "aberta": "ABER", "info": "INFO"}
    for r in resultados:
        print(rot[r["resultado"]], r["codigo"], f"{r['ocorrencias']:>3} oc.", r["titulo"][:70], "->", r["resumo"][:90])
    cont = Counter(r["resultado"] for r in resultados)
    abertas = sum(1 for x in log if x["status"] == "aberta")
    print(f"\n{len(resultados)} regras: {cont['ok']} ok | {cont['explicada']} explicadas | {cont['aberta']} abertas | {cont['info']} info; {len(log)} ocorrências ({abertas} abertas)")
    for d in sem_uso:
        print("AVISO decisão sem ocorrência:", d["codigo_regra"], d["id_partida"], d["id_clube"])
    return 1 if (abertas and "--estrito" in sys.argv) else 0


if __name__ == "__main__":
    sys.exit(principal())
