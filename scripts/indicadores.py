"""Valores de referência dos indicadores (gabarito para as medidas DAX).

Definições em docs/dicionario_indicadores.md. Cada linha de data/processed/ref_indicadores.csv
traz um indicador (id_indicador), o escopo (geral, fase, faixa_minuto, clube, artilheiro, qualidade),
a chave dentro do escopo e o valor. Tudo sai das tabelas de data/processed/ e é recriável.
"""
import csv
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal

from classificacao import contagem_cartoes, tabela_primeira_fase
from comum import ler_csv

COLUNAS = ["id_indicador", "indicador", "escopo", "chave", "id_clube", "valor", "unidade"]
TIPOS_GOL = ("gol", "gol_penalti", "gol_falta", "gol_contra")
CARTAO = {"amarelo": "amarelo", "segundo_amarelo": "2o_amarelo", "vermelho": "vermelho"}
FAIXAS = [("01-15", 0, 15), ("16-30", 16, 30), ("31-45", 31, 45), ("46-60", 46, 60), ("61-75", 61, 75), ("76-90+", 76, 999)]
PRIMEIRA_FASE = "PRIMEIRA FASE"


def dec(x):
    return Decimal(x) if x not in ("", None) else None


def pct(a, b):
    return round(float(Decimal(a) * 100 / Decimal(b)), 4) if b else None


def media(soma, n):
    return round(float(Decimal(soma) / n), 4) if n else None


def dinheiro(d):
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def resultado(p):
    gm, gv = int(p["gols_mandante"]), int(p["gols_visitante"])
    return "M" if gm > gv else ("E" if gm == gv else "V")


def metricas(partidas, eventos):
    """Indicadores gerais (I01 a I26) para um conjunto de partidas e os eventos delas."""
    ids = {p["id_partida"] for p in partidas}
    ev = [e for e in eventos if e["id_partida"] in ids]
    n = len(partidas)
    gols = sum(int(p["gols_mandante"]) + int(p["gols_visitante"]) for p in partidas)
    res = Counter(resultado(p) for p in partidas)
    publico = [int(p["publico_boletim"]) for p in partidas]
    pagantes = sum(int(p["publico_pagante"]) for p in partidas)
    bruta = sum((dec(p["renda_bruta"]) for p in partidas), Decimal(0))
    liquida = sum((dec(p["renda_liquida"]) for p in partidas), Decimal(0))
    cart = contagem_cartoes([{"equipe_id": e["id_clube"], "cartao": CARTAO[e["tipo_evento"]]} for e in ev if e["tipo_evento"] in CARTAO])
    amarelos, vermelhos = sum(v[0] for v in cart.values()), sum(v[1] for v in cart.values())
    acresc = [int(p["acrescimo_1t_min"]) + int(p["acrescimo_2t_min"]) for p in partidas if p["acrescimo_1t_min"] != "" and p["acrescimo_2t_min"] != ""]
    m = {
        ("I01", "jogos", ""): (n, "jogos"),
        ("I02", "gols", ""): (gols, "gols"),
        ("I03", "gols_por_jogo", ""): (media(gols, n), "gols/jogo"),
        ("I04", "vitorias_mandante", ""): (res["M"], "jogos"),
        ("I05", "empates", ""): (res["E"], "jogos"),
        ("I06", "vitorias_visitante", ""): (res["V"], "jogos"),
        ("I07", "pct_vitorias_mandante", ""): (pct(res["M"], n), "%"),
        ("I08", "pct_empates", ""): (pct(res["E"], n), "%"),
        ("I09", "pct_vitorias_visitante", ""): (pct(res["V"], n), "%"),
        ("I10", "publico_total", ""): (sum(publico), "pessoas"),
        ("I11", "publico_medio", ""): (media(sum(publico), n), "pessoas/jogo"),
        ("I12", "publico_maximo", ""): (max(publico) if publico else None, "pessoas"),
        ("I13", "publico_minimo", ""): (min(publico) if publico else None, "pessoas"),
        ("I14", "publico_pagante", ""): (pagantes, "pessoas"),
        ("I15", "pct_pagantes", ""): (pct(pagantes, sum(publico)), "%"),
        ("I16", "renda_bruta", ""): (dinheiro(bruta), "R$"),
        ("I17", "renda_liquida", ""): (dinheiro(liquida), "R$"),
        ("I18", "ticket_medio", ""): (dinheiro(bruta / pagantes) if pagantes else None, "R$/pagante"),
        ("I19", "jogos_renda_liquida_negativa", ""): (sum(1 for p in partidas if dec(p["renda_liquida"]) < 0), "jogos"),
        ("I20", "amarelos", ""): (amarelos, "cartões"),
        ("I21", "vermelhos", ""): (vermelhos, "cartões"),
        ("I22", "cartoes_por_jogo", ""): (media(amarelos + vermelhos, n), "cartões/jogo"),
        ("I23", "acrescimo_medio_min", ""): (media(sum(acresc), len(acresc)), "min/jogo"),
        ("I25", "gols_de_penalti", ""): (sum(1 for e in ev if e["tipo_evento"] == "gol_penalti"), "gols"),
        ("I26", "jogos_sem_gols", ""): (sum(1 for p in partidas if int(p["gols_mandante"]) + int(p["gols_visitante"]) == 0), "jogos"),
    }
    return m


