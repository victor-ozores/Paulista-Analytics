import re

from comum import REF, ler_csv
from financeiro import texto_simples

ARQ_MOTIVOS = REF / "motivos_cartao.csv"
CONDICOES = ("texto", "resto")
COLUNAS = ("ordem_regra", "categoria", "ordem_exibicao", "condicao", "expressao", "explicacao")


def ler_regras_motivo(arq=ARQ_MOTIVOS):
    """Regras que agrupam os 113 textos livres de motivo de cartão da súmula em poucas categorias (arquivo de referência revisável)."""
    linhas = ler_csv(arq)
    if not linhas or not set(COLUNAS) <= set(linhas[0]):
        raise ValueError(f"{arq.name}: o arquivo precisa das colunas {', '.join(COLUNAS)} e de pelo menos uma regra")
    regras = []
    for i, l in enumerate(linhas, start=2):
        if not l["ordem_regra"].isdigit() or not l["ordem_exibicao"].isdigit() or not l["categoria"]:
            raise ValueError(f"{arq.name} linha {i}: ordem_regra e ordem_exibicao são números inteiros e categoria não pode ficar vazia")
        cond = l["condicao"]
        if cond not in CONDICOES:
            raise ValueError(f"{arq.name} linha {i}: condição '{cond}' desconhecida (use {', '.join(CONDICOES)})")
        if cond == "texto" and not l["expressao"]:
            raise ValueError(f"{arq.name} linha {i}: regra de texto sem expressão")
        if cond == "resto" and l["expressao"]:
            raise ValueError(f"{arq.name} linha {i}: a condição resto não usa expressão")
        try:
            padrao = re.compile(l["expressao"]) if cond == "texto" else None
        except re.error as erro:
            raise ValueError(f"{arq.name} linha {i}: expressão inválida ({erro})") from erro
        regras.append({"ordem_regra": int(l["ordem_regra"]), "categoria": l["categoria"], "ordem_exibicao": int(l["ordem_exibicao"]), "condicao": cond, "expressao": l["expressao"], "explicacao": l["explicacao"], "padrao": padrao})
    regras.sort(key=lambda r: r["ordem_regra"])
    if not regras or [r["condicao"] for r in regras].count("resto") != 1 or regras[-1]["condicao"] != "resto":
        raise ValueError(f"{arq.name}: a última regra (e só ela) deve ser a condição resto")
    for campo in ("ordem_regra", "categoria", "ordem_exibicao"):
        if len({r[campo] for r in regras}) != len(regras):
            raise ValueError(f"{arq.name}: {campo} repetido")
    return regras


def classificar_motivo(motivo, regras):
    """Primeira regra que casa com o texto (sem acento e em minúsculas); a última é o resto."""
    texto = texto_simples(motivo or "")
    for r in regras:
        if r["condicao"] == "texto" and r["padrao"].search(texto):
            return r
    return regras[-1]


def categorias_em_ordem(regras):
    return sorted(regras, key=lambda r: r["ordem_exibicao"])
