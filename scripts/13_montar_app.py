"""Monta o dashboard com a barra de navegação e as oito telas: Visão geral, Duelo, Classificação e chave, Gols e artilharia, Disciplina e arbitragem, Jogos e escalações, Público e renda e Conferência e fontes.

Gera, a partir dos fragmentos em prototype/, as páginas que abrem direto no navegador:
  prototype/financeiro/index.html   a tela "Público e renda" sozinha
  prototype/visao_geral/index.html   a tela "Visão geral" sozinha
  prototype/gols/index.html          a tela "Gols e artilharia" sozinha
  prototype/disciplina/index.html    a tela "Disciplina e arbitragem" sozinha
  prototype/jogos/index.html         a tela "Jogos e escalações" sozinha
  prototype/classificacao/index.html a tela "Classificação e chave" sozinha
  prototype/conferencia/index.html  a tela "Conferência e fontes" sozinha
  prototype/app/index.html          a barra de navegação com as oito telas (Visão geral, Duelo, Classificação, Gols, Disciplina, Jogos, Público e renda e Conferência)
  prototype/app/sandbox.html        a mesma página dentro de um iframe com sandbox, como o visual HTML Content
Os fragmentos são a fonte; as páginas geradas não vão para o git. Os números da tela vêm de data/processed/ e o
script confere o que repete o gabarito (ref_indicadores.csv) e para se algo não bater.

Uso: python scripts/13_montar_app.py
"""
import datetime
import html
import importlib.util
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from classificacao import contagem_cartoes, tabela_primeira_fase
from comum import RAIZ, ler_csv
from disciplina import categorias_em_ordem, classificar_motivo, ler_regras_motivo
from financeiro import SEM_GRUPO, BLOCOS, ler_regras_ingresso
from indicadores import CARTAO
from nomes import curto_por_pessoa, nome_de_comissao