def metricas_financeiro_elenco(partidas, ingressos, despesas, rateio, escalacao, substituicoes):
    """Indicadores do financeiro e do elenco (I38 a I44 do financeiro e I55 a I59 do elenco) para um conjunto de partidas.

    Despesas, torcida visitante, deduções e líquido a receber saem das tabelas de detalhe do boletim (fato_ingresso,
    fato_despesa, fato_rateio); a despesa total do gabarito vem de `despesas_total` da partida (outro caminho, para a
    medida DAX, que soma as rubricas, ser conferida contra um número que não passa pelas mesmas linhas)."""
    ids = {p["id_partida"] for p in partidas}
    ing = [x for x in ingressos if x["id_partida"] in ids]
    rat = [x for x in rateio if x["id_partida"] in ids]
    esc = [x for x in escalacao if x["id_partida"] in ids]
    publico = sum(int(p["publico_boletim"]) for p in partidas)
    bruta = sum((dec(p["renda_bruta"]) for p in partidas), Decimal(0))
    desp = sum((dec(p["despesas_total"]) for p in partidas), Decimal(0))
    visitante = sum(int(x["ingressos"]) for x in ing if x["setor_visitante"] == "1")
    deducoes = sum((dec(r["deducao_inss"]) + dec(r["deducao_outras"]) for r in rat), Decimal(0))
    liquido = sum((dec(r["liquido"]) for r in rat), Decimal(0))
    em_campo = [e for e in esc if e["jogou"] == "1"]
    return {
        ("I38", "despesas", ""): (dinheiro(desp), "R$"),
        ("I39", "pct_despesas_renda_bruta", ""): (pct(desp, bruta), "%"),
        ("I40", "despesa_por_ingresso", ""): (dinheiro(desp / publico) if publico else None, "R$/ingresso"),
        ("I41", "ingressos_setor_visitante", ""): (visitante, "ingressos"),
        ("I42", "pct_torcida_visitante", ""): (pct(visitante, publico), "%"),
        ("I43", "deducoes", ""): (dinheiro(deducoes), "R$"),
        ("I44", "liquido_a_receber", ""): (dinheiro(liquido), "R$"),
        ("I55", "atletas_em_campo", ""): (len(em_campo), "atletas-jogo"),
        ("I56", "titulares", ""): (sum(1 for e in esc if e["situacao"] == "titular"), "atletas-jogo"),
        ("I57", "reservas_que_entraram", ""): (sum(1 for e in em_campo if e["situacao"] == "reserva"), "atletas-jogo"),
        ("I58", "substituicoes", ""): (sum(1 for s in substituicoes if s["id_partida"] in ids), "substituições"),
        ("I59", "gols_de_reservas", ""): (sum(int(e["gols"]) for e in esc if e["situacao"] == "reserva"), "gols"),
    }


def faixas_minuto(eventos):
    c = Counter()
    for e in eventos:
        if e["tipo_evento"] in TIPOS_GOL and e["minuto"] != "":
            mi = int(e["minuto"])
            c[next(nome for nome, a, b in FAIXAS if a <= mi <= b)] += 1
    return c


