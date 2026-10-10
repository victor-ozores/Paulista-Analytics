from collections import Counter, defaultdict


def contagem_cartoes(registros):
    """Regra da FPF validada contra a tabela oficial (30 de 30 combinações).

    registros: dicts com `equipe_id` e `cartao` em {'amarelo', '2o_amarelo', 'vermelho'}.
    Amarelos = todas as advertências (atletas e comissão técnica) menos os segundos amarelos.
    Vermelhos = vermelhos diretos mais os segundos amarelos.
    """
    brutos = defaultdict(Counter)
    for r in registros:
        brutos[r["equipe_id"]][r["cartao"]] += 1
    return {k: (c["amarelo"] - c["2o_amarelo"], c["vermelho"] + c["2o_amarelo"]) for k, c in brutos.items()}


def tabela_primeira_fase(partidas, cartoes=None):
    """Classificação da 1ª fase pelo Art. 16 do regulamento (A1 2026).

    Ordem: pontos, vitórias, saldo de gols, gols marcados, menos vermelhos, menos amarelos, sorteio.
    partidas: dicts com id_clube_mandante, id_clube_visitante, gols_mandante, gols_visitante.
    cartoes: {id_clube: (amarelos, vermelhos)}.
    """
    cartoes = cartoes or {}
    t = defaultdict(lambda: dict(jogos=0, vitorias=0, empates=0, derrotas=0, gols_pro=0, gols_contra=0, pontos=0))
    for p in partidas:
        gm, gv = int(p["gols_mandante"]), int(p["gols_visitante"])
        for clube, gf, gc in ((p["id_clube_mandante"], gm, gv), (p["id_clube_visitante"], gv, gm)):
            r = t[clube]
            r["jogos"] += 1
            r["gols_pro"] += gf
            r["gols_contra"] += gc
            if gf > gc:
                r["vitorias"] += 1
                r["pontos"] += 3
            elif gf == gc:
                r["empates"] += 1
                r["pontos"] += 1
            else:
                r["derrotas"] += 1
    linhas = []
    for clube, r in t.items():
        am, ve = cartoes.get(clube, (0, 0))
        linhas.append({"id_clube": clube, **r, "saldo": r["gols_pro"] - r["gols_contra"], "amarelos": am, "vermelhos": ve, "aproveitamento": round(r["pontos"] / (3 * r["jogos"]), 4) if r["jogos"] else 0.0})
    chave = lambda l: (-l["pontos"], -l["vitorias"], -l["saldo"], -l["gols_pro"], l["vermelhos"], l["amarelos"])
    linhas.sort(key=lambda l: (chave(l), str(l["id_clube"])))
    for i, l in enumerate(linhas, 1):
        l["posicao"] = i
    contagem = Counter(chave(l) for l in linhas)
    for l in linhas:
        l["empate_total"] = contagem[chave(l)] > 1
    return linhas