PROC = RAIZ / "data" / "processed"
PROTO = RAIZ / "prototype"
COR_CATEGORIA = {"Inteira": "#ffd166", "Meia-entrada": "#4cc9f0", "Sócio-torcedor": "#2fd47a", "Cadeira e camarote": "#b388ff", "Gratuidade por lei": "#9aa6b8", "Outros": "#5b6679"}
FASE_COD = {"PRIMEIRA FASE": 1, "QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}


def modulo_versus():
    spec = importlib.util.spec_from_file_location("montar_versus", Path(__file__).resolve().parent / "11_montar_versus.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("montar_versus", m)
    spec.loader.exec_module(m)
    return m


def centavos(v):
    return int((Decimal(v) * 100).to_integral_value())


def montar_dados_fin(versus=None):
    versus = versus or modulo_versus().montar_dados()
    clubes = {c["id"]: c for c in versus["clubes"]}
    partidas = sorted(ler_csv(PROC / "fato_partida.csv"), key=lambda p: (p["data_hora_programada"], int(p["numero_jogo"])))
    fases = {f["id_fase"]: f["nome_fase"] for f in ler_csv(PROC / "dim_fase.csv")}
    estadios = {e["id_estadio"]: e for e in ler_csv(PROC / "dim_estadio.csv")}
    ingressos, despesas, rateio = (ler_csv(PROC / f"{n}.csv") for n in ("fato_ingresso", "fato_despesa", "fato_rateio"))
    regras_ing = sorted(ler_regras_ingresso(), key=lambda r: r["ordem_exibicao"])
    categorias = [{"n": r["categoria"], "c": COR_CATEGORIA.get(r["categoria"], "#9aa6b8"), "t": r["explicacao"]} for r in regras_ing]
    idx_cat = {r["categoria"]: i for i, r in enumerate(regras_ing)}

    total_grupo = defaultdict(int)
    total_rubrica = defaultdict(int)
    grupo_da_rubrica, bloco_da_rubrica = {}, {}
    for d in despesas:
        v = centavos(d["valor"])
        total_grupo[d["grupo"]] += v
        total_rubrica[d["rubrica"]] += v
        grupo_da_rubrica[d["rubrica"]] = d["grupo"]
        bloco_da_rubrica[d["rubrica"]] = d["bloco_codigo"]
    grupos = sorted(total_grupo, key=lambda g: (g == SEM_GRUPO, -total_grupo[g], g))
    idx_grupo = {g: i for i, g in enumerate(grupos)}
    rubricas = sorted(total_rubrica, key=lambda r: (-total_rubrica[r], r))
    idx_rub = {r: i for i, r in enumerate(rubricas)}
    codigos_bloco = list(BLOCOS)

    por_jogo = defaultdict(lambda: {"ci": [0] * len(categorias), "cr": [0] * len(categorias), "vi": 0, "vr": 0, "gd": [0] * len(grupos), "bd": [0, 0, 0], "ru": defaultdict(int), "dd": 0, "lq": 0})
    for i in ingressos:
        a = por_jogo[i["id_partida"]]
        k = idx_cat[i["categoria"]]
        a["ci"][k] += int(i["ingressos"])
        a["cr"][k] += centavos(i["arrecadacao"])
        if i["setor_visitante"] == "1":
            a["vi"] += int(i["ingressos"])
            a["vr"] += centavos(i["arrecadacao"])
    for d in despesas:
        a = por_jogo[d["id_partida"]]
        v = centavos(d["valor"])
        a["gd"][idx_grupo[d["grupo"]]] += v
        a["bd"][codigos_bloco.index(d["bloco_codigo"])] += v
        a["ru"][idx_rub[d["rubrica"]]] += v
    for r in rateio:
        a = por_jogo[r["id_partida"]]
        a["dd"] += centavos(r["deducao_inss"]) + centavos(r["deducao_outras"])
        a["lq"] += centavos(r["liquido"])

    jogos = []
    for p in partidas:
        a = por_jogo[p["id_partida"]]
        est = estadios[p["id_estadio"]]
        jogos.append({
            "i": p["id_partida"], "n": int(p["numero_jogo"]), "f": FASE_COD[fases[p["id_fase"]]], "r": int(p["rodada"]), "d": p["data_jogo"], "h": p["hora_programada"],
            "m": p["id_clube_mandante"], "v": p["id_clube_visitante"], "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]),
            "e": est["nome_fpf"], "c": est["municipio"], "pu": int(p["publico_boletim"]), "pg": int(p["publico_pagante"]),
            "rb": centavos(p["renda_bruta"]), "ds": centavos(p["despesas_total"]), "rl": centavos(p["renda_liquida"]), "dd": a["dd"], "lq": a["lq"],
            "ci": a["ci"], "cr": a["cr"], "vi": a["vi"], "vr": a["vr"], "gd": a["gd"], "bd": a["bd"], "rb2": sorted([k, v] for k, v in a["ru"].items()),
        })

    saida_clubes = [{"id": c["id"], "nome": c["nome"], "curto": c["curto"], "sigla": c["sigla"], "cor": c["cor"]} for c in versus["clubes"]]
    meta = {k: versus["meta"][k] for k in ("jogos", "regras", "ok", "expl", "aber", "info", "ocorr", "ocorr_abertas")}
    dados = {
        "meta": meta, "cat": categorias, "grp": [{"n": g, "v": total_grupo[g]} for g in grupos], "blo": [{"c": c, "n": BLOCOS[c]} for c in codigos_bloco],
        "rub": [[r, idx_grupo[grupo_da_rubrica[r]], codigos_bloco.index(bloco_da_rubrica[r])] for r in rubricas], "clubes": saida_clubes, "jogos": jogos,
    }
    conferir_gabarito(dados)
    return dados


FONTES_CONF = [
    {"k": "o", "t": "Súmula: placar, gols, cartões, escalação", "f": "Súmula oficial da FPF", "d": "O PDF de cada jogo traz placar, gols, cartões, relação de jogadores, substituições, comissão técnica, arbitragem e horários. Os 72 PDFs foram lidos."},
    {"k": "o", "t": "Boletim: público, renda e despesas", "f": "Boletim financeiro oficial da FPF", "d": "O PDF de cada jogo traz os ingressos por setor e tipo, a renda, as despesas e a divisão da renda líquida. Os 72 boletins foram lidos linha a linha."},
    {"k": "o", "t": "Portal: jogos, datas e classificação", "f": "Portal da FPF", "d": "A tabela de jogos e a classificação oficial são a referência para conferir tudo o mais. O portal bloqueia robôs, então a captura é feita no navegador, por uma pessoa."},
    {"k": "o", "t": "Escudos e nomes dos clubes", "f": "FPF", "d": "Nomes oficiais e escudo de cada clube, baixados do cadastro da FPF. O escudo é marca registrada do clube."},
    {"k": "n", "t": "ESPN: estatísticas de time, sigla e cor", "f": "ESPN (não oficial)", "d": "Da ESPN vêm só posse de bola, finalizações, faltas e escanteios de cada time, as 15 cobranças da disputa de pênaltis do jogo 68 (o placar da disputa, 7 × 8, é o da súmula) e a sigla e a cor dos clubes, sempre rotuladas. O resto da ESPN serve apenas para conferir a FPF: quando as duas divergem, vale a FPF."},
    {"k": "p", "t": "Categorias de ingresso, grupos de despesa", "f": "Classificação do projeto", "d": "As seis categorias de ingresso e os dez grupos de despesa foram definidos pelo projeto a partir dos nomes que aparecem no boletim. O boletim só traz os três blocos de despesa."},
]
CAMADAS = [
    {"n": "Fontes entre si", "r": "{regras} regras", "d": "Súmula, boletim e tabela da FPF contra a ESPN e entre si, jogo a jogo. A fonte oficial manda quando há divergência.", "q": ""},
    {"n": "Tabelas tratadas", "r": "integridade e testes", "d": "O tratamento só termina se chaves, vínculos e totais fecharem, e testes automáticos repetem essa conferência a cada mudança no projeto.", "q": ""},
    {"n": "Planilha no Excel", "r": "610 de 610", "d": "Indicadores, classificação, artilharia, financeiro e elenco (inclusive jogo a jogo e time a time) recalculados com fórmulas do Excel (o programa real, não o Python) e comparados com a base: 610 conferências iguais. Defeitos colocados de propósito são detectados.", "q": "09/10/2026"},
    {"n": "Carga no Power BI", "r": "271 de 271 colunas", "d": "Em cada uma das 271 colunas das 23 tabelas do modelo aberto, a quantidade de valores e uma soma foram comparadas com as tabelas tratadas: todas iguais.", "q": "08/10/2026"},
    {"n": "Relacionamentos", "r": "39, sem caminho duplo", "d": "Os 39 relacionamentos do modelo existem como no desenho, sem valor órfão e sem dois caminhos ativos entre o mesmo par de tabelas.", "q": "08/10/2026"},
    {"n": "Medidas × gabarito", "r": "586 de 586 linhas", "d": "As 72 medidas do modelo calculam cada indicador e foram comparadas, linha a linha, com valores calculados à parte em Python: 586 de 586 iguais.", "q": "08/10/2026"},
    {"n": "Medidas × tabela FPF", "r": "16 de 16 clubes", "d": "A classificação da 1ª fase calculada pelas medidas contra a tabela oficial da FPF, em 11 critérios (posição, pontos, jogos, vitórias, empates, derrotas, gols pró e contra, saldo, amarelos e vermelhos): sem nenhuma diferença.", "q": "08/10/2026"},
    {"n": "Boletins × outro leitor", "r": "72 de 72 jogos", "d": "Os 72 boletins financeiros foram relidos por outro motor de PDF e por um analisador escrito à parte, com 10 conferências por jogo, e comparados com as tabelas do financeiro: 72 de 72.", "q": "08/10/2026"},
]
AMIGAVEL = [
    ("(correcoes_dados.csv)", "(lista de correções)"), ("em correcoes_dados.csv", "na lista de correções"), ("(PDF e sumula_gol.csv)", "(o PDF e os dados lidos dele)"),
    ("em fato_evento", "nos eventos"), ("em despesa_grupos.csv", "na lista de grupos de despesa"), ("dim_estadio.capacidade", "capacidade dos estádios"),
    ("citada em fonte_capacidade", "citada ao lado da capacidade"),
]
PROIBIDO_NA_TELA = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")


def amigavel(texto):
    for velho, novo in AMIGAVEL:
        texto = texto.replace(velho, novo)
    return texto


def limpar_resumo(texto):
    return amigavel(texto).replace("{", "").replace("}", "").replace("'", "")


def contagens_para_camadas():
    def carregar(nome, arq):
        spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent / arq)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    pq, rel, med, car = carregar("pq08", "08_gerar_powerquery.py"), carregar("rel09", "09_gerar_relacionamentos.py"), carregar("med10", "10_gerar_medidas.py"), carregar("car15", "15_conferir_carga_powerbi.py")
    return {"tabelas": len(pq.TABELAS), "colunas": len([c for c in car.colunas() if c[1] != "escudo_base64"]), "relacionamentos": len(rel.R), "medidas": len(med.M),
            "gabarito": len(ler_csv(PROC / "ref_indicadores.csv")), "clubes": len(ler_csv(PROC / "dim_clube.csv")), "jogos": len(ler_csv(PROC / "fato_partida.csv"))}


def montar_dados_conf():
    regras = ler_csv(PROC / "resultado_regra.csv")
    ocorr = ler_csv(PROC / "fato_inconsistencia.csv")
    cfg = {l["chave"]: l["valor"] for l in ler_csv(PROC / "aux_config.csv")}
    nome_clube = {c["id_clube"]: c["nome_popular"] for c in ler_csv(PROC / "dim_clube.csv")}
    jogo = {}
    for p in ler_csv(PROC / "fato_partida.csv"):
        jogo[p["numero_jogo"]] = f"Jogo {p['numero_jogo']}: {nome_clube[p['id_clube_mandante']]} {p['gols_mandante']} × {p['gols_visitante']} {nome_clube[p['id_clube_visitante']]}"
    textos, idx = [], {}
    saida_oc = []
    for o in ocorr:
        x = amigavel(o["explicacao"])
        if x not in idx:
            idx[x] = len(textos)
            textos.append(x)
        detalhe = amigavel(o["detalhe"])
        if o["id_clube"] and nome_clube[o["id_clube"]] not in detalhe:
            detalhe = (detalhe + " | " if detalhe else "") + nome_clube[o["id_clube"]]
        a = [amigavel(o["fonte_a"]), o["valor_a"]]
        b = [amigavel(o["fonte_b"]), o["valor_b"]]
        if o["fonte_b"] == "total":
            a, b = [a[0], f"{o['valor_a']} de {o['valor_b']}"], []
        saida_oc.append({"i": o["id_inconsistencia"], "r": o["codigo_regra"], "sv": o["severidade"], "st": o["status"], "a": a, "b": b, "d": detalhe,
                         "j": jogo.get(o["numero_jogo"], ""), "x": idx[x]})
    saida_reg = [{"c": r["codigo"], "t": amigavel(r["titulo"]), "s": r["severidade"], "v": int(r["verificados"]), "o": int(r["ocorrencias"]), "r": r["resultado"], "x": limpar_resumo(r["resumo"])} for r in regras]
    por_resultado = defaultdict(int)
    for r in regras:
        por_resultado[r["resultado"]] += 1
    por_status = defaultdict(int)
    for o in ocorr:
        por_status[o["status"]] += 1
    por_codigo = {r["codigo"]: r for r in regras}
    placar, classif = por_codigo["A22"], por_codigo["A19"]
    meta = {"regras": len(regras), "itens": sum(int(r["verificados"]) for r in regras), "ok": por_resultado["ok"], "expl": por_resultado["explicada"], "aber": por_resultado["aberta"], "info": por_resultado["info"],
            "ocorr": len(ocorr), "st": dict(por_status), "placar": [int(placar["verificados"]) - int(placar["ocorrencias"]), int(placar["verificados"])], "classif": [int(classif["verificados"]) - int(classif["ocorrencias"]), int(classif["verificados"])],
            "pdf": cfg["coleta_pdf_em"][:10], "espn": cfg["coleta_espn_em"][:10], "fpf": cfg["fpf_atualizado_em"][:10]}
    correcoes = []
    for c in ler_csv(RAIZ / "data" / "referencia" / "correcoes_dados.csv"):
        fontes = [f.split(" http")[0].split(" (")[0].strip() for f in c["fontes"].split(" | ")]
        correcoes.append({"i": c["id_correcao"], "t": jogo[c["numero_jogo"]], "d": f"{c['tipo_evento']} de {c['pessoa']}", "c": c["campo"], "de": c["valor_original"], "para": c["valor_corrigido"], "f": fontes, "x": amigavel(c["justificativa"])})
    camadas = [{**c, "r": c["r"].format(regras=len(regras))} for c in CAMADAS]
    dados = {"meta": meta, "reg": saida_reg, "oc": saida_oc, "tx": textos, "fon": FONTES_CONF, "cam": camadas, "cor": correcoes}
    conferir_conf(dados, regras, ocorr)
    return dados


def texto_do_pacote(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from texto_do_pacote(v)
    elif isinstance(x, list):
        for v in x:
            yield from texto_do_pacote(v)


def conferir_conf(dados, regras, ocorr):
    meta = dados["meta"]
    if meta["ok"] + meta["expl"] + meta["aber"] + meta["info"] != meta["regras"]:
        raise SystemExit("conferência: os resultados das regras não somam o total de regras")
    if sum(meta["st"].values()) != len(ocorr):
        raise SystemExit("conferência: os status das ocorrências não somam o total")
    conta = defaultdict(int)
    for o in dados["oc"]:
        conta[o["r"]] += 1
    for r in dados["reg"]:
        if conta[r["c"]] != r["o"]:
            raise SystemExit(f"regra {r['c']}: {r['o']} ocorrências no resultado e {conta[r['c']]} no log")
        if (r["r"] == "aberta") != any(o["st"] == "aberta" and o["r"] == r["c"] for o in dados["oc"]):
            raise SystemExit(f"regra {r['c']}: o resultado '{r['r']}' não combina com as ocorrências abertas")
    if meta["st"].get("aberta", 0) != sum(int(r["abertas"]) for r in regras):
        raise SystemExit("conferência: as ocorrências abertas do log não batem com as das regras")
    if any(not 0 <= o["x"] < len(dados["tx"]) for o in dados["oc"]):
        raise SystemExit("conferência: explicação sem texto")
    if "Placar final: súmula x tabela da FPF" not in next(r["t"] for r in dados["reg"] if r["c"] == "A22") or "Art. 16" not in next(r["t"] for r in dados["reg"] if r["c"] == "A19"):
        raise SystemExit("conferência: as regras A22 e A19 não são mais as do placar e da classificação; ajuste montar_dados_conf")
    for texto in texto_do_pacote(dados):
        for ruim in PROIBIDO_NA_TELA:
            if ruim in texto:
                raise SystemExit(f"o texto '{texto[:60]}...' cita '{ruim}'; acrescente a troca em AMIGAVEL")
    esperado = {"tabelas": 23, "colunas": 271, "relacionamentos": 39, "medidas": 72, "gabarito": 586, "clubes": 16, "jogos": 72}
    atual = contagens_para_camadas()
    for nome, valor in esperado.items():
        if atual[nome] != valor:
            raise SystemExit(f"CAMADAS desatualizadas: o texto diz {valor} {nome} e os dados têm {atual[nome]}; refaça a conferência (scripts/15_conferir_carga_powerbi.py, 10_gerar_medidas.py --comparar) e atualize CAMADAS em 13_montar_app.py")
    if (meta["placar"][1], meta["classif"][1]) != (esperado["jogos"], esperado["clubes"]):
        raise SystemExit("conferência: placar e classificação não cobrem os 72 jogos e os 16 clubes")


N_QUARTAS, N_REBAIXADOS = 8, 2
CRITERIOS_ART16 = [("v", "vitorias", 1), ("sg", "saldo", 1), ("gp", "gols_pro", 1), ("cv", "vermelhos", -1), ("ca", "amarelos", -1)]


def campos_da_tabela(l):
    return {"c": int(l["id_clube"]), "p": int(l["posicao"]), "pt": int(l["pontos"]), "j": int(l["jogos"]), "v": int(l["vitorias"]), "e": int(l["empates"]), "d": int(l["derrotas"]),
            "gp": int(l["gols_pro"]), "gc": int(l["gols_contra"]), "sg": int(l["saldo"]), "ca": int(l["amarelos"]), "cv": int(l["vermelhos"])}


def vencedor_do_confronto(jogos):
    """Quem passa: nas quartas e na semifinal (jogo único), quem faz mais gols e, no empate, quem vence os pênaltis; na final (dois jogos), quem soma mais pontos e, no empate, quem vence os pênaltis do returno."""
    pontos = defaultdict(int)
    for j in jogos:
        gm, gv = int(j["gols_mandante"]), int(j["gols_visitante"])
        pontos[j["id_clube_mandante"]] += 3 if gm > gv else 1 if gm == gv else 0
        pontos[j["id_clube_visitante"]] += 3 if gv > gm else 1 if gm == gv else 0
    a, b = sorted(pontos, key=lambda c: -pontos[c])
    if pontos[a] != pontos[b]:
        return a, b, dict(pontos)
    ultimo = jogos[-1]
    pm, pv = int(ultimo["penaltis_mandante"]), int(ultimo["penaltis_visitante"])
    ganhou = ultimo["id_clube_mandante"] if pm > pv else ultimo["id_clube_visitante"]
    perdeu = ultimo["id_clube_visitante"] if pm > pv else ultimo["id_clube_mandante"]
    return ganhou, perdeu, dict(pontos)


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)).lower()