def calcular(proc):
    partidas = ler_csv(proc / "fato_partida.csv")
    eventos = ler_csv(proc / "fato_evento.csv")
    clubes = {c["id_clube"]: c["nome_popular"] for c in ler_csv(proc / "dim_clube.csv")}
    fases = {f["id_fase"]: f["nome_fase"] for f in ler_csv(proc / "dim_fase.csv")}
    ingressos, despesas, rateio = (ler_csv(proc / f"{n}.csv") for n in ("fato_ingresso", "fato_despesa", "fato_rateio"))
    escalacao, substituicoes = ler_csv(proc / "fato_escalacao.csv"), ler_csv(proc / "fato_substituicao.csv")
    linhas = []

    def add(ind, nome, escopo, chave, valor, unidade, id_clube=""):
        linhas.append({"id_indicador": ind, "indicador": nome, "escopo": escopo, "chave": chave, "id_clube": id_clube, "valor": valor, "unidade": unidade})

    def novas(sub):
        return metricas_financeiro_elenco(sub, ingressos, despesas, rateio, escalacao, substituicoes)

    for (ind, nome, _), (valor, un) in {**metricas(partidas, eventos), **novas(partidas)}.items():
        add(ind, nome, "geral", "", valor, un)
    for id_fase, nome_fase in fases.items():
        sub = [p for p in partidas if p["id_fase"] == id_fase]
        for (ind, nome, _), (valor, un) in {**metricas(sub, eventos), **novas(sub)}.items():
            add(ind, nome, "fase", nome_fase, valor, un)
    fx = faixas_minuto(eventos)
    for nome_faixa, _, _ in FAIXAS:
        add("I24", "gols_por_faixa_minuto", "faixa_minuto", nome_faixa, fx[nome_faixa], "gols")

    # Por clube (todas as fases) e classificação da 1ª fase pelo Art. 16
    fase_partida = {p["id_partida"]: fases[p["id_fase"]] for p in partidas}
    primeira = [p for p in partidas if fase_partida[p["id_partida"]] == PRIMEIRA_FASE]
    cart1 = contagem_cartoes([{"equipe_id": e["id_clube"], "cartao": CARTAO[e["tipo_evento"]]} for e in eventos if e["tipo_evento"] in CARTAO and fase_partida[e["id_partida"]] == PRIMEIRA_FASE])
    tab = {l["id_clube"]: l for l in tabela_primeira_fase(primeira, cart1)}
    cart_todos = contagem_cartoes([{"equipe_id": e["id_clube"], "cartao": CARTAO[e["tipo_evento"]]} for e in eventos if e["tipo_evento"] in CARTAO])
    for idc in sorted(clubes, key=lambda i: clubes[i]):
        nome = clubes[idc]
        jogos = [p for p in partidas if idc in (p["id_clube_mandante"], p["id_clube_visitante"])]
        gp = sum(int(p["gols_mandante"]) if p["id_clube_mandante"] == idc else int(p["gols_visitante"]) for p in jogos)
        gc = sum(int(p["gols_visitante"]) if p["id_clube_mandante"] == idc else int(p["gols_mandante"]) for p in jogos)
        casa = [int(p["publico_boletim"]) for p in partidas if p["id_clube_mandante"] == idc]
        am, ve = cart_todos.get(idc, (0, 0))
        add("I01", "jogos", "clube", nome, len(jogos), "jogos", idc)
        add("I27", "gols_pro", "clube", nome, gp, "gols", idc)
        add("I28", "gols_contra", "clube", nome, gc, "gols", idc)
        add("I20", "amarelos", "clube", nome, am, "cartões", idc)
        add("I21", "vermelhos", "clube", nome, ve, "cartões", idc)
        add("I32", "publico_medio_como_mandante", "clube", nome, media(sum(casa), len(casa)), "pessoas/jogo", idc)
        em_casa = [p for p in partidas if p["id_clube_mandante"] == idc]
        ids_casa, ids_fora = {p["id_partida"] for p in em_casa}, {p["id_partida"] for p in partidas if p["id_clube_visitante"] == idc}
        add("I44", "liquido_a_receber", "clube", nome, dinheiro(sum((dec(r["liquido"]) for r in rateio if r["id_clube"] == idc), Decimal(0))), "R$", idc)
        add("I51", "renda_bruta_como_mandante", "clube", nome, dinheiro(sum((dec(p["renda_bruta"]) for p in em_casa), Decimal(0))), "R$", idc)
        add("I52", "renda_liquida_como_mandante", "clube", nome, dinheiro(sum((dec(p["renda_liquida"]) for p in em_casa), Decimal(0))), "R$", idc)
        add("I53", "torcida_visitante_recebida", "clube", nome, sum(int(x["ingressos"]) for x in ingressos if x["id_partida"] in ids_casa and x["setor_visitante"] == "1"), "ingressos", idc)
        add("I54", "torcida_visitante_levada", "clube", nome, sum(int(x["ingressos"]) for x in ingressos if x["id_partida"] in ids_fora and x["setor_visitante"] == "1"), "ingressos", idc)
        if idc in tab:
            add("I29", "pontos_primeira_fase", "clube", nome, tab[idc]["pontos"], "pontos", idc)
            add("I30", "aproveitamento_primeira_fase", "clube", nome, pct(tab[idc]["pontos"], 3 * tab[idc]["jogos"]), "%", idc)
            add("I31", "posicao_primeira_fase", "clube", nome, tab[idc]["posicao"], "posição", idc)

    # Artilharia: gols do atleta pelo próprio clube (gol contra não conta para o artilheiro)
    art = Counter()
    for e in eventos:
        if e["tipo_evento"] in ("gol", "gol_penalti", "gol_falta"):
            art[(e["pessoa"], e["id_clube"])] += 1
    for (pessoa, idc), n in sorted(art.items(), key=lambda kv: (-kv[1], kv[0][0])):
        add("I33", "gols_artilheiro", "artilheiro", pessoa, n, "gols", idc)

    # Financeiro por categoria de ingresso, grupo de despesa e bloco do boletim (categorias e grupos são classificação do projeto)
    por_cat = defaultdict(lambda: [0, Decimal(0)])
    ordem_cat = {}
    for x in ingressos:
        por_cat[x["categoria"]][0] += int(x["ingressos"])
        por_cat[x["categoria"]][1] += dec(x["arrecadacao"])
        ordem_cat[x["categoria"]] = int(x["ordem_categoria"])
    total_ing = sum(v[0] for v in por_cat.values())
    total_arr = sum((v[1] for v in por_cat.values()), Decimal(0))
    for cat in sorted(por_cat, key=lambda c: ordem_cat[c]):
        q, r = por_cat[cat]
        add("I45", "ingressos_vendidos", "categoria", cat, q, "ingressos")
        add("I46", "arrecadacao_ingressos", "categoria", cat, dinheiro(r), "R$")
        add("I47", "preco_medio_ingresso", "categoria", cat, dinheiro(r / q) if q else None, "R$/ingresso")
        add("I48", "pct_ingressos", "categoria", cat, pct(q, total_ing), "%")
        add("I49", "pct_arrecadacao", "categoria", cat, pct(r, total_arr), "%")
    por_grupo, por_bloco = defaultdict(Decimal), defaultdict(Decimal)
    for d in despesas:
        por_grupo[d["grupo"]] += dec(d["valor"])
        por_bloco[d["bloco_codigo"]] += dec(d["valor"])
    total_desp = sum(por_grupo.values(), Decimal(0))
    for g in sorted(por_grupo, key=lambda k: (-por_grupo[k], k)):
        add("I38", "despesas", "grupo_despesa", g, dinheiro(por_grupo[g]), "R$")
        add("I50", "pct_despesas", "grupo_despesa", g, pct(por_grupo[g], total_desp), "%")
    for b in sorted(por_bloco):
        add("I38", "despesas", "bloco", b, dinheiro(por_bloco[b]), "R$")
        add("I50", "pct_despesas", "bloco", b, pct(por_bloco[b], total_desp), "%")

    # Qualidade dos dados (depende de 05_validar.py ter gravado o log)
    res_arq, log_arq = proc / "resultado_regra.csv", proc / "fato_inconsistencia.csv"
    if res_arq.exists() and log_arq.exists():
        res, log = ler_csv(res_arq), ler_csv(log_arq)
        st = Counter(x["status"] for x in log)
        add("I34", "regras_executadas", "qualidade", "", len(res), "regras")
        add("I35", "regras_sem_ocorrencia", "qualidade", "", sum(1 for r in res if r["resultado"] == "ok"), "regras")
        add("I36", "inconsistencias_abertas", "qualidade", "", st["aberta"], "ocorrências")
        add("I37", "inconsistencias_explicadas", "qualidade", "", st["explicada"] + st["aceita"] + st["corrigida"], "ocorrências")
    return linhas


def gravar(linhas, arq):
    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return format(v, ".4f").rstrip("0").rstrip(".")
        return str(v)

    with open(arq, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, delimiter=";", lineterminator="\n")
        w.writeheader()
        for l in linhas:
            w.writerow({**l, "valor": fmt(l["valor"])})
