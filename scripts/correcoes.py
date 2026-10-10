"""Correções documentadas sobre os eventos lidos das súmulas.

O dado bruto (PDF e `data/processed/fpf/`) nunca é alterado. Cada correção fica em
`data/referencia/correcoes_dados.csv` com a fonte e a justificativa, e é aplicada pelo
ETL (`04_tratar.py`) antes de numerar os eventos. A correção só vale se o valor original
ainda for o que está registrado: se a origem mudar, o ETL para e pede revisão.
"""
from comum import REF, ler_csv

ARQ_CORRECOES = REF / "correcoes_dados.csv"
COLUNAS = ["id_correcao", "numero_jogo", "tipo_evento", "pessoa", "campo", "valor_original", "valor_corrigido", "fontes", "justificativa"]
CAMPOS_SUPORTADOS = ("minuto",)


def ler_correcoes(arq=ARQ_CORRECOES):
    if not arq.exists():
        return []
    cs = ler_csv(arq)
    if cs and list(cs[0]) != COLUNAS:
        raise ValueError(f"{arq.name}: colunas esperadas {COLUNAS}, encontradas {list(cs[0])}")
    ids = [c["id_correcao"] for c in cs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{arq.name}: id_correcao repetido")
    for c in cs:
        if c["campo"] not in CAMPOS_SUPORTADOS:
            raise ValueError(f"{c['id_correcao']}: campo '{c['campo']}' não suportado (use {CAMPOS_SUPORTADOS})")
        if not c["fontes"].strip() or not c["justificativa"].strip():
            raise ValueError(f"{c['id_correcao']}: correção sem fonte ou sem justificativa")
    return cs


def aplicar_correcoes(brutos, correcoes):
    """Aplica as correções a `brutos` (lista de (numero_jogo, evento)); marca `id_correcao` em cada evento."""
    for _, ev in brutos:
        ev.setdefault("id_correcao", None)
    for c in correcoes:
        achados = [ev for n, ev in brutos if n == int(c["numero_jogo"]) and ev["tipo_evento"] == c["tipo_evento"] and c["pessoa"] in (ev["pessoa"] or "") and str(ev[c["campo"]]) == c["valor_original"]]
        if len(achados) != 1:
            raise ValueError(f"{c['id_correcao']}: esperava 1 evento com {c['campo']}={c['valor_original']} (jogo {c['numero_jogo']}, {c['tipo_evento']}, {c['pessoa']}), achei {len(achados)}. A origem mudou? Revise a correção.")
        ev = achados[0]
        ev[c["campo"]] = int(c["valor_corrigido"])
        ev["id_correcao"] = c["id_correcao"]
    return brutos