def chave_art16(l):
    return (-l["pontos"], -l["vitorias"], -l["saldo"], -l["gols_pro"], l["vermelhos"], l["amarelos"])


def ordem_da_rodada(tabela, nomes):
    """Depois de uma rodada do meio, clubes podem estar iguais em todos os critérios do Art. 16 (o regulamento decidiria por sorteio).
    Eles ficam lado a lado em ordem alfabética e voltam em `grupos`; sem empate total, a ordem é a da tabela."""
    saida, grupos, i = [], [], 0
    while i < len(tabela):
        j = i
        while j + 1 < len(tabela) and chave_art16(tabela[j + 1]) == chave_art16(tabela[i]):
            j += 1
        bloco = sorted(tabela[i:j + 1], key=lambda l: sem_acento(nomes[int(l["id_clube"])]))
        if j > i:
            grupos.append([int(l["id_clube"]) for l in bloco])
        saida += bloco
        i = j + 1
    for k, l in enumerate(saida, 1):
        l["posicao"] = k
    return saida, grupos


def desempates(tab):
    """Para cada grupo de clubes com os mesmos pontos, o critério do Art. 16 que separou cada par vizinho."""
    saida, i = [], 0
    while i < len(tab):
        j = i
        while j + 1 < len(tab) and tab[j + 1]["pt"] == tab[i]["pt"]:
            j += 1
        if j > i:
            pares = []
            for k in range(i, j):
                a, b = tab[k], tab[k + 1]
                iguais = []
                for cod, _, sentido in CRITERIOS_ART16:
                    if a[cod] != b[cod]:
                        pares.append({"a": a["c"], "b": b["c"], "c": cod, "va": a[cod], "vb": b[cod], "iguais": iguais})
                        break
                    iguais.append(cod)
                else:
                    raise SystemExit(f"clubes {a['c']} e {b['c']} empatados em todos os critérios do Art. 16 (sorteio): a tela não sabe explicar")
            saida.append({"p": tab[i]["pt"], "ids": [t["c"] for t in tab[i:j + 1]], "pares": pares})
        i = j + 1
    return saida


