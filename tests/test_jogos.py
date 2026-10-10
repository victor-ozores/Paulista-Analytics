import datetime
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
PROTO = RAIZ / "prototype"
REF = RAIZ / "data" / "referencia"
NECESSARIOS = ("fato_partida.csv", "fato_evento.csv", "fato_escalacao.csv", "fato_substituicao.csv", "fato_comissao.csv", "fato_estatistica_time.csv", "dim_atleta.csv", "dim_estadio.csv", "dim_arbitro.csv", "ref_indicadores.csv", "dim_fase.csv")
precisa_dados = pytest.mark.skipif(not all((PROC / n).exists() for n in NECESSARIOS), reason="rode scripts/04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
INTERNOS = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")
FS = {"t": "Todas as fases", "p": "1ª fase", "m": "Mata-mata"}
COD_FASE = {"PRIMEIRA FASE": 1, "QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
RES = {"m": "Vitória do mandante", "e": "Empate no tempo normal", "v": "Vitória do visitante"}
ABAS = {"pu": "Público", "ar": "Arbitragem", "es": "Estatísticas"}
PAPEIS = ["Árbitro", "Assistente 1", "Assistente 2", "Quarto árbitro", "VAR", "AVAR 1", "AVAR 2"]
PAPEL_NA_TABELA = ["id_arbitro", "id_assistente1", "id_assistente2", "id_quarto_arbitro", "id_var", "id_avar1", "id_avar2"]
TIPO_GOL = {"gol": "g", "gol_penalti": "p", "gol_falta": "f", "gol_contra": "c"}
TIPO_CARTAO = {"amarelo": "a", "vermelho": "v", "segundo_amarelo": "s"}
TIPO_NOME = {"g": "Gol", "p": "Gol de pênalti", "f": "Gol de falta", "c": "Gol contra", "a": "Cartão amarelo", "v": "Cartão vermelho", "s": "Segundo amarelo"}
FUNCAO_NOME = ["Atleta", "Técnico", "Auxiliar técnico", "Treinador de goleiro"]
FUNCAO_NA_SUMULA = ["Atleta", "Técnico", "Auxiliar Técnico", "Treinador de goleiro"]
COD_PERIODO = {"1T": 1, "2T": 2, "INT": 3, "PJ": 4}
ORDEM_DO_TEMPO = {"1T": 0, "INT": 1, "2T": 2, "PJ": 3}
STATS = [("Posse de bola", 0), ("Finalizações", 1), ("No alvo", 2), ("Escanteios", 3), ("Faltas", 4), ("Impedimentos", 5), ("Passes certos", 7), ("Desarmes", 8), ("Defesas do goleiro", 9)]
CAMPOS_STATS = ["posse_pct", "finalizacoes", "finalizacoes_no_alvo", "escanteios", "faltas", "impedimentos", "passes", "passes_certos", "desarmes", "defesas_goleiro"]
ROW, LISTA_H = 42, 630


def carregar(nome, arq):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


disc = carregar("disciplina_teste_jg", "disciplina.py")


def decod(t):
    return t.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def fmt(n, c=0):
    v = Decimal(n).quantize(Decimal(1).scaleb(-c), rounding=ROUND_HALF_UP)
    return f"{v:,.{c}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def plural(n, u, p):
    return f"{fmt(n)} " + (u if n == 1 else p)


def pct(a, b):
    return fmt(Decimal(100 * a) / b, 1) + "%" if b > 0 else "—"


def reais(c):
    return ("−" if c < 0 else "") + "R$ " + fmt(Decimal(abs(c)) / 100, 2)


def data_br(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}"


def data_longa(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}/{a}"


def tabela_tip(secao):
    assert secao.startswith("@"), secao[:60]
    return [tuple(x.split("::")) for x in secao[1:].split("\n")]


def centavos(v):
    return int((Decimal(v) * 100).to_integral_value())


def nome_rodada(r, rodadas_da_final, fase):
    if fase == 1:
        return f"1ª fase · rodada {r}"
    if fase == 4:
        return "Final · jogo de " + ("ida" if rodadas_da_final.index(r) == 0 else "volta")
    return {2: "Quartas de final", 3: "Semifinal"}[fase]


# ---------- referência recalculada aqui, direto das tabelas tratadas ----------

@pytest.fixture(scope="module")
def ref():
    fases = {f["id_fase"]: COD_FASE[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = sorted(ler_csv(PROC / "fato_partida.csv"), key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"])))
    eventos = ler_csv(PROC / "fato_evento.csv")
    escalacao = ler_csv(PROC / "fato_escalacao.csv")
    trocas = ler_csv(PROC / "fato_substituicao.csv")
    comissao = ler_csv(PROC / "fato_comissao.csv")
    estat = {(e["id_partida"], e["id_clube"]): e for e in ler_csv(PROC / "fato_estatistica_time.csv")}
    atletas = {a["id_atleta"]: a for a in ler_csv(PROC / "dim_atleta.csv")}
    estadios = {e["id_estadio"]: e for e in ler_csv(PROC / "dim_estadio.csv")}
    arbitros = {a["id_arbitro"]: a["nome"] for a in ler_csv(PROC / "dim_arbitro.csv")}
    camisa_de = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e["id_atleta"] for e in escalacao}
    pessoa_de = {}
    for e in eventos:
        if e["funcao"] == "Atleta" and e["fonte"] == "SUMULA":
            pessoa_de.setdefault(camisa_de[(e["id_partida"], e["id_clube"], e["numero_camisa"])], e["pessoa"])

    def nome_curto(ida):
        return atletas[ida]["nome_curto"]

    def nome_staff(nome):
        partes = nome.split()
        while len(partes) > 2 and partes[-1].lower() in ("junior", "júnior", "filho", "neto", "sobrinho"):
            partes = partes[:-1]
        return partes[0] if len(partes) == 1 else partes[0] + " " + partes[-1]

    regras = disc.ler_regras_motivo()
    exibicao = disc.categorias_em_ordem(regras)
    por_pessoa = defaultdict(list)
    for e in eventos:
        if e["tipo_evento"] in TIPO_CARTAO:
            por_pessoa[(e["id_partida"], e["pessoa"])].append(e)
    cartoes = []
    for lista in por_pessoa.values():
        lista = sorted(lista, key=lambda e: e["id_evento"])
        if any(e["tipo_evento"] == "segundo_amarelo" for e in lista):
            primeiro = next(e for e in lista if e["tipo_evento"] == "amarelo")
            lista = [e for e in lista if e is not primeiro]
        cartoes += lista
    lances_brutos = defaultdict(list)
    for e in [x for x in eventos if x["fonte"] == "SUMULA" and x["tipo_evento"] in TIPO_GOL] + cartoes:
        lances_brutos[e["id_partida"]].append(e)
    trocas_por = defaultdict(list)
    for t in trocas:
        trocas_por[t["id_partida"]].append(t)
    tecnicos = {(c["id_partida"], c["id_clube"]): c["nome"] for c in comissao if c["funcao"] == "Técnico"}
    elenco = defaultdict(list)
    for e in escalacao:
        elenco[(e["id_partida"], e["id_clube"])].append(e)
    finais = sorted({int(p["rodada"]) for p in partidas if fases[p["id_fase"]] == 4})
    jogos = []
    for p in partidas:
        i, mand, vis = p["id_partida"], p["id_clube_mandante"], p["id_clube_visitante"]
        lado = {mand: 0, vis: 1}
        e = estadios[p["id_estadio"]]
        j = {"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "h": p["hora_programada"], "w": datetime.date.fromisoformat(p["data_jogo"]).weekday(), "m": int(mand), "v": int(vis),
             "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]), "pm": int(p["penaltis_mandante"]) if p["penaltis_mandante"] != "" else None, "pv": int(p["penaltis_visitante"]) if p["penaltis_mandante"] != "" else None,
             "estadio": e["nome_fpf"], "cidade": e["municipio"], "of": [arbitros[p[k]] for k in PAPEL_NA_TABELA], "a1": int(p["acrescimo_1t_min"]), "a2": int(p["acrescimo_2t_min"]),
             "hr": [p["inicio_1t"], p["termino_1t"], p["inicio_2t"], p["termino_2t"]], "pu": int(p["publico_boletim"]), "pg": int(p["publico_pagante"]), "rb": centavos(p["renda_bruta"]), "ds": centavos(p["despesas_total"]), "rl": centavos(p["renda_liquida"]),
             "tec": [tecnicos.get((i, mand)), tecnicos.get((i, vis))]}
        j["esc"] = [[{"c": int(r["numero_camisa"]), "ida": r["id_atleta"], "a": nome_curto(r["id_atleta"]), "p": pessoa_de.get(r["id_atleta"]) or atletas[r["id_atleta"]]["nome"], "mj": int(r["minutos_jogados"] or 0), "tit": r["situacao"] == "titular"}
                     for r in sorted(elenco[(i, clube)], key=lambda r: r["situacao"] != "titular")] for clube in (mand, vis)]
        j["sub"] = [{"lado": lado[t["id_clube"]], "saiu": int(t["numero_saiu"]), "entrou": int(t["numero_entrou"]), "per": COD_PERIODO[t["periodo"]], "mn": int(t["minuto"]) if t["minuto"] != "" else None, "ac": int(t["acrescimo"] or 0), "conc": t["tipo"] == "concussao"}
                    for t in sorted(trocas_por[i], key=lambda t: (ORDEM_DO_TEMPO[t["periodo"]], int(t["minuto"] or 0), int(t["acrescimo"] or 0), lado[t["id_clube"]], int(t["ordem"])))]
        lances = []
        for e in sorted(lances_brutos[i], key=lambda e: (ORDEM_DO_TEMPO[e["periodo"]], int(e["minuto"] or 0), int(e["acrescimo"] or 0), e["id_evento"])):
            gol = e["tipo_evento"] in TIPO_GOL
            quem_ida = camisa_de[(i, e["id_clube"], e["numero_camisa"])] if e["funcao"] == "Atleta" else None
            lances.append({"t": TIPO_GOL[e["tipo_evento"]] if gol else TIPO_CARTAO[e["tipo_evento"]], "per": COD_PERIODO[e["periodo"]], "mn": int(e["minuto"]) if e["minuto"] != "" else None, "ac": int(e["acrescimo"] or 0),
                           "lado": lado[e["id_clube_creditado"] if gol else e["id_clube"]], "n": int(e["numero_camisa"]) if e["funcao"] == "Atleta" else 0, "f": FUNCAO_NA_SUMULA.index(e["funcao"]),
                           "a": nome_curto(quem_ida) if quem_ida else nome_staff(e["pessoa"]), "p": pessoa_de.get(quem_ida) if quem_ida else e["pessoa"],
                           "cat": None if gol else disc.classificar_motivo(e["motivo"], regras)["categoria"]})
        j["ev"] = lances
        j["st"] = [[float(estat[(i, clube)][c]) if c == "posse_pct" else int(estat[(i, clube)][c]) for c in CAMPOS_STATS] for clube in (mand, vis)]
        j["tec_curto"] = [nome_staff(t) if t else None for t in j["tec"]]
        jogos.append(j)
    for j in jogos:
        j["nome_rodada"] = nome_rodada(j["r"], finais, j["f"])
    return {"jogos": jogos, "por_n": {j["n"]: j for j in jogos}, "rodadas": sorted({j["r"] for j in jogos}), "exibicao": [(r["categoria"], r["explicacao"]) for r in exibicao], "nome_curto": nome_curto, "atletas": atletas, "pessoa_de": pessoa_de,
            "motivos": {e["motivo"] for e in cartoes}, "finais": finais}


def resultado(j):
    return "m" if j["gm"] > j["gv"] else "v" if j["gm"] < j["gv"] else "e"


def passa(j, fase, rod, clube, res):
    return (fase == "t" or (fase == "p" and j["f"] == 1) or (fase == "m" and j["f"] > 1)) and (rod is None or j["r"] == rod) and (clube is None or clube in (j["m"], j["v"])) and (res is None or resultado(j) == res)


def lista_de(ref, fase, rod, clube, res):
    return [j for j in ref["jogos"] if passa(j, fase, rod, clube, res)]


def linhas_do_jogo(j):
    lin = [("Jogo", f"{j['n']} · {j['nome_rodada']}"), ("Data", f"{DIAS[j['w']]}, {data_longa(j['d'])} às {j['h']}"), ("Estádio", f"{j['estadio']} · {j['cidade']}"), ("Público", fmt(j["pu"]))]
    return lin


@pytest.fixture(scope="module")
def montagem(tmp_path_factory):
    m = carregar("montar_app13_jg", "13_montar_app.py")
    versus = m.modulo_versus().montar_dados()
    jg = m.montar_dados_jg(versus)
    frag = (PROTO / "jogos" / "fragmento.html").read_text(encoding="utf-8").replace("__DADOS__", m.dados_json(jg))
    pasta = tmp_path_factory.mktemp("jg")
    (pasta / "jg.html").write_text(m.pagina("t", m.logos_js(versus) + frag), encoding="utf-8")
    return {"m": m, "versus": versus, "jg": jg, "frag": frag, "pasta": pasta}


@pytest.fixture(scope="module")
def curto(montagem):
    return {int(c["id"]): c["curto"] for c in montagem["jg"]["clubes"]}


@pytest.fixture(scope="module")
def sigla(montagem):
    return {int(c["id"]): c["sigla"] for c in montagem["jg"]["clubes"]}


def rodar(montagem, *extra):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_jg.js"), str(montagem["pasta"] / "jg.html"), *extra], capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr[-1500:]
    s = json.loads(proc.stdout)
    assert not s.get("semGancho")
    return s


@pytest.fixture(scope="module")
def saida(montagem):
    return rodar(montagem)


# ---------- pacote de dados ----------

@precisa_dados
def test_jogos_do_pacote_sao_os_72_das_tabelas_campo_a_campo(montagem, ref):
    jg = montagem["jg"]
    assert len(jg["jogos"]) == 72
    for p, j in zip(jg["jogos"], ref["jogos"]):
        assert (p["n"], p["f"], p["r"], p["d"], p["h"], p["w"], p["m"], p["v"], p["gm"], p["gv"], p["pm"], p["pv"]) == (j["n"], j["f"], j["r"], j["d"], j["h"], j["w"], j["m"], j["v"], j["gm"], j["gv"], j["pm"], j["pv"])
        assert (jg["est"][p["es"]]["n"], jg["est"][p["es"]]["m"]) == (j["estadio"], j["cidade"])
        assert [jg["pes"][k] for k in p["of"]] == j["of"] and (p["a1"], p["a2"]) == (j["a1"], j["a2"]) and p["hr"] == j["hr"]
        assert (p["pu"], p["pg"], p["rb"], p["ds"], p["rl"]) == (j["pu"], j["pg"], j["rb"], j["ds"], j["rl"])
        assert [jg["atl"][k]["p"] if k is not None else None for k in (p["tm"], p["tv"])] == j["tec"]
    assert [j["n"] for j in jg["jogos"]] == [j["n"] for j in ref["jogos"]] and [(j["pm"], j["pv"]) for j in jg["jogos"] if j["pm"] is not None] == [(7, 8)]


@precisa_dados
def test_so_o_jogo_47_tem_horarios_nao_plausiveis_so_o_68_tem_penaltis_e_so_um_time_fica_sem_tecnico(montagem):
    jg = montagem["jg"]
    assert [j["n"] for j in jg["jogos"] if not j["hp"]] == [47]
    assert [j["n"] for j in jg["jogos"] if j["pm"] is not None] == [68]
    assert [j["tm"] is None or j["tv"] is None for j in jg["jogos"]].count(True) == 1


@precisa_dados
def test_escalacoes_do_pacote_sao_as_3292_linhas_da_sumula_com_os_onze_titulares_primeiro(montagem, ref):
    jg = montagem["jg"]
    assert sum(len(l) for e in jg["esc"] for l in e) == 3292
    for k, j in enumerate(ref["jogos"]):
        for lado in (0, 1):
            linhas, esperado = jg["esc"][k][lado], j["esc"][lado]
            assert [(c, jg["atl"][a]["a"], jg["atl"][a]["p"], m) for c, a, m in linhas] == [(r["c"], r["a"], r["p"], r["mj"]) for r in esperado], (j["n"], lado)
            assert [r["tit"] for r in esperado] == [True] * 11 + [False] * (len(esperado) - 11)


@precisa_dados
def test_trocas_do_pacote_sao_as_706_na_ordem_do_jogo(montagem, ref):
    jg = montagem["jg"]
    assert sum(len(s) for s in jg["sub"]) == 706
    for k, j in enumerate(ref["jogos"]):
        assert [(s[0], s[1], s[2], s[3], s[4], s[5], s[6] == 1) for s in jg["sub"][k]] == [(s["lado"], s["saiu"], s["entrou"], s["per"], s["mn"], s["ac"], s["conc"]) for s in j["sub"]], j["n"]
    assert sum(1 for s in jg["sub"] for t in s if t[6] == 1) == 2 and sum(1 for s in jg["sub"] for t in s if t[3] == 3) == 91


@precisa_dados
def test_lances_do_pacote_sao_168_gols_e_413_cartoes_com_o_lado_certo(montagem, ref):
    jg = montagem["jg"]
    gols = cartoes = 0
    for k, j in enumerate(ref["jogos"]):
        esperado = [(e["t"], e["per"], e["mn"], e["ac"], e["lado"], e["a"], e["p"], e["n"], e["f"], e["cat"]) for e in j["ev"]]
        achado = [(e[0], e[1], e[2], e[3], e[4], jg["atl"][e[5]]["a"], jg["atl"][e[5]]["p"], e[6], e[7], jg["cat"][e[8]]["n"] if e[8] >= 0 else None) for e in jg["ev"][k]]
        assert achado == esperado, j["n"]
        por_lado = Counter(e[4] for e in jg["ev"][k] if e[0] in "gpfc")
        assert (por_lado[0], por_lado[1]) == (j["gm"], j["gv"])
        gols += sum(1 for e in jg["ev"][k] if e[0] in "gpfc")
        cartoes += sum(1 for e in jg["ev"][k] if e[0] in "avs")
    assert (gols, cartoes) == (168, 413)
    assert Counter(e[0] for lista in jg["ev"] for e in lista) == {"g": 150, "p": 13, "f": 3, "c": 2, "a": 385, "v": 24, "s": 4}
    assert [c["n"] for c in jg["cat"]] == [n for n, _ in ref["exibicao"]]


@precisa_dados
def test_gol_contra_e_de_jogador_do_outro_lado_e_todo_lance_de_atleta_esta_na_relacao_do_clube_dele(montagem):
    jg = montagem["jg"]
    contra = 0
    for k, lista in enumerate(jg["ev"]):
        for e in lista:
            if e[7] != 0:
                continue
            lado_do_atleta = 1 - e[4] if e[0] == "c" else e[4]
            contra += e[0] == "c"
            assert e[6] in {c for c, _, _ in jg["esc"][k][lado_do_atleta]}
    assert contra == 2


@precisa_dados
def test_estatisticas_do_pacote_sao_as_144_linhas_da_espn_e_a_posse_fecha_em_cem(montagem, ref):
    jg = montagem["jg"]
    assert len(jg["st"]) == 72 and sum(len(s) for s in jg["st"]) == 144
    for k, j in enumerate(ref["jogos"]):
        assert jg["st"][k] == j["st"]
        assert 99 <= jg["st"][k][0][0] + jg["st"][k][1][0] <= 101


@precisa_dados
def test_totais_do_pacote_batem_com_o_gabarito(montagem):
    gab = {l["id_indicador"]: Decimal(l["valor"]) for l in ler_csv(PROC / "ref_indicadores.csv") if l["escopo"] == "geral"}
    js = montagem["jg"]["jogos"]
    assert sum(j["gm"] + j["gv"] for j in js) == gab["I02"] == 168
    assert sum(j["pu"] for j in js) == gab["I10"] and sum(j["pg"] for j in js) == gab["I14"]
    assert sum(j["rb"] for j in js) == centavos(gab["I16"]) and sum(j["rl"] for j in js) == centavos(gab["I17"]) and sum(j["ds"] for j in js) == centavos(gab["I38"])
    assert all(j["rb"] - j["ds"] == j["rl"] for j in js)


@precisa_dados
def test_arbitros_do_pacote_tem_os_jogos_do_cadastro_nos_sete_papeis(montagem):
    jg = montagem["jg"]
    papel = ["jogos_arbitro", "jogos_assistente", "jogos_assistente", "jogos_quarto_arbitro", "jogos_var", "jogos_var", "jogos_var"]
    por = defaultdict(Counter)
    for j in jg["jogos"]:
        for p, k in zip(papel, j["of"]):
            por[p][jg["pes"][k]] += 1
    for a in ler_csv(PROC / "dim_arbitro.csv"):
        for p in set(papel):
            assert por[p][a["nome"]] == int(a[p]), (a["nome"], p)
    assert sorted({jg["pes"][j["of"][0]] for j in jg["jogos"]}) and len({jg["pes"][j["of"][0]] for j in jg["jogos"]}) == 16


@precisa_dados
def test_nome_de_cada_atleta_e_o_mesmo_das_outras_telas(montagem):
    m = montagem["m"]
    versus = montagem["versus"]
    jg = montagem["jg"]
    gl = m.montar_dados_gl(versus)
    ds = m.montar_dados_ds(versus)
    vg = m.montar_dados_vg(versus)
    nomes_jg = {a["p"]: a["a"] for a in jg["atl"]}
    outros = {a["p"]: a["a"] for a in gl["atl"]}
    outros.update({a["p"]: a["a"] for a in ds["atl"]})
    outros.update({a["p"]: a["a"] for a in vg["art"]})
    assert len(outros) > 200
    for pessoa, nome in outros.items():
        assert nomes_jg[pessoa] == nome, pessoa


@precisa_dados
def test_nomes_de_comissao_pulam_sufixo_e_a_tela_nao_mostra_texto_livre_de_motivo(montagem, ref):
    m = montagem["m"]
    assert m.nome_de_comissao("Ricardo Catala Salgado Junior") == "Ricardo Salgado" and m.nome_de_comissao("Abel Ferreira") == "Abel Ferreira" and m.nome_de_comissao("Pelé") == "Pelé"
    assert m.nome_de_comissao("João Silva Filho") == "João Silva" and m.nome_de_comissao("Neto Junior") == "Neto Junior"
    nomes = {c["n"] for c in montagem["jg"]["cat"]} | {c["x"] for c in montagem["jg"]["cat"]}
    for motivo in ref["motivos"]:
        if motivo and not any(motivo in t for t in nomes):
            assert json.dumps(motivo, ensure_ascii=False) not in montagem["frag"], motivo[:40]
            assert len(motivo) < 40 or motivo not in montagem["frag"]


@precisa_dados
def test_textos_do_pacote_nao_citam_nada_interno(montagem):
    jg = montagem["jg"]
    assert len(jg["clubes"]) == 16 and len(jg["est"]) == 16
    for texto in [c[k] for c in jg["clubes"] for k in ("nome", "curto", "sigla")] + [a[k] for a in jg["atl"] for k in ("a", "p")] + jg["pes"] + [e[k] for e in jg["est"] for k in ("n", "m")] + [c[k] for c in jg["cat"] for k in ("n", "x")]:
        for ruim in INTERNOS:
            assert ruim not in texto, (ruim, texto)


# ---------- o montador para se os dados não fecharem ----------

def adulterar(monkeypatch, m, arquivo, mexer):
    original = m.ler_csv

    def leitor(caminho, *a, **k):
        linhas = original(caminho, *a, **k)
        if Path(caminho).name == arquivo:
            mexer(linhas)
        return linhas

    monkeypatch.setattr(m, "ler_csv", leitor)


def refazer(montagem):
    return montagem["m"].montar_dados_jg(montagem["versus"])


def para(montagem, monkeypatch, arquivo, mexer, trecho):
    adulterar(monkeypatch, montagem["m"], arquivo, mexer)
    with pytest.raises(SystemExit, match=trecho):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_gol_sumir(montagem, monkeypatch):
    para(montagem, monkeypatch, "fato_evento.csv", lambda ls: ls.pop(next(k for k, x in enumerate(ls) if x["tipo_evento"] == "gol")), "gols")


@precisa_dados
def test_o_montador_para_se_um_amarelo_sumir(montagem, monkeypatch):
    para(montagem, monkeypatch, "fato_evento.csv", lambda ls: ls.pop(next(k for k, x in enumerate(ls) if x["tipo_evento"] == "amarelo")), "amarelos e vermelhos")


@precisa_dados
def test_o_montador_para_se_o_placar_de_um_jogo_mudar(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "7")
        l["gols_visitante"] = str(int(l["gols_visitante"]) + 1)

    para(montagem, monkeypatch, "fato_partida.csv", mexer, "gols")


@precisa_dados
def test_o_montador_para_se_o_publico_de_um_jogo_mudar(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "3")
        l["publico_boletim"] = str(int(l["publico_boletim"]) + 1)

    para(montagem, monkeypatch, "fato_partida.csv", mexer, "público total")


@precisa_dados
def test_o_montador_para_se_a_renda_liquida_nao_fechar_com_as_despesas(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "3")
        l["renda_liquida"] = str(Decimal(l["renda_liquida"]) + 1)

    para(montagem, monkeypatch, "fato_partida.csv", mexer, "renda líquida")


@precisa_dados
def test_o_montador_para_se_um_jogo_mudar_de_arbitro(montagem, monkeypatch):
    def mexer(linhas):
        a, b = (next(x for x in linhas if x["numero_jogo"] == n) for n in ("1", "2"))
        a["id_assistente1"] = b["id_assistente1"]

    para(montagem, monkeypatch, "fato_partida.csv", mexer, "no cadastro")


@precisa_dados
def test_o_montador_para_se_um_titular_sumir_da_relacao(montagem, monkeypatch):
    para(montagem, monkeypatch, "fato_escalacao.csv", lambda ls: ls.pop(next(k for k, x in enumerate(ls) if x["situacao"] == "titular")), "11 titulares")


@precisa_dados
def test_o_montador_para_se_o_evento_citar_camisa_fora_da_relacao(montagem, monkeypatch):
    def mexer(linhas):
        next(x for x in linhas if x["tipo_evento"] == "gol")["numero_camisa"] = "99"

    para(montagem, monkeypatch, "fato_evento.csv", mexer, "camisa que não está")


@precisa_dados
def test_o_montador_para_se_uma_troca_citar_camisa_que_nao_esta_na_relacao(montagem, monkeypatch):
    def mexer(linhas):
        linhas[0]["numero_entrou"] = "98"

    para(montagem, monkeypatch, "fato_substituicao.csv", mexer, "troca com camisa")


@precisa_dados
def test_o_montador_para_se_um_titular_jogar_menos_de_90_sem_sair_nem_ser_expulso(montagem, monkeypatch):
    def mexer(linhas):
        seguros = [x for x in linhas if x["situacao"] == "titular" and x["minutos_jogados"] == "90" and x["gols"] == "0" and x["vermelhos"] == "0"]
        trocados = {(t["id_partida"], t["id_clube"], t["numero_saiu"]) for t in ler_csv(PROC / "fato_substituicao.csv")}
        x = next(x for x in seguros if (x["id_partida"], x["id_clube"], x["numero_camisa"]) not in trocados)
        x["minutos_jogados"] = "80"

    para(montagem, monkeypatch, "fato_escalacao.csv", mexer, "titular que não saiu")


@precisa_dados
def test_o_montador_para_se_um_reserva_jogar_sem_entrar_numa_troca(montagem, monkeypatch):
    def mexer(linhas):
        trocados = {(t["id_partida"], t["id_clube"], t["numero_entrou"]) for t in ler_csv(PROC / "fato_substituicao.csv")}
        x = next(x for x in linhas if x["situacao"] == "reserva" and (x["id_partida"], x["id_clube"], x["numero_camisa"]) not in trocados)
        x["minutos_jogados"] = "10"

    para(montagem, monkeypatch, "fato_escalacao.csv", mexer, "reserva jogou")


@precisa_dados
def test_o_montador_para_se_a_posse_de_bola_nao_somar_cem(montagem, monkeypatch):
    def mexer(linhas):
        linhas[0]["posse_pct"] = "10.0"

    para(montagem, monkeypatch, "fato_estatistica_time.csv", mexer, "posse de bola")


@precisa_dados
def test_o_montador_para_se_faltar_a_estatistica_de_um_time(montagem, monkeypatch):
    with pytest.raises((SystemExit, KeyError)):
        adulterar(monkeypatch, montagem["m"], "fato_estatistica_time.csv", lambda ls: ls.pop(0))
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_penalti_virar_gol_comum(montagem, monkeypatch):
    def mexer(linhas):
        next(x for x in linhas if x["tipo_evento"] == "gol_penalti")["tipo_evento"] = "gol"

    para(montagem, monkeypatch, "fato_evento.csv", mexer, "pênalti")


@precisa_dados
def test_a_falta_do_tecnico_de_um_jogo_nao_para_o_montador(montagem, monkeypatch):
    def mexer(linhas):
        linhas.pop(next(k for k, x in enumerate(linhas) if x["funcao"] == "Técnico"))

    adulterar(monkeypatch, montagem["m"], "fato_comissao.csv", mexer)
    jg = refazer(montagem)
    assert sum(1 for j in jg["jogos"] if j["tm"] is None or j["tv"] is None) == 2


# ---------- montagem da tela ----------

@precisa_dados
def test_fragmento_nao_deixa_marca_sobrando_e_so_age_quando_visivel(montagem):
    assert not re.search(r"__[A-Z_]+__", montagem["frag"])
    src = (PROTO / "jogos" / "fragmento.html").read_text(encoding="utf-8")
    assert src.count("__DADOS__") == 1 and "height:100%;min-height:320px" in src and "if(!raiz.offsetParent)return;" in src
    assert "window.PA.mods.jg={entrar:entrar}" in src and 'id="jgx"' in src
    for ruim in INTERNOS:
        assert ruim not in src, ruim
    assert "http://" not in src and "https://" not in src and "@import" not in src and "<link" not in src


@precisa_dados
def test_textos_da_tela_sao_todos_de_pelo_menos_16_pixels():
    src = (PROTO / "jogos" / "fragmento.html").read_text(encoding="utf-8")
    tamanhos = [int(x) for x in re.findall(r"font-size:(\d+)px", src)] + [int(x) for x in re.findall(r"font:[^;{}]*?(\d+)px", src)]
    assert tamanhos and min(tamanhos) >= 16, sorted(set(tamanhos))


@precisa_dados
def test_desenhos_nao_roubam_o_clique_nem_a_dica_e_as_listas_tem_barra_com_folga():
    src = (PROTO / "jogos" / "fragmento.html").read_text(encoding="utf-8")
    assert re.search(r"#jgx \.tip\{[^}]*pointer-events:none", src)
    rola = re.search(r"#jgx \.rola\{([^}]*)\}", src).group(1)
    assert "overflow-y:auto" in rola and "scrollbar-width:thin" in rola and re.search(r"padding-right:(1[2-9]|[2-9]\d)px", rola)
    assert re.search(r"#jgx \.rw::after\{[^}]*pointer-events:none", src)
    assert re.search(r"#jgx \.tl text\{[^}]*pointer-events:none", src) and re.search(r"#jgx \.tl \.eix\{[^}]*pointer-events:none", src)
    js = src[src.index("<script>"):]
    for fixo in ("72 jogos", "3.292", "3292", "706", "168 gols", "413", "no máximo 9", "16 clubes"):
        assert fixo not in js, fixo
    assert "ROW=42,LISTA_H=630" in js


@precisa_dados
def test_pagina_do_app_leva_a_tela_depois_da_disciplina_e_antes_do_publico():
    m = carregar("montar_app13_jgpg", "13_montar_app.py")
    dados = m.montar_todos_os_dados()
    frag = m.montar_fragmentos(dados)
    app = frag["app"]
    assert not re.search(r"__[A-Z_]+__", app)
    assert app.count('id="jgx"') == 1 and app.count('<section class="mod" id="mod-jg">') == 1 and m.dados_json(dados["jg"]) in app and frag["jg"] in app
    nav = re.search(r"<nav[^>]*>(.*?)</nav>", app, re.S).group(1)
    assert re.findall(r'data-mod="(\w+)"', nav) == ["vg", "vs", "clas", "gl", "ds", "jg", "fin", "conf"] == [t[0] for t in m.TELAS]
    assert '<button data-mod="jg"><span>Jogos</span></button>' in nav
    assert app.index('id="mod-vs"') < app.index('id="mod-jg"')


# ---------- comportamento (módulo simulado em Node) ----------

def tags(h, classe_base, extra=""):
    return re.findall(rf'<button class="{classe_base}( [a-z ]*)?" data-act="{extra}', h)


def rodadas_da(h):
    padrao = re.compile(r'<button class="rc( on)?( off)?" data-act="rod" data-v="(\d+)" data-tip="([^"]*)">(\d+)</button>')
    return [{"on": bool(a), "off": bool(b), "r": int(r), "tip": decod(t), "txt": int(x)} for a, b, r, t, x in padrao.findall(h)]


def escudos_da(h):
    padrao = re.compile(r'<button class="cb( on)?( off)?" data-act="clube" data-id="(\d+)" data-tip="([^"]*)">(.*?)</button>', re.S)
    return [{"on": bool(a), "off": bool(b), "id": int(i), "tip": decod(t), "logo": lg} for a, b, i, t, lg in padrao.findall(h)]


def resultados_da(h):
    padrao = re.compile(r'<button class="rs( on)?( off)?" data-act="res" data-v="(\w)" data-tip="([^"]*)">([^<]*)</button>')
    return [{"on": bool(a), "off": bool(b), "v": v, "tip": decod(t), "txt": decod(x)} for a, b, v, t, x in padrao.findall(h)]


def linhas_da(h):
    padrao = re.compile(r'<button class="jl( sel)?( pen)?" data-act="jogo" data-id="(\d+)" data-tip="([^"]*)"><span class="dt">([^<]*)</span><span class="nm l">([^<]*)</span><span class="es">(.*?)</span><span class="pl">([^<]*)</span><span class="es">(.*?)</span><span class="nm">([^<]*)</span></button>', re.S)
    return [{"sel": bool(a), "pen": bool(b), "n": int(n), "tip": decod(t), "dt": decod(d), "casa": decod(c), "lc": lc, "pl": decod(p), "lv": lv, "fora": decod(f)} for a, b, n, t, d, c, lc, p, lv, f in padrao.findall(h)]


def nome_chip(ref, r):
    return next(j["nome_rodada"] for j in ref["jogos"] if j["r"] == r)


def esperado_de(estado):
    return estado["fase"], estado["rod"], estado["clube"], estado["res"]


@precisa_dados
@precisa_node
def test_o_codigo_roda_no_node_sem_texto_estragado_em_todos_os_estados(saida):
    assert len(saida["filtros"]) == 73 and len(saida["jogos"]) == 72
    assert not any(e["ruim"] for e in saida["filtros"]) and not any(e["ruim"] for e in saida["jogos"])


@precisa_dados
@precisa_node
def test_filtros_pedidos_chegam_ao_estado_esperado_e_o_jogo_da_ficha_fica_na_lista(saida, ref):
    for f in saida["filtros"]:
        e = f["estado"]
        l = lista_de(ref, *esperado_de(e))
        assert l and e["jogo"] in {j["n"] for j in l}, f["pedido"]
    sem_nada = saida["filtros"][0]["estado"]
    assert (sem_nada["fase"], sem_nada["rod"], sem_nada["clube"], sem_nada["res"], sem_nada["jogo"]) == ("t", None, None, None, 72)
    assert any(esperado_de(f["estado"]) != (f["pedido"]["fase"], f["pedido"]["rod"], f["pedido"]["clube"], f["pedido"]["res"]) for f in saida["filtros"]), "combinações vazias precisam ser soltas"


@precisa_dados
@precisa_node
def test_lista_de_jogos_mostra_os_jogos_do_filtro_em_ordem_de_data_com_o_jogo_da_ficha_marcado(saida, ref, curto):
    for f in saida["filtros"]:
        e = f["estado"]
        l = lista_de(ref, *esperado_de(e))
        h = f["paineis"][0]
        linhas = linhas_da(h)
        assert [x["n"] for x in linhas] == [j["n"] for j in l] and f"{plural(len(l), 'jogo', 'jogos')}</small>" in h
        for x, j in zip(linhas, l):
            assert (x["dt"], x["casa"], x["pl"], x["fora"], x["sel"], x["pen"]) == (data_br(j["d"]), curto[j["m"]], f"{j['gm']} × {j['gv']}", curto[j["v"]], j["n"] == e["jogo"], j["pm"] is not None), (f["pedido"], j["n"])
            secoes = x["tip"].split("||")
            extra = [("Pênaltis", f"{j['pm']} × {j['pv']}")] if j["pm"] is not None else []
            assert secoes[0] == f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}" and tabela_tip(secoes[1]) == linhas_do_jogo(j) + extra and secoes[2] == "~Clique para ver a ficha do jogo."
            assert "<img" in x["lc"] + x["lv"] or 'class="sg"' in x["lc"] + x["lv"]
        assert sum(1 for x in linhas if x["sel"]) == 1
        assert 'data-r="jg" style="max-height:630px"' in h


@precisa_dados
@precisa_node
def test_rodadas_clubes_e_resultados_marcam_o_escolhido_e_apagam_o_que_deixaria_a_lista_vazia(saida, ref, curto):
    for f in saida["filtros"]:
        e = f["estado"]
        fase, rod, clube, res = esperado_de(e)
        h = f["paineis"][0]
        chips = rodadas_da(h)
        assert [c["r"] for c in chips] == ref["rodadas"] == list(range(1, 13)) and all(c["txt"] == c["r"] for c in chips)
        for c in chips:
            n = len(lista_de(ref, fase, c["r"], clube, res))
            assert (c["on"], c["off"]) == (rod == c["r"], n == 0), (f["pedido"], c["r"])
            secoes = c["tip"].split("||")
            assert secoes[0] == nome_chip(ref, c["r"]) and secoes[1] == ("Nenhum jogo com os outros filtros." if n == 0 else plural(n, "jogo", "jogos") + (" na lista. Clique para soltar." if c["on"] else " com os outros filtros."))
        crests = escudos_da(h)
        ordem = sorted(curto, key=lambda i: curto[i])
        assert [c["id"] for c in crests] == ordem and len(crests) == 16
        for c in crests:
            n = len(lista_de(ref, fase, rod, c["id"], res))
            assert (c["on"], c["off"]) == (clube == c["id"], n == 0), (f["pedido"], c["id"])
            secoes = c["tip"].split("||")
            assert secoes[0] == curto[c["id"]] and secoes[1] == ("Nenhum jogo com os outros filtros." if n == 0 else plural(n, "jogo", "jogos") + (" na lista. Clique para soltar." if c["on"] else " com os outros filtros."))
            assert "<img" in c["logo"] or 'class="sg"' in c["logo"]
        rs = resultados_da(h)
        assert [(r["v"], r["txt"]) for r in rs] == [("m", "Mandante"), ("e", "Empate"), ("v", "Visitante")]
        for r in rs:
            n = len(lista_de(ref, fase, rod, clube, r["v"]))
            assert (r["on"], r["off"]) == (res == r["v"], n == 0), (f["pedido"], r["v"])
            secoes = r["tip"].split("||")
            assert secoes[0] == RES[r["v"]] and secoes[1] == ("Nenhum jogo com os outros filtros." if n == 0 else plural(n, "jogo", "jogos") + (" (os que foram para os pênaltis contam como empate no tempo normal)" if r["v"] == "e" else "") + ".")


@precisa_dados
@precisa_node
def test_lista_rola_para_deixar_o_jogo_escolhido_a_vista(saida):
    for f in saida["filtros"]:
        e = f["estado"]
        l = [x["n"] for x in linhas_da(f["paineis"][0])]
        k = l.index(e["jogo"])
        assert f["topo"] <= k * ROW and (k + 1) * ROW <= f["topo"] + LISTA_H, (f["pedido"], f["topo"], k)
    for r in saida["rolagem"]:
        assert r["topo"] >= 0
    descida = saida["rolagem"][:72]
    assert descida[0]["topo"] == 0 and all(0 <= descida[k]["topo"] <= max(0, (k + 1) * ROW - 1) for k in range(72))
    assert descida[-1]["topo"] == 72 * ROW - LISTA_H and all(b["topo"] >= a["topo"] for a, b in zip(descida, descida[1:]))
    subida = saida["rolagem"][72:]
    assert subida[0]["topo"] == descida[-1]["topo"] and subida[-1]["topo"] == 0 and all(b["topo"] <= a["topo"] for a, b in zip(subida, subida[1:]))


def cabecalho_da(h):
    nomes = re.findall(r'<div class="eq c([01])">.*?<div><b>([^<]*)</b><small>([^<]*)</small></div>', h, re.S)
    sc = re.search(r'<div class="sc" data-tip="([^"]*)"><b>([^<]*)</b><small>([^<]*)</small></div>', h)
    metas = re.findall(r'<div class="mt" data-tip="([^"]*)">([^<]*)</div>', h)
    return [(l, decod(n), decod(p)) for l, n, p in nomes], (decod(sc.group(1)), decod(sc.group(2)), decod(sc.group(3))), [(decod(t), decod(x)) for t, x in metas]


@precisa_dados
@precisa_node
def test_ficha_de_cada_jogo_mostra_clubes_placar_pernaltis_data_estadio_e_arbitro(saida, ref, curto):
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        nomes, sc, metas = cabecalho_da(e["paineis"][0])
        assert nomes == [("0", curto[j["m"]], "Mandante"), ("1", curto[j["v"]], "Visitante")], j["n"]
        assert sc[1] == f"{j['gm']} × {j['gv']}" and sc[2] == (f"Pênaltis {j['pm']} × {j['pv']}" if j["pm"] is not None else "")
        secoes = sc[0].split("||")
        assert secoes[0] == f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}" and tabela_tip(secoes[1]) == [("Tempo normal", f"{j['gm']} × {j['gv']}")] + ([("Pênaltis", f"{j['pm']} × {j['pv']}")] if j["pm"] is not None else [])
        assert secoes[2] == ("~Tempo normal e disputa de pênaltis: os dois placares estão na súmula oficial." if j["pm"] is not None else "~Placar da súmula oficial.")
        assert metas[0][1] == f"{j['nome_rodada']} · {DIAS[j['w']]}, {data_longa(j['d'])} às {j['h']}" and metas[1][1] == f"{j['estadio']} · {j['cidade']} · árbitro {j['of'][0]}"
        assert tabela_tip(metas[0][0].split("||")[1]) == linhas_do_jogo(j) and tabela_tip(metas[1][0].split("||")[1]) == [("Estádio", j["estadio"]), ("Cidade", j["cidade"]), ("Árbitro", j["of"][0])]
    assert cabecalho_da(next(e for e in saida["jogos"] if e["n"] == 68)["paineis"][0])[1][2] == "Pênaltis 7 × 8"


def geometria(j, ev, subs):
    e1, e2 = j["a1"], j["a2"]
    for e in ev + subs:
        if e["per"] == 1 and e["ac"] > e1:
            e1 = e["ac"]
        if e["per"] == 2 and e["ac"] > e2:
            e2 = e["ac"]
    x0, x1, gap = 60, 1240, 36
    u = (x1 - x0 - gap) / (90 + e1 + e2)

    def x(per, mn, ac):
        if per == 1:
            return x0 + (mn + ac) * u
        if per == 2:
            return x0 + (45 + e1) * u + gap + ((mn - 45) + ac) * u
        if per == 3:
            return x0 + (45 + e1) * u + gap / 2
        return x1 - 10

    return e1, e2, u, x


def marcadores_da(h):
    achados = []
    for tip, inner in re.findall(r'<g class="mk" data-tip="([^"]*)">(.*?)</g>', h, re.S):
        tip = decod(tip)
        titulo = tip.split("||")[0]
        circ = re.search(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="11" fill="(#[0-9a-f]{3,6})"', inner)
        rects = re.findall(r'<rect x="([\d.]+)" y="([\d.]+)" width="(\d+)" height="(\d+)" rx="2" fill="(#[0-9a-f]{6})"/>', inner)
        letra = re.search(r'>([PFC])</text>', inner)
        if circ:
            achados.append({"tit": titulo, "tip": tip, "x": float(circ.group(1)), "y": float(circ.group(2)), "w": 22, "letra": letra.group(1) if letra else None, "cor": circ.group(3)})
        elif len(rects) == 2:
            achados.append({"tit": titulo, "tip": tip, "x": float(rects[0][0]) + 12, "y": float(rects[1][1]) + 10, "w": 20, "cores": [r[4] for r in rects]})
        else:
            x, y, w, hh, cor = rects[0]
            achados.append({"tit": titulo, "tip": tip, "x": float(x) + int(w) / 2, "y": float(y) + int(hh) / 2, "w": int(w), "cor": cor})
    return achados


@precisa_dados
@precisa_node
def test_linha_do_jogo_desenha_cada_gol_cartao_e_troca_no_minuto_e_no_lado_certos(saida, ref, curto):
    chave = {"Gol": "g", "Gol de pênalti": "p", "Gol de falta": "f", "Gol contra": "c", "Cartão amarelo": "a", "Cartão vermelho": "v", "Segundo amarelo": "s"}
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        h = e["paineis"][1]
        marcas = marcadores_da(h)
        subs = [{"per": s["per"], "ac": s["ac"], "mn": s["mn"], "lado": s["lado"]} for s in j["sub"]]
        e1, e2, u, xpos = geometria(j, j["ev"], subs)
        esperado = []
        for l in j["ev"]:
            x = xpos(l["per"], l["mn"], l["ac"]) if l["per"] != 4 and l["mn"] is not None else 1230
            esperado.append((l["lado"], l["t"], x))
        for s in j["sub"]:
            esperado.append((s["lado"], "t", xpos(s["per"], s["mn"] or 0, s["ac"])))
        achado = []
        for m in marcas:
            lado = 0 if m["y"] < 96 else 1
            t = "t" if m["tit"].startswith("Troca ·") else chave[m["tit"]]
            achado.append((lado, t, m["x"]))
        assert [(a[0], a[1]) for a in sorted(achado)] == [(b[0], b[1]) for b in sorted(esperado)], j["n"]
        assert all(abs(a[2] - b[2]) < 0.11 for a, b in zip(sorted(achado), sorted(esperado))), j["n"]
        for m in marcas:
            if m["tit"] in ("Gol", "Gol de pênalti", "Gol de falta", "Gol contra"):
                assert (m["letra"], m["cor"]) == ({"Gol": None, "Gol de pênalti": "P", "Gol de falta": "F", "Gol contra": "C"}[m["tit"]], "#ff5470" if m["tit"] == "Gol contra" else "#fff")
            elif m["tit"] == "Cartão amarelo":
                assert m["cor"] == "#ffd166"
            elif m["tit"] == "Cartão vermelho":
                assert m["cor"] == "#ff5470"
            elif m["tit"] == "Segundo amarelo":
                assert m["cores"] == ["#ffd166", "#ff5470"]
        for k, a in enumerate(marcas):
            for b in marcas[k + 1:]:
                assert not (abs(a["x"] - b["x"]) < 12 and abs(a["y"] - b["y"]) < 8), (j["n"], a["tit"], b["tit"])
        assert f"{plural(sum(1 for l in j['ev'] if l['t'] in 'gpfc'), 'gol', 'gols')} · {plural(sum(1 for l in j['ev'] if l['t'] in 'avs'), 'cartão', 'cartões')} · {plural(len(j['sub']), 'troca', 'trocas')}" in h
        assert h.count("<image") == (2 if "<image" in h else 0)
        assert e1 >= j["a1"] and e2 >= j["a2"]


@precisa_dados
@precisa_node
def test_dica_de_cada_marcador_traz_minuto_quem_clube_e_motivo(saida, ref, curto):
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        h = e["paineis"][1]
        marcas = marcadores_da(h)
        tips_lances = [m["tip"] for m in marcas if not m["tit"].startswith("Troca ·")]
        esperados = []
        for l in j["ev"]:
            lado_clube = curto[j["m"] if l["lado"] == 0 else j["v"]]
            gol = l["t"] in "gpfc"
            minuto = "pós-jogo" if l["per"] == 4 else "—" if l["mn"] is None else f"{l['mn']}" + (f"+{l['ac']}" if l["ac"] > 0 else "") + "'"
            quem = f"{l['a']} (camisa {l['n']})" if l["f"] == 0 else f"{l['a']} ({FUNCAO_NOME[l['f']].lower()})"
            linhas = [("Minuto", minuto), ("Quem", quem)]
            if gol:
                linhas.append(("Gol do", lado_clube))
                if l["t"] == "c":
                    linhas.append(("Jogador do", curto[j["v"] if l["lado"] == 0 else j["m"]]))
                nota = f"~{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}"
            else:
                linhas.append(("Clube", lado_clube))
                linhas.append(("Motivo", l["cat"]))
                if l["t"] != "a":
                    linhas.append(("Efeito", "expulsão"))
                nota = "~" + dict(ref["exibicao"])[l["cat"]]
            esperados.append("||".join([TIPO_NOME[l["t"]], "@" + "\n".join(f"{a}::{b}" for a, b in linhas), nota]))
        assert sorted(tips_lances) == sorted(esperados), j["n"]
        tips_trocas = sorted(m["tip"] for m in marcas if m["tit"].startswith("Troca ·"))
        assert len(tips_trocas) == len(j["sub"])


def elenco_da(h):
    cab = re.findall(r'<div class="elh"><div class="tn">(.*?)<b>([^<]*)</b></div><div class="tc" data-tip="([^"]*)">([^<]*)</div></div>', h, re.S)
    linhas = re.findall(r'<div class="ln( nj)?" data-tip="([^"]*)"><span class="cm">(\d+)</span><span class="np">([^<]*)</span><span class="ic">(.*?)</span></div>', h, re.S)
    bancos = h.count('<div class="bn">Banco</div>')
    return cab, linhas, bancos


def icones_de(ic):
    return {"g": [int(x) for x in re.findall(r'<i class="bg">(\d+)</i>', ic)], "gc": [int(x) for x in re.findall(r'<i class="bg gc">(\d+)</i>', ic)], "a": ic.count('<i class="ca"></i>'), "v": ic.count('<i class="cv"></i>'),
            "sx": re.findall(r'<span class="sx">↓([^<]*)</span>', ic), "se": re.findall(r'<span class="se">↑([^<]*)</span>', ic)}


def sub_txt(s):
    return "int." if s["per"] == 3 else f"{s['mn']}" + (f"+{s['ac']}" if s["ac"] > 0 else "") + "'"


def sub_longo(s):
    return "no intervalo" if s["per"] == 3 else f"aos {s['mn']}" + (f"+{s['ac']}" if s["ac"] > 0 else "") + " min" + (" do 1º tempo" if s["per"] == 1 else " do 2º tempo")


@precisa_dados
@precisa_node
def test_escalacoes_mostram_titulares_banco_tecnico_icones_e_dica_de_cada_atleta(saida, ref, curto):
    tem_cortado, fim_do_jogo = set(), []
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        h = e["paineis"][2]
        cab, linhas, bancos = elenco_da(h)
        assert bancos == 2 and f"{plural(len(j['esc'][0]) + len(j['esc'][1]), 'relacionado', 'relacionados')}</small>" in h and 'data-r="el" style="max-height:308px"' in h
        partes = h.split('<div class="bn">Banco</div>')
        assert [x.count('<div class="ln') for x in partes] == [11, len(j["esc"][0]) - 11 + 11, len(j["esc"][1]) - 11], "o banco começa depois dos 11 titulares de cada time"
        assert [c[1] for c in cab] == [curto[j["m"]], curto[j["v"]]]
        for lado, c in enumerate(cab):
            tec = j["tec"][lado]
            assert c[3] == ("Técnico não consta na súmula" if tec is None else "Técnico: " + j["tec_curto"][lado]), j["n"]
            secoes = decod(c[2]).split("||")
            assert secoes[0] == "Técnico" and secoes[1] == ("O técnico deste time não consta na súmula deste jogo." if tec is None else tec)
        esperados = j["esc"][0] + j["esc"][1]
        assert len(linhas) == len(esperados)
        for lado, base in ((0, 0), (1, len(j["esc"][0]))):
            for k, r in enumerate(j["esc"][lado]):
                nj, tip, cm, np_, ic = linhas[base + k]
                entrou = next((s for s in j["sub"] if s["lado"] == lado and s["entrou"] == r["c"]), None)
                saiu = next((s for s in j["sub"] if s["lado"] == lado and s["saiu"] == r["c"]), None)
                assert (bool(nj), int(cm), decod(np_)) == (r["mj"] == 0 and entrou is None, r["c"], r["a"]), (j["n"], lado, k)
                gols = [x for x in j["ev"] if x["f"] == 0 and x["n"] == r["c"] and (1 - x["lado"] if x["t"] == "c" else x["lado"]) == lado]
                g = sum(1 for x in gols if x["t"] in "gpf")
                gc = sum(1 for x in gols if x["t"] == "c")
                am = sum(1 for x in gols if x["t"] == "a")
                vm = sum(1 for x in gols if x["t"] in "vs")
                ico = icones_de(ic)
                assert (ico["g"], ico["gc"], ico["a"] > 0, ico["v"] > 0) == ([g] if g else [], [gc] if gc else [], am > 0, vm > 0), (j["n"], r["a"])
                assert ico["sx"] == ([sub_txt(saiu)] if saiu else []) and ico["se"] == ([sub_txt(entrou)] if entrou else []), (j["n"], r["a"])
                secoes = decod(tip).split("||")
                lin = [("Camisa", str(r["c"])), ("Situação", "Titular" if k < 11 else "Reserva"), ("Minutos jogados", str(r["mj"]) if r["mj"] > 0 else "0 (entrou no fim do jogo)" if entrou else "não entrou")]
                if entrou:
                    lin.append(("Entrou", sub_longo(entrou)))
                if saiu:
                    lin.append(("Saiu", sub_longo(saiu)))
                if g:
                    lin.append(("Gols", str(g)))
                if gc:
                    lin.append(("Gols contra", str(gc)))
                if am:
                    lin.append(("Amarelos", str(am)))
                if vm:
                    lin.append(("Vermelhos", str(vm)))
                conc = (entrou and entrou["conc"]) or (saiu and saiu["conc"])
                cortado = ref["atletas"][r["ida"]]["nome_truncado"] == "1" and not (ref["pessoa_de"].get(r["ida"]) and len(ref["pessoa_de"][r["ida"]]) > len(ref["atletas"][r["ida"]]["nome"]))
                assert secoes[0] == r["p"] and tabela_tip(secoes[1]) == lin and secoes[2] == ("~Troca por concussão." if conc else "~" + curto[j["m"] if lado == 0 else j["v"]]), (j["n"], r["a"])
                assert secoes[3:] == (["~O nome vem cortado em 33 letras na súmula e pode estar incompleto."] if cortado else []), (j["n"], r["a"])
                if cortado:
                    tem_cortado.add(r["ida"])
                if r["mj"] == 0 and entrou is not None:
                    fim_do_jogo.append((j["n"], r["c"]))
    assert len(fim_do_jogo) == 19 and {n for n, _ in fim_do_jogo} == {6, 7, 28, 31, 38, 47, 50, 52, 56, 61, 64, 67, 71}
    assert len(tem_cortado) == 41


def lances_da(h):
    padrao = re.compile(r'<div class="ev" data-tip="([^"]*)"><span class="mn">([^<]*)</span><div class="tx"><b>([^<]*)</b><small>([^<]*)</small></div><span class="es">(.*?)</span></div>', re.S)
    return [{"tip": decod(t), "mn": decod(m), "nome": decod(n), "tipo": decod(s), "logo": lg} for t, m, n, s, lg in padrao.findall(h)]


@precisa_dados
@precisa_node
def test_lances_listam_gols_e_cartoes_em_ordem_com_minuto_atleta_tipo_e_o_clube_certo(saida, ref, curto):
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        h = e["paineis"][3]
        linhas = lances_da(h)
        assert len(linhas) == len(j["ev"]), j["n"]
        g = sum(1 for l in j["ev"] if l["t"] in "gpfc")
        assert f"{plural(g, 'gol', 'gols')} · {plural(len(j['ev']) - g, 'cartão', 'cartões')}</small>" in h and 'data-r="ev" style="max-height:366px"' in h
        for x, l in zip(linhas, j["ev"]):
            minuto = "pós" if l["per"] == 4 else "—" if l["mn"] is None else f"{l['mn']}" + (f"+{l['ac']}" if l["ac"] > 0 else "") + "'"
            assert (x["mn"], x["nome"], x["tipo"]) == (minuto, l["a"], TIPO_NOME[l["t"]]), (j["n"], l)
            assert x["tip"].startswith(TIPO_NOME[l["t"]] + "||@Minuto::")
            assert "<img" in x["logo"] or 'class="sg"' in x["logo"]
    assert all(ref["por_n"][e["n"]]["ev"] for e in saida["jogos"])


def kvs_da(h):
    padrao = re.compile(r'<div class="kv( sm)?" data-tip="([^"]*)"><span>([^<]*)</span><b( class="neg")?>([^<]*)</b></div>')
    return [{"tip": decod(t), "rot": decod(r), "val": decod(v), "neg": bool(n)} for _, t, r, n, v in padrao.findall(h)]


def estatisticas_da(h):
    padrao = re.compile(r'<div class="er" data-tip="([^"]*)"><div class="nm"><b>([^<]*)</b><span>([^<]*)</span><b>([^<]*)</b></div><div class="sp"><i class="h" style="width:([\d.]+)%"></i><i class="a" style="width:([\d.]+)%"></i></div></div>')
    return [{"tip": decod(t), "a": decod(a), "rot": decod(r), "b": decod(b), "wa": float(wa), "wb": float(wb)} for t, a, r, b, wa, wb in padrao.findall(h)]


@precisa_dados
@precisa_node
def test_aba_publico_traz_publico_pagantes_renda_despesas_liquida_ticket_e_estadio(saida, ref):
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        h = e["abas"]["pu"]
        kv = kvs_da(h)
        ticket = int((Decimal(j["rb"]) / j["pg"]).quantize(Decimal(1), rounding=ROUND_HALF_UP)) if j["pg"] else None
        esperado = [("Público", fmt(j["pu"])), ("Pagantes", fmt(j["pg"])), ("Renda bruta", reais(j["rb"])), ("Despesas", reais(j["ds"])), ("Renda líquida", reais(j["rl"])), ("Ticket médio", reais(ticket) if ticket is not None else "—"), ("Estádio", f"{j['estadio']} · {j['cidade']}")]
        assert [(k["rot"], k["val"]) for k in kv] == esperado, j["n"]
        assert [k["neg"] for k in kv] == [False, False, False, False, j["rl"] < 0, False, False]
        assert kv[1]["tip"].split("||")[1] == f"Pessoas que pagaram ingresso: {pct(j['pg'], j['pu'])} do público."
        assert kv[6]["tip"].split("||")[2] == "~A capacidade dos estádios não foi verificada em fonte oficial, por isso a tela não mostra a ocupação."
        assert 'class="tabs"' in h and h.count('data-act="aba"') == 3
    assert any(ref["por_n"][e["n"]]["rl"] < 0 for e in saida["jogos"]) and any(ref["por_n"][e["n"]]["rl"] >= 0 for e in saida["jogos"])


@precisa_dados
@precisa_node
def test_aba_arbitragem_lista_os_sete_do_jogo_acrescimos_e_horarios_ou_o_aviso_do_jogo_47(saida, ref):
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        h = e["abas"]["ar"]
        pes = re.findall(r'<div class="pe" data-tip="([^"]*)"><span>([^<]*)</span><b>([^<]*)</b></div>', h)
        assert [(decod(r), decod(n)) for _, r, n in pes] == list(zip(PAPEIS, j["of"])), j["n"]
        for t, r, n in pes:
            assert decod(t).split("||")[:2] == [decod(r), decod(n)] and decod(t).endswith("||~Árbitros do jogo, como na súmula oficial.")
        kv = kvs_da(h)
        assert kv[0]["rot"] == "Acréscimos" and kv[0]["val"] == f"{j['a1']} + {j['a2']} min"
        if j["n"] == 47:
            assert len(kv) == 1 and "Os horários desta súmula não são confiáveis" in h and "Regra A33" in decod(h)
        else:
            assert [(k["rot"], k["val"]) for k in kv[1:]] == [("1º tempo", f"{j['hr'][0]}–{j['hr'][1]}"), ("2º tempo", f"{j['hr'][2]}–{j['hr'][3]}")] and len(kv) == 3 and "não são confiáveis" not in h


@precisa_dados
@precisa_node
def test_aba_estatisticas_traz_nove_barras_da_espn_com_a_divisao_entre_os_dois_times(saida, ref, curto):
    for e in saida["jogos"]:
        j = ref["por_n"][e["n"]]
        h = e["abas"]["es"]
        assert "ESPN, não oficial" in h
        barras = estatisticas_da(h)
        assert [b["rot"] for b in barras] == [r for r, _ in STATS]
        for b, (rot, k) in zip(barras, STATS):
            a, c = j["st"][0][k], j["st"][1][k]
            va, vc = (f"{fmt(a, 1)}%", f"{fmt(c, 1)}%") if k == 0 else (str(a), str(c))
            assert (b["a"], b["b"]) == (va, vc), (j["n"], rot)
            total = a + c
            assert abs(b["wa"] - (100 * a / total if total else 50)) < 0.01 and abs(b["wb"] - (100 * c / total if total else 50)) < 0.01
            secoes = b["tip"].split("||")
            lin = [(curto[j["m"]], va), (curto[j["v"]], vc)]
            if k == 7:
                lin += [("Passes feitos", f"{j['st'][0][6]} × {j['st'][1][6]}"), ("Acerto de passe", f"{pct(a, j['st'][0][6])} × {pct(c, j['st'][1][6])}")]
            assert secoes[0] == rot and tabela_tip(secoes[1]) == lin and secoes[2] == "~ESPN, não oficial."


@precisa_dados
@precisa_node
def test_escala_do_tempo_cresce_quando_uma_troca_ou_um_lance_passa_do_acrescimo_oficial(saida, ref):
    g = saida["geometriaSintetica"]
    assert g["antes"] == [g["a1"], g["a2"]] and g["depois"] == [g["antes"][0] + 5, g["antes"][1] + 4]


@precisa_dados
@precisa_node
def test_cabecalho_botoes_de_fase_limpar_e_subtitulo(saida, ref, curto):
    for f in saida["filtros"]:
        e = f["estado"]
        fase, rod, clube, res = esperado_de(e)
        l = lista_de(ref, fase, rod, clube, res)
        partes = ([curto[clube]] if clube is not None else []) + ([FS[fase]] if fase != "t" else []) + ([nome_chip(ref, rod)] if rod is not None else []) + ([RES[res]] if res is not None else [])
        esperado = (" · ".join(partes) if partes else "Calendário e ficha de cada jogo") + " · " + plural(len(l), "jogo", "jogos") + " na lista"
        assert f["sub"] == esperado, f["pedido"]
        chips = re.findall(r'<button class="chp( on)?" data-act="fase" data-v="(\w)"[^>]*><span>([^<]*)</span></button>', f["ctl"])
        assert [(x[1], x[2], bool(x[0])) for x in chips] == [(k, FS[k], k == fase) for k in "tpm"]
        assert ("lim off" in f["ctl"]) == (not partes) and 'data-act="ajuda"' in f["ctl"]


@precisa_dados
@precisa_node
def test_rodape_e_ajuda_explicam_a_tela(saida):
    r = saida["rodape"]
    assert "Dados: súmulas oficiais da FPF" in r["rod"] and "escalações conferidas com as súmulas" in r["rod"] and "estatísticas: ESPN, não oficial" in r["rod"] and "Projeto independente, sem vínculo com a FPF" in r["rod"]
    assert r["aj"].count("<li>") == 4 and re.search(r'<button[^>]*data-act="ajuda-fechar"[^>]*data-tip="[^"]+"[^>]*>Entendi</button>', r["aj"])
    for palavra in ("Titular e banco", "Troca", "Cartões", "ESPN, não oficial", "setas"):
        assert palavra in r["aj"]
    tip = decod(re.search(r'data-tip="([^"]*)"', r["rod"]).group(1))
    assert tip.startswith("De onde vêm os números||Placar, escalações, trocas, gols, cartões") and tabela_tip(tip.split("||")[2]) == [("Jogos", "72"), ("Relacionados", "3.292"), ("Trocas", "706")]


def modelo(est, acao, id_, v, ref):
    fase, rod, clube, res, jogo, aba = est["fase"], est["rod"], est["clube"], est["res"], est["jogo"], est["aba"]
    rodadas = ref["rodadas"]
    clubes = {j[k] for j in ref["jogos"] for k in ("m", "v")}

    def normalizar(fase, rod, clube, res, jogo):
        if not lista_de(ref, fase, rod, clube, res) and res is not None:
            res = None
        if not lista_de(ref, fase, rod, clube, res) and clube is not None:
            clube = None
        if not lista_de(ref, fase, rod, clube, res) and rod is not None:
            rod = None
        l = lista_de(ref, fase, rod, clube, res)
        if jogo not in {j["n"] for j in l}:
            jogo = l[0]["n"]
        return {"fase": fase, "rod": rod, "clube": clube, "res": res, "jogo": jogo, "aba": aba, "ajuda": est["ajuda"]}

    if acao == "fase":
        return normalizar(v, rod, clube, res, jogo) if v in ("t", "p", "m") else est
    if acao == "rod":
        if v is None or not v.isdigit() or int(v) not in rodadas:
            return est
        r = int(v)
        novo = None if rod == r else r
        return normalizar(fase, novo, clube, res, jogo) if lista_de(ref, fase, novo, clube, res) else est
    if acao == "clube":
        if id_ is None or not id_.isdigit() or int(id_) not in clubes:
            return est
        c = int(id_)
        novo = None if clube == c else c
        return normalizar(fase, rod, novo, res, jogo) if lista_de(ref, fase, rod, novo, res) else est
    if acao == "res":
        if v not in ("m", "e", "v"):
            return est
        novo = None if res == v else v
        return normalizar(fase, rod, clube, novo, jogo) if lista_de(ref, fase, rod, clube, novo) else est
    if acao == "jogo":
        if id_ is None or not id_.isdigit() or int(id_) not in {j["n"] for j in lista_de(ref, fase, rod, clube, res)}:
            return est
        return {**est, "jogo": int(id_)}
    if acao == "aba":
        return {**est, "aba": v} if v in ("pu", "ar", "es") else est
    if acao == "limpar":
        return normalizar("t", None, None, None, jogo)
    return est


@precisa_dados
@precisa_node
def test_cliques_nos_botoes_gerados_levam_ao_estado_esperado(saida, ref):
    assert set(saida["acoesVistas"]) == {"aba", "ajuda", "ajuda-fechar", "clube", "fase", "jogo", "limpar", "res", "rod"}
    assert len(saida["cliques"]) == 38
    for c in saida["cliques"]:
        a, d = c["antes"], c["depois"]
        if c["act"] in ("fase", "rod", "clube", "res", "jogo", "aba", "limpar"):
            esperado = modelo(a, c["act"], c["id"], c["v"], ref)
            assert d == esperado, c["rot"]
        elif c["act"] == "ajuda":
            assert d == {**a, "ajuda": True}
        elif c["act"] == "ajuda-fechar":
            assert d == {**a, "ajuda": False}
        else:
            assert c["rot"] == "clique fora da ajuda" and a["ajuda"] is True and d == {**a, "ajuda": False}
    por = {c["rot"]: c for c in saida["cliques"]}
    solta = por["chip mata-mata solta o clube que nao jogou nela"]
    assert solta["antes"]["clube"] == saida["foraDoMata"] and solta["depois"]["clube"] is None and solta["depois"]["fase"] == "m"
    assert por["chip mata-mata solta a rodada que nao existe nela"]["antes"]["rod"] == 3 and por["chip mata-mata solta a rodada que nao existe nela"]["depois"]["rod"] is None
    assert por["rodada 3 de novo solta"]["depois"]["rod"] is None and por["rodada 3 outra vez"]["depois"]["rod"] == 3
    assert por["rodada 12 fora da 1a fase"]["depois"] == por["rodada 12 fora da 1a fase"]["antes"], "rodada que não existe na fase é ignorada"
    assert por["clube no mata-mata"]["depois"]["clube"] == saida["noMata"] and por["resultado visitante de novo solta"]["depois"]["res"] is None
    do_quadro_de_rodadas = [c for c in saida["cliques"] if c["rot"].startswith("rodada")]
    assert len(do_quadro_de_rodadas) == 6 and all(c["tag"] == "rc" for c in do_quadro_de_rodadas)
    assert por["jogo da lista"]["tag"] == "jl" and por["aba arbitragem"]["depois"]["aba"] == "ar"
    caso = por["chip mata-mata solta so o resultado"]
    assert caso["antes"]["clube"] == saida["casoDoResultado"]["c"] and caso["antes"]["res"] == saida["casoDoResultado"]["r"] and (caso["depois"]["fase"], caso["depois"]["clube"], caso["depois"]["res"]) == ("m", saida["casoDoResultado"]["c"], None)
    f12 = saida["final12"]
    assert por["clube que nao jogou a rodada 12"]["depois"] == por["clube que nao jogou a rodada 12"]["antes"] and por["clube que nao jogou a rodada 12"]["depois"]["res"] == saida["final12"]["res"]
    assert por["resultado que nao houve na rodada 12"]["depois"] == por["resultado que nao houve na rodada 12"]["antes"] and por["resultado que nao houve na rodada 12"]["depois"]["res"] == saida["final12"]["res"], "o que não combina é ignorado, sem soltar o que já estava escolhido"
    assert por["resultado que houve na rodada 12"]["depois"]["res"] == f12["res"] and por["clube que jogou a rodada 12"]["depois"]["clube"] == f12["m"] and por["o mesmo clube de novo solta"]["depois"]["clube"] is None
    assert f12["fora"] not in (f12["m"], f12["v"]) and f12["outro"] != f12["res"]
    for esperado in (saida["clubeInexistente"], saida["clubeSemId"], saida["clubeTexto"], saida["rodadaInexistente"], saida["rodadaTexto"], saida["resultadoInvalido"], saida["resultadoProto"], saida["faseProto"], saida["faseInvalida"], saida["abaInvalida"], saida["jogoInexistente"], saida["jogoTexto"]):
        assert esperado == {"fase": "t", "rod": None, "clube": None, "res": None, "jogo": 72, "aba": "pu", "ajuda": False}
    assert saida["clubeForaDaFase"]["clube"] is None and saida["clubeForaDaFase"]["fase"] == "m"
    assert saida["jogoForaDaLista"]["jogo"] == saida["clubeForaDaFase"]["jogo"] and saida["rodadaForaDaFase"]["rod"] is None


@precisa_dados
@precisa_node
def test_teclas_esc_soltam_resultado_clube_rodada_e_fase_nessa_ordem_e_as_setas_andam_na_lista(saida, ref):
    t = {x["rot"]: x for x in saida["teclas"]}
    no = saida["noMata"]
    livre = {"fase": "t", "rod": None, "clube": None, "res": None, "ajuda": False}
    assert t["esc sem nada"]["tratou"] is False and {k: v for k, v in t["esc sem nada"]["estado"].items() if k not in ("jogo", "aba")} == livre
    tudo = saida["comTudo"]
    assert (tudo["fase"], tudo["rod"], tudo["res"], tudo["clube"]) == ("m", 9, saida["quartas"]["res"], saida["quartas"]["clube"])
    ordem = ["esc solta o resultado primeiro", "esc solta o clube", "esc solta a rodada", "esc solta a fase"]
    esperado = [{**tudo, "res": None}, {**tudo, "res": None, "clube": None}, {**tudo, "res": None, "clube": None, "rod": None}, {**tudo, "res": None, "clube": None, "rod": None, "fase": "t"}]
    for rot, alvo in zip(ordem, esperado):
        e = t[rot]["estado"]
        assert t[rot]["tratou"] is True and {k: e[k] for k in ("fase", "rod", "clube", "res")} == {k: alvo[k] for k in ("fase", "rod", "clube", "res")}, rot
        assert e["jogo"] in {j["n"] for j in lista_de(ref, e["fase"], e["rod"], e["clube"], e["res"])}
    assert t["esc de novo nao trata"]["tratou"] is False
    assert t["backspace solta o clube"]["antes"]["clube"] == no and t["backspace solta o clube"]["estado"]["clube"] is None and t["backspace solta o clube"]["tratou"] is True
    assert (t["abre com ?"]["tratou"], t["abre com ?"]["estado"]["ajuda"]) == (True, True) and t["seta com a ajuda aberta nao anda"]["tratou"] is False
    assert (t["esc fecha a ajuda"]["tratou"], t["esc fecha a ajuda"]["estado"]["ajuda"]) == (True, False)
    assert t["h abre"]["estado"]["ajuda"] is True and t["enter fecha"]["estado"]["ajuda"] is False
    assert t["h com ctrl nao abre"]["tratou"] is False and t["outra tecla"]["tratou"] is False
    assert t["esc com ajuda e filtro fecha so a ajuda"]["antes"]["ajuda"] is True and t["esc com ajuda e filtro fecha so a ajuda"]["estado"]["ajuda"] is False
    assert t["esc com ajuda e filtro fecha so a ajuda"]["estado"]["fase"] == t["esc com ajuda e filtro fecha so a ajuda"]["antes"]["fase"]
    fecha = t["esc com ajuda e resultado fecha so a ajuda"]
    assert fecha["antes"]["ajuda"] is True and fecha["antes"]["res"] == saida["resDoMata"] and fecha["estado"]["ajuda"] is False and fecha["estado"]["res"] == saida["resDoMata"] and fecha["estado"]["fase"] == "m"
    assert t["backspace com ajuda aberta nao solta"]["tratou"] is False and t["backspace com ajuda aberta nao solta"]["estado"]["ajuda"] is True
    assert t["espaco fecha a ajuda"]["tratou"] is True and t["espaco fecha a ajuda"]["estado"]["ajuda"] is False
    lim = saida["limitesDeJogos"]
    assert t["seta para baixo no ultimo jogo"]["tratou"] is False and t["seta para baixo no ultimo jogo"]["estado"]["jogo"] == lim["ultimo"] == 72
    assert t["seta para cima anda um"]["tratou"] is True and t["seta para cima anda um"]["estado"]["jogo"] == ref["jogos"][-2]["n"]
    assert t["seta para cima no primeiro jogo"]["tratou"] is False and t["seta para cima no primeiro jogo"]["estado"]["jogo"] == lim["primeiro"] == ref["jogos"][0]["n"]
    assert t["seta para baixo desce um"]["tratou"] is True and t["seta para baixo desce um"]["estado"]["jogo"] == ref["jogos"][1]["n"]
    c = t["seta com clube anda so na lista"]
    assert c["tratou"] is True and c["estado"]["jogo"] == c["lista"][c["lista"].index(c["antes"]["jogo"]) + 1]
    assert saida["teclaNoDocumento"] == {"escPrevenido": True, "clubeDepoisDoEsc": None, "escondidoPrevenido": False, "clubeEscondido": no}


@precisa_dados
@precisa_node
def test_toda_dica_abre_com_titulo_sem_texto_estragado_nem_nome_interno(saida):
    tips = saida["tips"]
    assert len(tips) > 3000 and saida["tipEscondeAoSair"] is True
    for t in tips:
        assert t["visivel"] is True and t["html"] == t["tipHtml"] and t["html"].startswith("<b>") and t["tip"].split("||")[0], t["rot"]
        assert not re.search(r"NaN|undefined|Infinity|\[object|null", t["tip"]), t["tip"][:80]
        for ruim in INTERNOS:
            assert ruim not in t["tip"], (ruim, t["tip"][:80])
    assert {t["rot"] for t in tips} >= {"p1", "p2", "p3", "p4", "p5", "p6", "controles", "rodape", "cabecalho"}


@precisa_dados
@precisa_node
def test_dica_escapa_html_e_monta_titulo_tabela_paragrafo_e_nota(saida):
    assert saida["tipHtml"]["completo"] == '<b>Título</b><div class="tv"><div><span>A</span><em>1</em></div><div><span>B</span><em>2</em></div></div><span>Parágrafo</span><small>Nota</small>'
    assert saida["tipHtml"]["escapado"] == "<b>&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;</b>"


@precisa_dados
@precisa_node
def test_sem_escudos_a_tela_cai_para_a_sigla_colorida(montagem):
    s = rodar(montagem, "semlogos")
    t = s["filtros"][0]
    assert not any(e["ruim"] for e in s["filtros"]) and not any(e["ruim"] for e in s["jogos"])
    assert t["paineis"][0].count("<img") == 0 and t["paineis"][0].count('class="sg"') == 16 + 72 * 2
    com = rodar(montagem)["filtros"][0]
    assert com["paineis"][0].count("<img") == 16 + 72 * 2 and com["paineis"][0].count('class="sg"') == 0