def montar_dados_clas(versus=None):
    versus = versus or modulo_versus().montar_dados()
    fases = {f["id_fase"]: f["nome_fase"] for f in ler_csv(PROC / "dim_fase.csv")}
    estadios = {e["id_estadio"]: e["nome_fpf"] for e in ler_csv(PROC / "dim_estadio.csv")}
    partidas = ler_csv(PROC / "fato_partida.csv")
    eventos = [e for e in ler_csv(PROC / "fato_evento.csv") if e["tipo_evento"] in CARTAO]
    oficial = ler_csv(PROC / "fato_classificacao_oficial.csv")
    primeira = [p for p in partidas if fases[p["id_fase"]] == "PRIMEIRA FASE"]
    rodadas = sorted({int(p["rodada"]) for p in primeira})
    nomes = {int(c["id"]): c["curto"] for c in versus["clubes"]}
    posicoes, pontos_rod, calculado_final, empates_rod = defaultdict(list), defaultdict(list), None, []
    for r in rodadas:
        ate = [p for p in primeira if int(p["rodada"]) <= r]
        ids = {p["id_partida"] for p in ate}
        cart = contagem_cartoes([{"equipe_id": e["id_clube"], "cartao": CARTAO[e["tipo_evento"]]} for e in eventos if e["id_partida"] in ids])
        tabela, grupos = ordem_da_rodada(tabela_primeira_fase(ate, cart), nomes)
        empates_rod.append(grupos)
        for l in tabela:
            posicoes[int(l["id_clube"])].append(l["posicao"])
            pontos_rod[int(l["id_clube"])].append(l["pontos"])
        calculado_final = tabela
    tab = [campos_da_tabela(l) for l in sorted((o for o in oficial if o["fase"] == "PRIMEIRA FASE"), key=lambda o: int(o["posicao"]))]
    mm = []
    for p in sorted((p for p in partidas if fases[p["id_fase"]] != "PRIMEIRA FASE"), key=lambda p: (p["data_hora_programada"], int(p["numero_jogo"]))):
        pm, pv = p["penaltis_mandante"], p["penaltis_visitante"]
        mm.append({"n": int(p["numero_jogo"]), "f": FASE_COD[fases[p["id_fase"]]], "r": int(p["rodada"]), "d": p["data_jogo"], "h": p["hora_programada"], "m": int(p["id_clube_mandante"]), "v": int(p["id_clube_visitante"]),
                   "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]), "pm": int(pm) if pm else None, "pv": int(pv) if pv else None, "e": estadios[p["id_estadio"]]})
    confrontos = defaultdict(list)
    for p in sorted((p for p in partidas if fases[p["id_fase"]] != "PRIMEIRA FASE"), key=lambda p: (p["data_hora_programada"], int(p["numero_jogo"]))):
        confrontos[frozenset((p["id_clube_mandante"], p["id_clube_visitante"]))].append(p)
    passou = {}
    for par, jogos in confrontos.items():
        ganhou, perdeu, pts = vencedor_do_confronto(jogos)
        passou[par] = (int(ganhou), int(perdeu), pts)
    final = next(v for par, v in passou.items() if len(confrontos[par]) == 2)
    for j in mm:
        j["w"] = passou[frozenset((str(j["m"]), str(j["v"])))][0]
    a19 = next(r for r in ler_csv(PROC / "resultado_regra.csv") if r["codigo"] == "A19")
    clubes = [{k: c[k] for k in ("id", "nome", "curto", "sigla", "cor")} for c in versus["clubes"]]
    dados = {"meta": {"nq": N_QUARTAS, "nr": N_REBAIXADOS, "rod": len(rodadas), "fpf": oficial[0]["atualizado_em"][:10], "conf": [int(a19["verificados"]) - int(a19["ocorrencias"]), int(a19["verificados"])],
                      "camp": final[0], "vice": final[1], "fpts": [final[2][str(final[0])], final[2][str(final[1])]]},
             "clubes": clubes, "tab": tab, "rod": {str(k): v for k, v in posicoes.items()}, "rpt": {str(k): v for k, v in pontos_rod.items()}, "mm": mm, "emp": desempates(tab), "rt": empates_rod}
    conferir_clas(dados, calculado_final, oficial, primeira, passou, a19)
    return dados


def conferir_clas(dados, calculado, oficial, primeira, passou, a19):
    tab, meta = dados["tab"], dados["meta"]
    if [t["p"] for t in tab] != list(range(1, 17)) or len({t["c"] for t in tab}) != 16:
        raise SystemExit("classificação oficial: precisa de 16 clubes nas posições 1 a 16")
    for l in calculado:
        t = next(x for x in tab if x["c"] == int(l["id_clube"]))
        if campos_da_tabela(l) != t:
            raise SystemExit(f"clube {l['id_clube']}: o cálculo pelo Art. 16 ({campos_da_tabela(l)}) não bate com a tabela oficial ({t})")
    if any(l["empate_total"] for l in calculado):
        raise SystemExit("há empate em todos os critérios do Art. 16: a tela não trata sorteio")
    if meta["conf"] != [16, 16] or a19["resultado"] != "ok":
        raise SystemExit("a regra A19 (ordem pelo Art. 16 contra a posição oficial) deixou de dar 16 de 16")
    if any(len(v) != meta["rod"] for v in dados["rod"].values()) or any(len(v) != meta["rod"] for v in dados["rpt"].values()):
        raise SystemExit("posições ou pontos por rodada com tamanho diferente do número de rodadas")
    for t in tab:
        if dados["rod"][str(t["c"])][-1] != t["p"] or dados["rpt"][str(t["c"])][-1] != t["pt"]:
            raise SystemExit(f"clube {t['c']}: a posição ou os pontos da última rodada não batem com a tabela oficial")
        pts = dados["rpt"][str(t["c"])]
        if any(b < a or b - a > 3 for a, b in zip(pts, pts[1:])) or pts[0] > 3:
            raise SystemExit(f"clube {t['c']}: pontos por rodada impossíveis")
    for r in range(meta["rod"]):
        if sorted(v[r] for v in dados["rod"].values()) != list(range(1, 17)):
            raise SystemExit(f"rodada {r + 1}: as posições não são 1 a 16")
    if len(dados["rt"]) != meta["rod"] or dados["rt"][-1]:
        raise SystemExit("os empates totais por rodada precisam ter uma lista por rodada e nenhum na última")
    for r, grupos in enumerate(dados["rt"]):
        for g in grupos:
            pos = [dados["rod"][str(c)][r] for c in g]
            if len(g) < 2 or pos != list(range(pos[0], pos[0] + len(g))):
                raise SystemExit(f"rodada {r + 1}: o empate total {g} não está em posições seguidas")
    quartas = [j for j in dados["mm"] if j["f"] == 2]
    topo = {t["p"]: t["c"] for t in tab}
    esperados = {frozenset((topo[1], topo[8])), frozenset((topo[2], topo[7])), frozenset((topo[3], topo[6])), frozenset((topo[4], topo[5]))}
    if len(quartas) != 4 or {frozenset((j["m"], j["v"])) for j in quartas} != esperados:
        raise SystemExit("as quartas de final não são 1º x 8º, 2º x 7º, 3º x 6º e 4º x 5º da tabela")
    grupos = defaultdict(dict)
    for o in oficial:
        if o["fase"] != "PRIMEIRA FASE":
            grupos[(o["fase"], o["grupo"])][int(o["posicao"])] = int(o["id_clube"])
    vencedores_oficiais = {frozenset(map(int, (g[1], g[2]))): g[1] for g in grupos.values()}
    for par, (ganhou, perdeu, _) in passou.items():
        chave = frozenset((int(c) for c in par))
        if vencedores_oficiais[chave] != ganhou:
            raise SystemExit(f"confronto {sorted(chave)}: o vencedor pelo regulamento ({ganhou}) não é o primeiro da tabela oficial da fase")
    final = next(g for (fase, _), g in grupos.items() if fase == "FINAL")
    if (meta["camp"], meta["vice"]) != (final[1], final[2]):
        raise SystemExit("campeão e vice não batem com a tabela oficial da final")
    if len(dados["mm"]) != 8 or {j["f"] for j in dados["mm"]} != {2, 3, 4}:
        raise SystemExit("o mata-mata precisa de 8 jogos: 4 quartas, 2 semifinais e 2 da final")
    for texto in texto_do_pacote({k: v for k, v in dados.items() if k in ("clubes",)}):
        for ruim in PROIBIDO_NA_TELA:
            if ruim in texto:
                raise SystemExit(f"o texto '{texto[:60]}...' cita '{ruim}'")


def curtos_das_pessoas(eventos):
    """Nome completo dos gols e cartões -> nome curto do atleta (o da dimensão, o mesmo em todas as telas)."""
    return curto_por_pessoa(eventos, ler_csv(PROC / "fato_escalacao.csv"), ler_csv(PROC / "dim_atleta.csv"))


def montar_dados_vg(versus=None, clas=None, conf=None):
    """Tela Visão geral: os 72 jogos em resumo (placar, público, renda, cartões), os artilheiros e o campeão. A tela faz as contas de cada recorte (todas as fases, 1ª fase, mata-mata)."""
    versus = versus or modulo_versus().montar_dados()
    clas = clas or montar_dados_clas(versus)
    conf = conf or montar_dados_conf()
    fases = {f["id_fase"]: FASE_COD[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = ler_csv(PROC / "fato_partida.csv")
    eventos = ler_csv(PROC / "fato_evento.csv")
    amarelos, vermelhos = defaultdict(int), defaultdict(int)
    for e in eventos:
        if e["tipo_evento"] == "amarelo":
            amarelos[e["id_partida"]] += 1
        elif e["tipo_evento"] == "segundo_amarelo":
            amarelos[e["id_partida"]] -= 1
            vermelhos[e["id_partida"]] += 1
        elif e["tipo_evento"] == "vermelho":
            vermelhos[e["id_partida"]] += 1
    jogos = []
    for p in sorted(partidas, key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"]))):
        i = p["id_partida"]
        jogos.append({"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "m": int(p["id_clube_mandante"]), "v": int(p["id_clube_visitante"]),
                      "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]), "pu": int(p["publico_boletim"]), "pg": int(p["publico_pagante"]), "rb": centavos(p["renda_bruta"]),
                      "am": amarelos[i], "vm": vermelhos[i]})
    fase_do_jogo = {p["id_partida"]: fases[p["id_fase"]] for p in partidas}
    curto = curtos_das_pessoas(eventos)
    gols = defaultdict(lambda: {"g1": 0, "g2": 0, "clubes": Counter()})
    for e in eventos:
        if e["tipo_evento"] in ("gol", "gol_penalti", "gol_falta"):
            a = gols[e["pessoa"]]
            a["g1" if fase_do_jogo[e["id_partida"]] == 1 else "g2"] += 1
            a["clubes"][int(e["id_clube"])] += 1
    art = sorted(({"p": pessoa, "a": curto[pessoa], "c": a["clubes"].most_common(1)[0][0], "g1": a["g1"], "g2": a["g2"]} for pessoa, a in gols.items()), key=lambda x: (-(x["g1"] + x["g2"]), x["p"]))
    c, k = clas["meta"], conf["meta"]
    mm = [{x: j[x] for x in ("n", "f", "m", "v", "gm", "gv", "pm", "pv", "w")} for j in clas["mm"]]
    meta = {"camp": c["camp"], "vice": c["vice"], "fpts": c["fpts"], "regras": k["regras"], "ok": k["ok"], "expl": k["expl"], "aber": k["aber"], "info": k["info"], "classif": k["classif"], "placar": k["placar"]}
    dados = {"meta": meta, "clubes": clas["clubes"], "jogos": jogos, "art": art, "mm": mm}
    conferir_vg(dados)
    return dados


def conferir_vg(dados):
    ref = [l for l in ler_csv(PROC / "ref_indicadores.csv")]
    geral = {l["id_indicador"]: Decimal(l["valor"]) for l in ref if l["escopo"] == "geral"}
    js = dados["jogos"]
    soma = lambda lista, campo: sum(j[campo] for j in lista)
    if len(js) != 72 or len({j["n"] for j in js}) != 72:
        raise SystemExit("a visão geral precisa dos 72 jogos")
    esperado = [("jogos", len(js), int(geral["I01"])), ("gols", soma(js, "gm") + soma(js, "gv"), int(geral["I02"])), ("vitórias do mandante", sum(1 for j in js if j["gm"] > j["gv"]), int(geral["I04"])),
                ("empates", sum(1 for j in js if j["gm"] == j["gv"]), int(geral["I05"])), ("vitórias do visitante", sum(1 for j in js if j["gm"] < j["gv"]), int(geral["I06"])),
                ("público total", soma(js, "pu"), int(geral["I10"])), ("maior público", max(j["pu"] for j in js), int(geral["I12"])), ("menor público", min(j["pu"] for j in js), int(geral["I13"])),
                ("público pagante", soma(js, "pg"), int(geral["I14"])), ("renda bruta", soma(js, "rb"), centavos(geral["I16"])), ("amarelos", soma(js, "am"), int(geral["I20"])),
                ("vermelhos", soma(js, "vm"), int(geral["I21"])), ("jogos sem gols", sum(1 for j in js if j["gm"] + j["gv"] == 0), int(geral["I26"]))]
    for nome, achado, certo in esperado:
        if achado != certo:
            raise SystemExit(f"visão geral, {nome}: {achado} na tela, {certo} no gabarito")
    por_fase = {1: "PRIMEIRA FASE", 2: "QUARTAS DE FINAL", 3: "SEMIFINAL", 4: "FINAL"}
    fase = {(l["id_indicador"], l["chave"]): Decimal(l["valor"]) for l in ref if l["escopo"] == "fase"}
    for f, nome in por_fase.items():
        dentro = [j for j in js if j["f"] == f]
        for cod, achado in (("I01", len(dentro)), ("I02", soma(dentro, "gm") + soma(dentro, "gv")), ("I10", soma(dentro, "pu"))):
            if Decimal(achado) != fase[(cod, nome)]:
                raise SystemExit(f"visão geral, {cod} em {nome}: {achado} na tela, {fase[(cod, nome)]} no gabarito")
        if soma(dentro, "rb") != centavos(fase[("I16", nome)]):
            raise SystemExit(f"visão geral, renda bruta em {nome} não bate com o gabarito")
    gabarito_art = {l["chave"]: int(Decimal(l["valor"])) for l in ref if l["escopo"] == "artilheiro"}
    if {a["p"]: a["g1"] + a["g2"] for a in dados["art"]} != gabarito_art:
        raise SystemExit("os artilheiros da tela não batem com o gabarito (gols de atletas, sem gol contra)")
    if sum(a["g1"] + a["g2"] for a in dados["art"]) + sum(1 for e in ler_csv(PROC / "fato_evento.csv") if e["tipo_evento"] == "gol_contra") != int(geral["I02"]):
        raise SystemExit("gols dos atletas mais gols contra não fecham com o total de gols")
    ids = {c["id"] for c in dados["clubes"]}
    if any(str(j[x]) not in ids for j in js for x in ("m", "v")) or any(str(a["c"]) not in ids for a in dados["art"]):
        raise SystemExit("a visão geral cita um clube que não está na lista de clubes")
    for texto in [c[k] for c in dados["clubes"] for k in ("nome", "curto", "sigla")] + [a["a"] for a in dados["art"]] + [a["p"] for a in dados["art"]]:
        for ruim in PROIBIDO_NA_TELA:
            if ruim in texto:
                raise SystemExit(f"o texto '{texto[:60]}' cita '{ruim}'")


TIPO_GOL = {"gol": "g", "gol_penalti": "p", "gol_falta": "f", "gol_contra": "c"}
FAIXAS_MINUTO = [("01-15", 0, 15), ("16-30", 16, 30), ("31-45", 31, 45), ("46-60", 46, 60), ("61-75", 61, 75), ("76-90+", 76, 999)]


def montar_dados_gl(versus=None):
    """Tela Gols e artilharia: os 72 jogos (placar) e os 168 gols, um por um (jogo, minuto, tipo, clube que ganhou o gol, atleta). A tela faz as contas de cada recorte."""
    versus = versus or modulo_versus().montar_dados()
    fases = {f["id_fase"]: FASE_COD[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = ler_csv(PROC / "fato_partida.csv")
    eventos = ler_csv(PROC / "fato_evento.csv")
    numero = {p["id_partida"]: int(p["numero_jogo"]) for p in partidas}
    ordem = {int(p["numero_jogo"]): i for i, p in enumerate(sorted(partidas, key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"]))))}
    jogos = [{"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "m": int(p["id_clube_mandante"]), "v": int(p["id_clube_visitante"]), "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"])}
             for p in sorted(partidas, key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"])))]
    curto = curtos_das_pessoas(eventos)
    brutos = [e for e in eventos if e["tipo_evento"] in TIPO_GOL]
    pessoas = sorted({e["pessoa"] for e in brutos})
    indice = {p: i for i, p in enumerate(pessoas)}
    gols = sorted(({"j": numero[e["id_partida"]], "mn": int(e["minuto"]), "pe": 1 if e["periodo"] == "1T" else 2, "t": TIPO_GOL[e["tipo_evento"]], "c": int(e["id_clube_creditado"]), "k": int(e["id_clube"]), "a": indice[e["pessoa"]]} for e in brutos),
                  key=lambda g: (ordem[g["j"]], g["mn"], g["pe"], g["a"]))
    atl = [{"p": p, "a": curto[p]} for p in pessoas]
    clubes = [{k: c[k] for k in ("id", "nome", "curto", "sigla", "cor")} for c in versus["clubes"]]
    dados = {"clubes": clubes, "jogos": jogos, "gols": gols, "atl": atl}
    conferir_gl(dados)
    return dados


def conferir_gl(dados):
    ref = ler_csv(PROC / "ref_indicadores.csv")
    geral = {l["id_indicador"]: Decimal(l["valor"]) for l in ref if l["escopo"] == "geral"}
    js, gs, atl = dados["jogos"], dados["gols"], dados["atl"]
    if len(js) != 72 or len({j["n"] for j in js}) != 72:
        raise SystemExit("gols: precisa dos 72 jogos")
    if len(gs) != int(geral["I02"]) or sum(j["gm"] + j["gv"] for j in js) != len(gs):
        raise SystemExit(f"gols: {len(gs)} gols na lista, {sum(j['gm'] + j['gv'] for j in js)} nos placares, {geral['I02']} no gabarito")
    por_jogo = {j["n"]: j for j in js}
    contagem = Counter((g["j"], g["c"]) for g in gs)
    for j in js:
        if contagem[(j["n"], j["m"])] != j["gm"] or contagem[(j["n"], j["v"])] != j["gv"]:
            raise SystemExit(f"jogo {j['n']}: os gols listados não fecham com o placar")
    if any(g["c"] not in (por_jogo[g["j"]]["m"], por_jogo[g["j"]]["v"]) for g in gs):
        raise SystemExit("há gol creditado a um clube que não jogou aquele jogo")
    if any(g["t"] == "c" and g["k"] == g["c"] for g in gs) or any(g["t"] != "c" and g["k"] != g["c"] for g in gs):
        raise SystemExit("gol contra e clube do atleta não batem")
    tipos = Counter(g["t"] for g in gs)
    if tipos["p"] != int(geral["I25"]):
        raise SystemExit(f"gols de pênalti: {tipos['p']} na lista, {geral['I25']} no gabarito")
    if sum(1 for j in js if j["gm"] + j["gv"] == 0) != int(geral["I26"]):
        raise SystemExit("jogos sem gols não batem com o gabarito")
    faixa = {l["chave"]: int(Decimal(l["valor"])) for l in ref if l["escopo"] == "faixa_minuto" and l["id_indicador"] == "I24"}
    achado = {nome: sum(1 for g in gs if lo <= g["mn"] <= hi) for nome, lo, hi in FAIXAS_MINUTO}
    if achado != faixa:
        raise SystemExit(f"gols por faixa de minuto: {achado} na lista, {faixa} no gabarito")
    if sum(1 for g in gs if g["pe"] == 1) != sum(v for k, v in achado.items() if k in ("01-15", "16-30", "31-45")):
        raise SystemExit("gols do 1º tempo não batem com as três primeiras faixas")
    por_fase = {l["chave"]: int(Decimal(l["valor"])) for l in ref if l["escopo"] == "fase" and l["id_indicador"] == "I02"}
    nomes = {1: "PRIMEIRA FASE", 2: "QUARTAS DE FINAL", 3: "SEMIFINAL", 4: "FINAL"}
    for f, nome in nomes.items():
        if sum(1 for g in gs if por_jogo[g["j"]]["f"] == f) != por_fase[nome]:
            raise SystemExit(f"gols em {nome} não batem com o gabarito")
    artilheiros = Counter(atl[g["a"]]["p"] for g in gs if g["t"] != "c")
    gabarito = {l["chave"]: int(Decimal(l["valor"])) for l in ref if l["escopo"] == "artilheiro"}
    if dict(artilheiros) != gabarito:
        raise SystemExit("os artilheiros da tela não batem com o gabarito (gols de atletas, sem gol contra)")
    ids = {c["id"] for c in dados["clubes"]}
    if any(str(j[x]) not in ids for j in js for x in ("m", "v")):
        raise SystemExit("os gols citam um clube que não está na lista de clubes")
    for texto in [c[k] for c in dados["clubes"] for k in ("nome", "curto", "sigla")] + [a["a"] for a in atl] + [a["p"] for a in atl]:
        for ruim in PROIBIDO_NA_TELA:
            if ruim in texto:
                raise SystemExit(f"o texto '{texto[:60]}' cita '{ruim}'")


TIPO_CARTAO = {"amarelo": "a", "vermelho": "v", "segundo_amarelo": "s"}


def cartoes_da_regra_fpf(eventos):
    """Os cartões pela regra da FPF: o primeiro amarelo de quem foi expulso por segundo amarelo deixa de contar (conta só a expulsão, como vermelho)."""
    cartoes = [e for e in eventos if e["tipo_evento"] in TIPO_CARTAO]
    descartar = set()
    for s in (e for e in cartoes if e["tipo_evento"] == "segundo_amarelo"):
        primeiros = sorted((e for e in cartoes if e["tipo_evento"] == "amarelo" and e["id_partida"] == s["id_partida"] and e["pessoa"] == s["pessoa"] and e["id_evento"] not in descartar),
                           key=lambda e: (e["minuto_total"] == "", int(e["minuto_total"] or 0)))
        if not primeiros:
            raise SystemExit(f"segundo amarelo sem amarelo anterior: jogo {s['id_partida']}, {s['pessoa']}")
        descartar.add(primeiros[0]["id_evento"])
    return [e for e in cartoes if e["id_evento"] not in descartar]


def montar_dados_ds(versus=None):
    """Tela Disciplina e arbitragem: os 72 jogos (árbitro, acréscimos, gols de pênalti) e os 413 cartões, um por um (jogo, minuto, tipo, clube, atleta ou comissão e categoria do motivo). O texto livre do motivo não vai para a tela. A tela faz as contas de cada recorte."""
    versus = versus or modulo_versus().montar_dados()
    fases = {f["id_fase"]: FASE_COD[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = sorted(ler_csv(PROC / "fato_partida.csv"), key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"])))
    eventos = ler_csv(PROC / "fato_evento.csv")
    nome_arbitro = {a["id_arbitro"]: a["nome"] for a in ler_csv(PROC / "dim_arbitro.csv")}
    numero = {p["id_partida"]: int(p["numero_jogo"]) for p in partidas}
    ordem = {int(p["numero_jogo"]): i for i, p in enumerate(partidas)}
    arb = sorted({nome_arbitro[p["id_arbitro"]] for p in partidas})
    indice_arb = {n: i for i, n in enumerate(arb)}
    penaltis = Counter(e["id_partida"] for e in eventos if e["tipo_evento"] == "gol_penalti")
    jogos = [{"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "m": int(p["id_clube_mandante"]), "v": int(p["id_clube_visitante"]), "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]),
              "ar": indice_arb[nome_arbitro[p["id_arbitro"]]], "a1": int(p["acrescimo_1t_min"]), "a2": int(p["acrescimo_2t_min"]), "pn": penaltis[p["id_partida"]]} for p in partidas]
    regras = ler_regras_motivo()
    exibicao = categorias_em_ordem(regras)
    posicao = {r["ordem_regra"]: i for i, r in enumerate(exibicao)}
    curto = curtos_das_pessoas(eventos)
    brutos = cartoes_da_regra_fpf(eventos)
    atletas = sorted({e["pessoa"] for e in brutos if e["funcao"] == "Atleta"})
    indice_atl = {p: i for i, p in enumerate(atletas)}
    cart = sorted(({"j": numero[e["id_partida"]], "mn": int(e["minuto"]) if e["minuto"] != "" else None, "t": TIPO_CARTAO[e["tipo_evento"]], "c": int(e["id_clube"]), "f": 0 if e["funcao"] == "Atleta" else 1,
                    "p": indice_atl[e["pessoa"]] if e["funcao"] == "Atleta" else None, "m": posicao[classificar_motivo(e["motivo"], regras)["ordem_regra"]]} for e in brutos),
                  key=lambda x: (ordem[x["j"]], x["mn"] is None, x["mn"] or 0, x["c"], x["t"], x["p"] if x["p"] is not None else -1))
    clubes = [{k: c[k] for k in ("id", "nome", "curto", "sigla", "cor")} for c in versus["clubes"]]
    dados = {"meta": {"textos": len({e["motivo"] for e in brutos})}, "clubes": clubes, "jogos": jogos, "arb": arb, "atl": [{"p": p, "a": curto[p]} for p in atletas],
             "cat": [{"n": r["categoria"], "x": r["explicacao"]} for r in exibicao], "cart": cart}
    conferir_ds(dados)
    return dados


def conferir_ds(dados):
    ref = ler_csv(PROC / "ref_indicadores.csv")
    geral = {l["id_indicador"]: Decimal(l["valor"]) for l in ref if l["escopo"] == "geral"}
    js, cs, cat = dados["jogos"], dados["cart"], dados["cat"]
    if len(js) != 72 or len({j["n"] for j in js}) != 72:
        raise SystemExit("disciplina: precisa dos 72 jogos")
    por_jogo = {j["n"]: j for j in js}
    if any(c["j"] not in por_jogo or c["c"] not in (por_jogo[c["j"]]["m"], por_jogo[c["j"]]["v"]) for c in cs):
        raise SystemExit("disciplina: há cartão de um clube que não jogou aquele jogo")
    if any(not 0 <= c["m"] < len(cat) for c in cs) or any(c["mn"] is not None and not 0 <= c["mn"] <= 130 for c in cs):
        raise SystemExit("disciplina: categoria ou minuto de cartão fora do esperado")
    if any((c["f"] == 0) != (c["p"] is not None) or (c["p"] is not None and not 0 <= c["p"] < len(dados["atl"])) for c in cs):
        raise SystemExit("disciplina: atleta do cartão não bate com a lista de atletas")
    if len(set(c["p"] for c in cs if c["p"] is not None)) != len(dados["atl"]):
        raise SystemExit("disciplina: a lista de atletas tem alguém sem cartão")
    outros = sum(1 for c in cs if cat[c["m"]]["n"] == "Outros")
    if outros * 20 > len(cs):
        raise SystemExit(f"disciplina: {outros} de {len(cs)} cartões caíram em 'Outros'; revise data/referencia/motivos_cartao.csv")

    def conta(lista):
        a = sum(1 for c in lista if c["t"] == "a")
        return a, len(lista) - a

    nomes = {1: "PRIMEIRA FASE", 2: "QUARTAS DE FINAL", 3: "SEMIFINAL", 4: "FINAL"}
    fase = {(l["id_indicador"], l["chave"]): Decimal(l["valor"]) for l in ref if l["escopo"] == "fase"}
    clube = {(l["id_indicador"], l["id_clube"]): int(Decimal(l["valor"])) for l in ref if l["escopo"] == "clube"}
    a, v = conta(cs)
    if (a, v) != (int(geral["I20"]), int(geral["I21"])):
        raise SystemExit(f"disciplina: {a} amarelos e {v} vermelhos na tela, {geral['I20']} e {geral['I21']} no gabarito")
    if round(Decimal(len(cs)) / 72, 4) != geral["I22"]:
        raise SystemExit("disciplina: cartões por jogo não bate com o gabarito")
    if round(Decimal(sum(j["a1"] + j["a2"] for j in js)) / 72, 4) != geral["I23"]:
        raise SystemExit("disciplina: acréscimo médio não bate com o gabarito")
    if sum(j["pn"] for j in js) != int(geral["I25"]):
        raise SystemExit("disciplina: gols de pênalti não batem com o gabarito")
    for f, nome in nomes.items():
        jf = [j for j in js if j["f"] == f]
        cf = [c for c in cs if por_jogo[c["j"]]["f"] == f]
        if conta(cf) != (int(fase[("I20", nome)]), int(fase[("I21", nome)])):
            raise SystemExit(f"disciplina: amarelos e vermelhos em {nome} não batem com o gabarito")
        if round(Decimal(len(cf)) / len(jf), 4) != fase[("I22", nome)] or round(Decimal(sum(j["a1"] + j["a2"] for j in jf)) / len(jf), 4) != fase[("I23", nome)]:
            raise SystemExit(f"disciplina: cartões por jogo ou acréscimo em {nome} não batem com o gabarito")
        if sum(j["pn"] for j in jf) != int(fase[("I25", nome)]):
            raise SystemExit(f"disciplina: gols de pênalti em {nome} não batem com o gabarito")
    for c in dados["clubes"]:
        if conta([x for x in cs if str(x["c"]) == c["id"]]) != (clube[("I20", c["id"])], clube[("I21", c["id"])]):
            raise SystemExit(f"disciplina: cartões do clube {c['nome']} não batem com o gabarito")
    por_arbitro = Counter(j["ar"] for j in js)
    esperado = {a["nome"]: int(a["jogos_arbitro"]) for a in ler_csv(PROC / "dim_arbitro.csv") if int(a["jogos_arbitro"]) > 0}
    if {dados["arb"][i]: n for i, n in por_arbitro.items()} != esperado:
        raise SystemExit("disciplina: jogos por árbitro não batem com o cadastro de árbitros")
    ids = {c["id"] for c in dados["clubes"]}
    if any(str(j[x]) not in ids for j in js for x in ("m", "v")):
        raise SystemExit("disciplina: cita um clube que não está na lista de clubes")
    for texto in [c[k] for c in dados["clubes"] for k in ("nome", "curto", "sigla")] + [a["a"] for a in dados["atl"]] + [a["p"] for a in dados["atl"]] + dados["arb"] + [c["n"] for c in cat] + [c["x"] for c in cat]:
        for ruim in PROIBIDO_NA_TELA:
            if ruim in texto:
                raise SystemExit(f"o texto '{texto[:60]}' cita '{ruim}'")


PERIODO_COD = {"1T": 1, "2T": 2, "INT": 3, "PJ": 4}
ORDEM_DO_TEMPO = {"1T": 0, "INT": 1, "2T": 2, "PJ": 3}
FUNCAO_COD = {"Atleta": 0, "Técnico": 1, "Auxiliar Técnico": 2, "Treinador de goleiro": 3}
CAMPOS_ESTATISTICA = ["posse_pct", "finalizacoes", "finalizacoes_no_alvo", "escanteios", "faltas", "impedimentos", "passes", "passes_certos", "desarmes", "defesas_goleiro"]
PAPEIS_DE_ARBITRAGEM = ["id_arbitro", "id_assistente1", "id_assistente2", "id_quarto_arbitro", "id_var", "id_avar1", "id_avar2"]


def hhmm_em_minutos(texto):
    h, m = texto.split(":")
    return int(h) * 60 + int(m)


def horarios_plausiveis(p):
    """Mesma conta da regra A33: 1T e 2T de 40 a 80 min e intervalo de 8 a 30 min."""
    i1, t1, i2, t2 = (hhmm_em_minutos(p[k]) for k in ("inicio_1t", "termino_1t", "inicio_2t", "termino_2t"))
    return 40 <= (t1 - i1) % 1440 <= 80 and 40 <= (t2 - i2) % 1440 <= 80 and 8 <= (i2 - t1) % 1440 <= 30


def nome_pode_estar_cortado(atleta, pessoa_dos_eventos):
    """A relação de jogadores corta o nome em 33 letras; vale como completo o nome de um gol ou cartão que seja mais comprido que o da relação."""
    return atleta["nome_truncado"] == "1" and not (pessoa_dos_eventos and len(pessoa_dos_eventos) > len(atleta["nome"]))


def montar_dados_jg(versus=None):
    """Tela Jogos: os 72 jogos (data, estádio, arbitragem, público e renda), as escalações, as trocas, os gols e os cartões de cada um e as estatísticas dos times (ESPN, não oficial). A tela só escolhe, filtra e conta."""
    versus = versus or modulo_versus().montar_dados()
    fases = {f["id_fase"]: FASE_COD[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = sorted(ler_csv(PROC / "fato_partida.csv"), key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"])))
    eventos = ler_csv(PROC / "fato_evento.csv")
    escalacao = ler_csv(PROC / "fato_escalacao.csv")
    trocas = ler_csv(PROC / "fato_substituicao.csv")
    comissao = ler_csv(PROC / "fato_comissao.csv")
    estatisticas = {(e["id_partida"], e["id_clube"]): e for e in ler_csv(PROC / "fato_estatistica_time.csv")}
    dim_atleta = {a["id_atleta"]: a for a in ler_csv(PROC / "dim_atleta.csv")}
    estadios = sorted(ler_csv(PROC / "dim_estadio.csv"), key=lambda e: e["id_estadio"])
    nome_arbitro = {a["id_arbitro"]: a["nome"] for a in ler_csv(PROC / "dim_arbitro.csv")}
    atleta_da_camisa = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e["id_atleta"] for e in escalacao}
    pessoa_do_atleta = {}
    for e in eventos:
        if e["funcao"] == "Atleta" and e["fonte"] == "SUMULA":
            ida = atleta_da_camisa.get((e["id_partida"], e["id_clube"], e["numero_camisa"]))
            if ida is None:
                raise SystemExit(f"jogos: o evento {e['id_evento']} cita uma camisa que não está na relação de jogadores")
            pessoa_do_atleta.setdefault(ida, e["pessoa"])
    atletas_do_jogo = sorted({e["id_atleta"] for e in escalacao})
    nomes_staff = sorted({c["nome"] for c in comissao if c["funcao"] == "Técnico"} | {e["pessoa"] for e in eventos if e["funcao"] not in ("Atleta", "") and e["fonte"] == "SUMULA"})
    atl = [{"a": dim_atleta[i]["nome_curto"], "p": pessoa_do_atleta.get(i) or dim_atleta[i]["nome"], **({"t": 1} if nome_pode_estar_cortado(dim_atleta[i], pessoa_do_atleta.get(i)) else {})} for i in atletas_do_jogo]
    atl += [{"a": nome_de_comissao(n), "p": n} for n in nomes_staff]
    indice_atleta = {i: k for k, i in enumerate(atletas_do_jogo)}
    indice_staff = {n: len(atletas_do_jogo) + k for k, n in enumerate(nomes_staff)}
    pes = sorted({nome_arbitro[p[papel]] for p in partidas for papel in PAPEIS_DE_ARBITRAGEM})
    indice_pes = {n: k for k, n in enumerate(pes)}
    indice_estadio = {e["id_estadio"]: k for k, e in enumerate(estadios)}
    tecnicos = {(c["id_partida"], c["id_clube"]): indice_staff[c["nome"]] for c in comissao if c["funcao"] == "Técnico"}
    regras = ler_regras_motivo()
    exibicao = categorias_em_ordem(regras)
    posicao = {r["ordem_regra"]: i for i, r in enumerate(exibicao)}
    gols_e_cartoes = [e for e in eventos if e["fonte"] == "SUMULA" and e["tipo_evento"] in TIPO_GOL] + cartoes_da_regra_fpf(eventos)
    por_jogo = defaultdict(list)
    for e in gols_e_cartoes:
        por_jogo[e["id_partida"]].append(e)
    trocas_do_jogo = defaultdict(list)
    for t in trocas:
        trocas_do_jogo[t["id_partida"]].append(t)
    elenco = defaultdict(list)
    for e in escalacao:
        elenco[(e["id_partida"], e["id_clube"])].append(e)
    jogos, esc, sub, ev, st = [], [], [], [], []
    for p in partidas:
        i, mand, vis = p["id_partida"], p["id_clube_mandante"], p["id_clube_visitante"]
        lado = {mand: 0, vis: 1}
        pm = p["penaltis_mandante"]
        jogos.append({"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "h": p["hora_programada"], "w": datetime.date.fromisoformat(p["data_jogo"]).weekday(),
                      "m": int(mand), "v": int(vis), "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]), "pm": int(pm) if pm != "" else None, "pv": int(p["penaltis_visitante"]) if pm != "" else None,
                      "es": indice_estadio[p["id_estadio"]], "of": [indice_pes[nome_arbitro[p[papel]]] for papel in PAPEIS_DE_ARBITRAGEM], "a1": int(p["acrescimo_1t_min"]), "a2": int(p["acrescimo_2t_min"]),
                      "hr": [p["inicio_1t"], p["termino_1t"], p["inicio_2t"], p["termino_2t"]], "hp": 1 if horarios_plausiveis(p) else 0,
                      "pu": int(p["publico_boletim"]), "pg": int(p["publico_pagante"]), "rb": centavos(p["renda_bruta"]), "ds": centavos(p["despesas_total"]), "rl": centavos(p["renda_liquida"]),
                      "tm": tecnicos.get((i, mand)), "tv": tecnicos.get((i, vis))})
        if any(sum(1 for e in elenco[(i, clube)] if e["situacao"] == "titular") != 11 for clube in (mand, vis)):
            raise SystemExit(f"jogo {p['numero_jogo']}: cada time precisa de 11 titulares na relação")
        esc.append([[[int(e["numero_camisa"]), indice_atleta[e["id_atleta"]], int(e["minutos_jogados"] or 0)] for e in sorted(elenco[(i, clube)], key=lambda e: e["situacao"] != "titular")] for clube in (mand, vis)])
        sub.append([[lado[t["id_clube"]], int(t["numero_saiu"]), int(t["numero_entrou"]), PERIODO_COD[t["periodo"]], int(t["minuto"]) if t["minuto"] != "" else None, int(t["acrescimo"] or 0), 1 if t["tipo"] == "concussao" else 0]
                    for t in sorted(trocas_do_jogo[i], key=lambda t: (ORDEM_DO_TEMPO[t["periodo"]], int(t["minuto"] or 0), int(t["acrescimo"] or 0), lado[t["id_clube"]], int(t["ordem"])))])
        linhas = []
        for e in sorted(por_jogo[i], key=lambda e: (ORDEM_DO_TEMPO[e["periodo"]], int(e["minuto"] or 0), int(e["acrescimo"] or 0), e["id_evento"])):
            gol = e["tipo_evento"] in TIPO_GOL
            clube_do_lado = e["id_clube_creditado"] if gol else e["id_clube"]
            if e["funcao"] == "Atleta":
                quem, camisa = indice_atleta[atleta_da_camisa[(i, e["id_clube"], e["numero_camisa"])]], int(e["numero_camisa"])
            else:
                quem, camisa = indice_staff[e["pessoa"]], 0
            linhas.append([TIPO_GOL[e["tipo_evento"]] if gol else TIPO_CARTAO[e["tipo_evento"]], PERIODO_COD[e["periodo"]], int(e["minuto"]) if e["minuto"] != "" else None, int(e["acrescimo"] or 0), lado[clube_do_lado], quem, camisa,
                           FUNCAO_COD[e["funcao"]], -1 if gol else posicao[classificar_motivo(e["motivo"], regras)["ordem_regra"]]])
        ev.append(linhas)
        st.append([[float(estatisticas[(i, clube)][c]) if c == "posse_pct" else int(estatisticas[(i, clube)][c]) for c in CAMPOS_ESTATISTICA] for clube in (mand, vis)])
    clubes = [{k: c[k] for k in ("id", "nome", "curto", "sigla", "cor")} for c in versus["clubes"]]
    dados = {"clubes": clubes, "est": [{"n": e["nome_fpf"], "m": e["municipio"]} for e in estadios], "pes": pes, "atl": atl, "cat": [{"n": r["categoria"], "x": r["explicacao"]} for r in exibicao],
             "jogos": jogos, "esc": esc, "sub": sub, "ev": ev, "st": st}
    conferir_jg(dados)
    return dados


def conferir_jg(dados):
    ref = ler_csv(PROC / "ref_indicadores.csv")
    geral = {l["id_indicador"]: Decimal(l["valor"]) for l in ref if l["escopo"] == "geral"}
    js, esc, sub, ev, st, atl, pes = dados["jogos"], dados["esc"], dados["sub"], dados["ev"], dados["st"], dados["atl"], dados["pes"]
    if len(js) != 72 or len({j["n"] for j in js}) != 72 or not len(esc) == len(sub) == len(ev) == len(st) == 72:
        raise SystemExit("jogos: precisa dos 72 jogos, cada um com escalação, trocas, lances e estatísticas")
    soma = lambda campo: sum(j[campo] for j in js)
    esperado = [("gols", soma("gm") + soma("gv"), int(geral["I02"])), ("público total", soma("pu"), int(geral["I10"])), ("público pagante", soma("pg"), int(geral["I14"])), ("renda bruta", soma("rb"), centavos(geral["I16"])),
                ("renda líquida", soma("rl"), centavos(geral["I17"])), ("despesas", soma("ds"), centavos(geral["I38"]))]
    for nome, achado, certo in esperado:
        if achado != certo:
            raise SystemExit(f"jogos, {nome}: {achado} na tela, {certo} no gabarito")
    if any(j["rb"] - j["ds"] != j["rl"] for j in js):
        raise SystemExit("jogos: renda bruta menos despesas não dá a renda líquida")
    gols = [e for lista in ev for e in lista if e[0] in "gpfc"]
    cartoes = [e for lista in ev for e in lista if e[0] in "avs"]
    if len(gols) != int(geral["I02"]) or sum(1 for e in gols if e[0] == "p") != int(geral["I25"]):
        raise SystemExit("jogos: gols ou gols de pênalti da lista não batem com o gabarito")
    if (sum(1 for e in cartoes if e[0] == "a"), sum(1 for e in cartoes if e[0] != "a")) != (int(geral["I20"]), int(geral["I21"])):
        raise SystemExit("jogos: amarelos e vermelhos da lista não batem com o gabarito")
    for k, j in enumerate(js):
        lados = Counter(e[4] for e in ev[k] if e[0] in "gpfc")
        if (lados[0], lados[1]) != (j["gm"], j["gv"]):
            raise SystemExit(f"jogo {j['n']}: os gols listados não fecham com o placar")
        for lado in (0, 1):
            linhas = esc[k][lado]
            camisas = [c for c, _, _ in linhas]
            if len(set(camisas)) != len(camisas) or len(linhas) < 12:
                raise SystemExit(f"jogo {j['n']}: relação de jogadores repetida ou curta")
            if any(not 0 <= m <= 90 for _, _, m in linhas):
                raise SystemExit(f"jogo {j['n']}: minutos jogados fora de 0 a 90")
            titulares = linhas[:11]
            entraram = {s[2] for s in sub[k] if s[0] == lado}
            sairam = {s[1] for s in sub[k] if s[0] == lado}
            if not entraram <= {c for c, _, _ in linhas[11:]} or not sairam <= set(camisas):
                raise SystemExit(f"jogo {j['n']}: troca com camisa que não está na relação")
            if {c for c, _, m in linhas[11:] if m > 0} - entraram:
                raise SystemExit(f"jogo {j['n']}: reserva jogou sem entrar numa troca")
            if any(m != 90 for c, _, m in titulares if c not in sairam and not any(e[6] == c and e[0] in "vs" and e[4] == lado for e in ev[k])):
                raise SystemExit(f"jogo {j['n']}: titular que não saiu nem foi expulso com menos de 90 minutos")
        for e in ev[k]:
            if not 0 <= e[5] < len(atl) or e[8] >= len(dados["cat"]):
                raise SystemExit(f"jogo {j['n']}: lance com atleta ou categoria fora da lista")
            if e[7] == 0 and e[6] not in {c for c, _, _ in esc[k][e[4] if e[0] != "c" else 1 - e[4]]}:
                raise SystemExit(f"jogo {j['n']}: lance de atleta com camisa que não está na relação do clube dele")
        for lado in (0, 1):
            if len(st[k][lado]) != len(CAMPOS_ESTATISTICA):
                raise SystemExit(f"jogo {j['n']}: estatísticas incompletas")
        if not 99 <= st[k][0][0] + st[k][1][0] <= 101:
            raise SystemExit(f"jogo {j['n']}: posse de bola não soma 100%")
    if sum(len(l) for e in esc for l in e) != len(ler_csv(PROC / "fato_escalacao.csv")) or sum(len(s) for s in sub) != len(ler_csv(PROC / "fato_substituicao.csv")):
        raise SystemExit("jogos: escalações ou trocas da tela não fecham com as tabelas")
    por_papel = defaultdict(Counter)
    for j in js:
        for papel, quem in zip(("jogos_arbitro", "jogos_assistente", "jogos_assistente", "jogos_quarto_arbitro", "jogos_var", "jogos_var", "jogos_var"), j["of"]):
            por_papel[papel][pes[quem]] += 1
    for a in ler_csv(PROC / "dim_arbitro.csv"):
        for papel, contagem in por_papel.items():
            if contagem[a["nome"]] != int(a[papel]):
                raise SystemExit(f"jogos: {a['nome']} tem {contagem[a['nome']]} jogos como {papel} na tela e {a[papel]} no cadastro")
    ids = {c["id"] for c in dados["clubes"]}
    if any(str(j[x]) not in ids for j in js for x in ("m", "v")):
        raise SystemExit("jogos: cita um clube que não está na lista de clubes")
    for texto in [c[k] for c in dados["clubes"] for k in ("nome", "curto", "sigla")] + [a[k] for a in atl for k in ("a", "p")] + pes + [e[k] for e in dados["est"] for k in ("n", "m")] + [c[k] for c in dados["cat"] for k in ("n", "x")]:
        for ruim in PROIBIDO_NA_TELA:
            if ruim in texto:
                raise SystemExit(f"o texto '{texto[:60]}' cita '{ruim}'")


def conferir_gabarito(dados):
    ref = {l["id_indicador"]: Decimal(l["valor"]) for l in ler_csv(PROC / "ref_indicadores.csv") if l["escopo"] == "geral"}
    js = dados["jogos"]
    soma = lambda campo: sum(j[campo] for j in js)
    esperado = [("público total", soma("pu"), int(ref["I10"])), ("público pagante", soma("pg"), int(ref["I14"])), ("renda bruta", soma("rb"), centavos(ref["I16"])), ("renda líquida", soma("rl"), centavos(ref["I17"])),
                ("jogos com renda líquida negativa", sum(1 for j in js if j["rl"] < 0), int(ref["I19"]))]
    for nome, achado, certo in esperado:
        if achado != certo:
            raise SystemExit(f"{nome}: {achado} na tela, {certo} no gabarito")
    for j in js:
        if sum(j["ci"]) != j["pu"] or sum(j["cr"]) != j["rb"] or sum(j["gd"]) != j["ds"] or sum(j["bd"]) != j["ds"] or j["rb"] - j["ds"] != j["rl"]:
            raise SystemExit(f"jogo {j['n']}: categorias, grupos ou blocos não fecham com o boletim")
        if sum(v for _, v in j["rb2"]) != j["ds"]:
            raise SystemExit(f"jogo {j['n']}: rubricas não fecham com as despesas")
    ticket = Decimal(soma("rb")) / 100 / soma("pg")
    if round(ticket, 2) != ref["I18"]:
        raise SystemExit(f"ticket médio: {round(ticket, 2)} na tela, {ref['I18']} no gabarito")


def dados_json(dados):
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def logos_js(dados_versus):
    logos = [{"id": c["id"], "logo": c["logo"]} for c in dados_versus["clubes"]]
    return "<script>window.PA={clubes:" + json.dumps(logos, ensure_ascii=False, separators=(",", ":")) + "};</script>"


def pagina(titulo, corpo, css_extra=""):
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{titulo}</title><style>html,body{{margin:0;height:100%;background:#05070a}}{css_extra}</style></head><body>" + corpo + "</body></html>")


def sandbox(pag, titulo):
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>' + titulo + '</title>'
            "<style>html,body{margin:0;height:100%;background:#222}iframe{border:0;width:100%;height:100%}</style></head><body>"
            '<iframe sandbox="allow-scripts" srcdoc="' + html.escape(pag, quote=True) + '"></iframe></body></html>')


TELAS = [
    ("vg", "visao_geral", "__DADOS_VG__", "__MOD_VG__"),
    ("vs", "versus", "__DADOS_VS__", "__MOD_VS__"),
    ("clas", "classificacao", "__DADOS_CLAS__", "__MOD_CLAS__"),
    ("gl", "gols", "__DADOS_GL__", "__MOD_GL__"),
    ("ds", "disciplina", "__DADOS_DS__", "__MOD_DS__"),
    ("jg", "jogos", "__DADOS_JG__", "__MOD_JG__"),
    ("fin", "financeiro", "__DADOS_FIN__", "__MOD_FIN__"),
    ("conf", "conferencia", "__DADOS_CONF__", "__MOD_CONF__"),
]


def fragmento(pasta):
    return (PROTO / pasta / "fragmento.html").read_text(encoding="utf-8")


def montar_todos_os_dados(versus=None):
    """Os pacotes de dados de todas as telas, por chave de TELAS."""
    versus = versus or modulo_versus().montar_dados()
    clas, conf = montar_dados_clas(versus), montar_dados_conf()
    return {"vs": versus, "fin": montar_dados_fin(versus), "clas": clas, "conf": conf, "vg": montar_dados_vg(versus, clas, conf), "gl": montar_dados_gl(versus), "ds": montar_dados_ds(versus), "jg": montar_dados_jg(versus)}


def montar_codigo_app(meta):
    """Página do app com uma marca `__DADOS_XXX__` no lugar do pacote de dados de cada tela (a medida DAX do Power BI troca as marcas pelos dados).
    `meta`: contagem das regras de conferência para o selo da barra (chaves `regras` e `aber`)."""
    shell = (PROTO / "app" / "shell.html").read_text(encoding="utf-8")
    for marcador in [t[3] for t in TELAS] + ["__SELO__"]:
        if shell.count(marcador) != 1:
            raise SystemExit(f"shell.html: a marca {marcador} deve aparecer uma vez")
    for chave, pasta, marca, marcador in TELAS:
        texto = fragmento(pasta)
        if texto.count("__DADOS__") != 1:
            raise SystemExit(f"{pasta}/fragmento.html: a marca __DADOS__ deve aparecer uma vez")
        shell = shell.replace(marcador, texto.replace("__DADOS__", marca))
    selo = f"{meta['regras']} regras · {meta['aber']} abertas"
    return shell.replace("__SELO__", html.escape(selo))


def montar_fragmentos(dados):
    """dados: {chave de TELAS: pacote}. Devolve {chave: fragmento da tela com os dados, "app": página do app com tudo}."""
    app = montar_codigo_app(dados["conf"]["meta"])
    for chave, pasta, marca, _ in TELAS:
        app = app.replace(marca, dados_json(dados[chave]))
    saida = {chave: fragmento(pasta).replace("__DADOS__", dados_json(dados[chave])) for chave, pasta, *_ in TELAS}
    saida["app"] = app
    return saida


def main():
    dados = montar_todos_os_dados()
    frag = montar_fragmentos(dados)
    for _, pasta, *_ in TELAS:
        (PROTO / pasta).mkdir(parents=True, exist_ok=True)
    (PROTO / "app").mkdir(parents=True, exist_ok=True)
    com_escudos = {"fin": "Público e renda", "clas": "Classificação e chave", "vg": "Visão geral", "gl": "Gols e artilharia", "ds": "Disciplina e arbitragem", "jg": "Jogos e escalações"}
    titulos = {"vg": "Visão geral", "fin": "Público e renda", "clas": "Classificação e chave", "gl": "Gols e artilharia", "ds": "Disciplina e arbitragem", "jg": "Jogos e escalações", "conf": "Conferência e fontes"}
    for chave, nome in titulos.items():
        corpo = (logos_js(dados["vs"]) if chave in com_escudos else "") + frag[chave]
        pasta = next(t[1] for t in TELAS if t[0] == chave)
        (PROTO / pasta / "index.html").write_text(pagina(f"{nome} - Paulista Analytics", corpo), encoding="utf-8", newline="\n")
    pag_app = pagina("Paulista Analytics", frag["app"])
    (PROTO / "app" / "index.html").write_text(pag_app, encoding="utf-8", newline="\n")
    (PROTO / "app" / "sandbox.html").write_text(sandbox(pag_app, "Paulista Analytics no sandbox"), encoding="utf-8", newline="\n")
    print(f"jogos: {len(dados['fin']['jogos'])} | categorias: {len(dados['fin']['cat'])} | grupos de despesa: {len(dados['fin']['grp'])} | rubricas: {len(dados['fin']['rub'])}")
    for chave, nome in (("vg", "Visão geral"), ("fin", "Público e renda"), ("clas", "Classificação e chave"), ("gl", "Gols e artilharia"), ("ds", "Disciplina e arbitragem"), ("jg", "Jogos e escalações"), ("conf", "Conferência e fontes")):
        print(f"dados da tela {nome} (JSON): {len(dados_json(dados[chave])):,} caracteres".replace(",", "."))
    print(f"duelo (fragmento com dados): {len(frag['vs']):,} | Visão geral: {len(frag['vg']):,} | Público e renda: {len(frag['fin']):,} | Classificação: {len(frag['clas']):,} | Gols: {len(frag['gl']):,} | Disciplina: {len(frag['ds']):,} | Jogos: {len(frag['jg']):,} | Conferência: {len(frag['conf']):,} | página do app: {len(frag['app']):,} caracteres".replace(",", "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
