import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
PROTO = RAIZ / "prototype"
precisa_dados = pytest.mark.skipif(not all((PROC / n).exists() for n in ("fato_classificacao_oficial.csv", "fato_partida.csv", "fato_evento.csv", "resultado_regra.csv", "ref_indicadores.csv")), reason="rode scripts/04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
INTERNOS = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")
FASE = {2: "Quartas de final", 3: "Semifinal", 4: "Final"}
CRIT = {"v": "vitórias", "sg": "saldo de gols", "gp": "gols marcados", "cv": "cartões vermelhos", "ca": "cartões amarelos"}
SENTIDO = {"v": 1, "sg": 1, "gp": 1, "cv": -1, "ca": -1}
ORDEM_ART16 = ["v", "sg", "gp", "cv", "ca"]


def carregar(nome, arq):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sem_tags(t):
    return re.sub(r"<[^>]*>", "", t)


def decod(t):
    return t.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def sinal(n):
    return "+" + str(n) if n > 0 else "−" + str(-n) if n < 0 else "0"


def pc(a, b):
    return f"{100 * a / b:.1f}".replace(".", ",") + "%"


def lista(a):
    return a[0] if len(a) == 1 else ", ".join(a[:-1]) + " e " + a[-1]


def plural(n, u, p):
    return f"{n} " + (u if n == 1 else p)


def data_br(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}"


def data_longa(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}/{a}"


# ---------- referência recalculada aqui, direto das tabelas tratadas ----------

@pytest.fixture(scope="module")
def ref():
    fases = {f["id_fase"]: f["nome_fase"] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = ler_csv(PROC / "fato_partida.csv")
    for p in partidas:
        p["fase"] = fases[p["id_fase"]]
    return {
        "partidas": partidas,
        "fase1": [p for p in partidas if p["fase"] == "PRIMEIRA FASE"],
        "mata": [p for p in partidas if p["fase"] != "PRIMEIRA FASE"],
        "eventos": ler_csv(PROC / "fato_evento.csv"),
        "oficial": ler_csv(PROC / "fato_classificacao_oficial.csv"),
        "clubes": {c["id_clube"]: c for c in ler_csv(PROC / "dim_clube.csv")},
        "estadios": {e["id_estadio"]: e["nome_fpf"] for e in ler_csv(PROC / "dim_estadio.csv")},
        "regras": {r["codigo"]: r for r in ler_csv(PROC / "resultado_regra.csv")},
    }


def tabela_ate(ref, rodada):
    jogos = [p for p in ref["fase1"] if int(p["rodada"]) <= rodada]
    ids = {p["id_partida"] for p in jogos}
    t = {}
    for p in jogos:
        gm, gv = int(p["gols_mandante"]), int(p["gols_visitante"])
        for c, gf, gc in ((p["id_clube_mandante"], gm, gv), (p["id_clube_visitante"], gv, gm)):
            l = t.setdefault(c, dict(pt=0, j=0, v=0, e=0, d=0, gp=0, gc=0, ca=0, cv=0))
            l["j"] += 1
            l["gp"] += gf
            l["gc"] += gc
            l["pt"] += 3 if gf > gc else 1 if gf == gc else 0
            l["v"] += gf > gc
            l["e"] += gf == gc
            l["d"] += gf < gc
    for e in ref["eventos"]:
        if e["id_partida"] in ids:
            l = t[e["id_clube"]]
            if e["tipo_evento"] == "amarelo":
                l["ca"] += 1
            elif e["tipo_evento"] == "segundo_amarelo":
                l["ca"] -= 1
                l["cv"] += 1
            elif e["tipo_evento"] == "vermelho":
                l["cv"] += 1
    for l in t.values():
        l["sg"] = l["gp"] - l["gc"]
    return t


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)).lower()


def ordenar(t, nomes=None, grupos=None):
    """Ordem pelo Art. 16. Com `nomes`, clubes iguais em todos os critérios ficam em ordem alfabética e os grupos vão para `grupos`; sem `nomes`, empate total é erro."""
    chave = lambda c: (-t[c]["pt"], -t[c]["v"], -t[c]["sg"], -t[c]["gp"], t[c]["cv"], t[c]["ca"])
    if nomes is None:
        assert len({chave(c) for c in t}) == len(t), "empate em todos os critérios"
        return sorted(t, key=chave)
    ordem = sorted(t, key=lambda c: (chave(c), sem_acento(nomes[c])))
    if grupos is not None:
        por_chave = defaultdict(list)
        for c in ordem:
            por_chave[chave(c)].append(int(c))
        grupos.extend(g for g in por_chave.values() if len(g) > 1)
    return ordem


def vencedor(jogos):
    pts = Counter()
    for j in jogos:
        gm, gv = int(j["gols_mandante"]), int(j["gols_visitante"])
        pts[j["id_clube_mandante"]] += 3 if gm > gv else 1 if gm == gv else 0
        pts[j["id_clube_visitante"]] += 3 if gv > gm else 1 if gm == gv else 0
    (a, pa), (b, pb) = pts.most_common(2)
    if pa != pb:
        return a, b, pts
    u = jogos[-1]
    pm, pv = int(u["penaltis_mandante"]), int(u["penaltis_visitante"])
    return (u["id_clube_mandante"], u["id_clube_visitante"], pts) if pm > pv else (u["id_clube_visitante"], u["id_clube_mandante"], pts)


@pytest.fixture(scope="module")
def montagem(tmp_path_factory):
    m = carregar("montar_app13_clas", "13_montar_app.py")
    versus = m.modulo_versus().montar_dados()
    clas = m.montar_dados_clas(versus)
    frag = (PROTO / "classificacao" / "fragmento.html").read_text(encoding="utf-8").replace("__DADOS__", m.dados_json(clas))
    pasta = tmp_path_factory.mktemp("clas")
    (pasta / "clas.html").write_text(m.pagina("t", m.logos_js(versus) + frag), encoding="utf-8")
    return {"m": m, "versus": versus, "clas": clas, "frag": frag, "pasta": pasta}


@pytest.fixture(scope="module")
def curto(montagem):
    return {int(c["id"]): c["curto"] for c in montagem["clas"]["clubes"]}


def rodar(montagem, *extra):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_clas.js"), str(montagem["pasta"] / "clas.html"), *extra], capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr[-1500:]
    s = json.loads(proc.stdout)
    assert not s.get("semGancho")
    return s


@pytest.fixture(scope="module")
def saida(montagem):
    return rodar(montagem)


# ---------- pacote de dados ----------

@precisa_dados
def test_tabela_do_pacote_e_a_classificacao_oficial_da_primeira_fase(montagem, ref):
    oficial = sorted((o for o in ref["oficial"] if o["fase"] == "PRIMEIRA FASE"), key=lambda o: int(o["posicao"]))
    tab = montagem["clas"]["tab"]
    assert len(tab) == len(oficial) == 16
    for t, o in zip(tab, oficial):
        assert t == {"c": int(o["id_clube"]), "p": int(o["posicao"]), "pt": int(o["pontos"]), "j": int(o["jogos"]), "v": int(o["vitorias"]), "e": int(o["empates"]), "d": int(o["derrotas"]),
                     "gp": int(o["gols_pro"]), "gc": int(o["gols_contra"]), "sg": int(o["saldo"]), "ca": int(o["amarelos"]), "cv": int(o["vermelhos"])}
    assert [t["p"] for t in tab] == list(range(1, 17))
    assert all(t["pt"] == 3 * t["v"] + t["e"] and t["j"] == t["v"] + t["e"] + t["d"] == 8 and t["sg"] == t["gp"] - t["gc"] for t in tab)
    assert sum(t["gp"] for t in tab) == sum(t["gc"] for t in tab) == sum(int(p["gols_mandante"]) + int(p["gols_visitante"]) for p in ref["fase1"])


@precisa_dados
def test_clubes_do_pacote_sao_os_16_da_tabela_com_sigla_da_fpf(montagem, ref):
    clubes = montagem["clas"]["clubes"]
    assert {int(c["id"]) for c in clubes} == {t["c"] for t in montagem["clas"]["tab"]} and len(clubes) == 16
    for c in clubes:
        assert c["sigla"] == ref["clubes"][str(c["id"])]["sigla"] and c["curto"] and re.fullmatch(r"#?[0-9A-Fa-f]{6}", c["cor"])


@precisa_dados
def test_a_ordem_da_tabela_e_a_do_art_16_recalculada_aqui_a_partir_dos_jogos_e_cartoes(montagem, ref):
    calc = tabela_ate(ref, 8)
    ordem = ordenar(calc)
    assert ordem == [str(t["c"]) for t in montagem["clas"]["tab"]]
    for t in montagem["clas"]["tab"]:
        l = calc[str(t["c"])]
        assert {k: l[k] for k in ("pt", "j", "v", "e", "d", "gp", "gc", "sg", "ca", "cv")} == {k: t[k] for k in ("pt", "j", "v", "e", "d", "gp", "gc", "sg", "ca", "cv")}


@precisa_dados
def test_posicao_e_pontos_depois_de_cada_rodada_recalculados_do_zero(montagem, ref):
    d = montagem["clas"]
    assert d["meta"]["rod"] == 8 and sorted({int(p["rodada"]) for p in ref["fase1"]}) == list(range(1, 9))
    nomes = {c: ref["clubes"][c]["nome_popular"] for c in ref["clubes"]}
    esperado_pos, esperado_pts, esperado_emp = defaultdict(list), defaultdict(list), []
    for r in range(1, 9):
        calc = tabela_ate(ref, r)
        grupos = []
        for pos, c in enumerate(ordenar(calc, nomes, grupos), 1):
            esperado_pos[c].append(pos)
            esperado_pts[c].append(calc[c]["pt"])
        esperado_emp.append(grupos)
    assert {k: v for k, v in d["rod"].items()} == dict(esperado_pos)
    assert {k: v for k, v in d["rpt"].items()} == dict(esperado_pts)
    assert d["rt"] == esperado_emp and d["rt"][-1] == [] and sum(len(g) for g in d["rt"]) >= 1
    for r in range(8):
        assert sorted(v[r] for v in d["rod"].values()) == list(range(1, 17))
    assert any(len(set(v)) > 1 for v in d["rod"].values())


def criterio_que_separou(a, b):
    iguais = []
    for c in ORDEM_ART16:
        if a[c] != b[c]:
            assert (a[c] - b[c]) * SENTIDO[c] > 0, "a ordem da tabela contraria o critério"
            return c, iguais
        iguais.append(c)
    raise AssertionError("empate em todos os critérios")


@precisa_dados
def test_desempates_do_pacote_listam_cada_grupo_de_pontos_iguais_e_o_criterio_de_cada_par(montagem):
    d = montagem["clas"]
    tab = d["tab"]
    grupos = Counter(t["pt"] for t in tab)
    esperados = sorted((pt for pt, n in grupos.items() if n > 1), reverse=True)
    assert [g["p"] for g in d["emp"]] == esperados and len(esperados) > 0
    for g in d["emp"]:
        membros = [t for t in tab if t["pt"] == g["p"]]
        assert g["ids"] == [t["c"] for t in membros] and len(g["pares"]) == len(membros) - 1
        for i, par in enumerate(g["pares"]):
            a, b = membros[i], membros[i + 1]
            crit, iguais = criterio_que_separou(a, b)
            assert par == {"a": a["c"], "b": b["c"], "c": crit, "va": a[crit], "vb": b[crit], "iguais": iguais}


@precisa_dados
def test_mata_mata_do_pacote_bate_com_os_oito_jogos_e_com_o_regulamento(montagem, ref):
    d = montagem["clas"]
    mm = d["mm"]
    assert len(mm) == 8 and len(ref["mata"]) == 8 and [j["f"] for j in mm] == [2, 2, 2, 2, 3, 3, 4, 4]
    assert [j["d"] + j["h"] for j in mm] == sorted(j["d"] + j["h"] for j in mm)
    por_jogo = {int(p["numero_jogo"]): p for p in ref["mata"]}
    assert {j["n"] for j in mm} == set(por_jogo)
    cod = {"QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}
    for j in mm:
        p = por_jogo[j["n"]]
        assert (j["f"], j["r"], j["d"], j["h"], j["m"], j["v"], j["gm"], j["gv"], j["e"]) == (cod[p["fase"]], int(p["rodada"]), p["data_jogo"], p["hora_programada"], int(p["id_clube_mandante"]), int(p["id_clube_visitante"]), int(p["gols_mandante"]), int(p["gols_visitante"]), ref["estadios"][p["id_estadio"]])
        pen = (int(p["penaltis_mandante"]), int(p["penaltis_visitante"])) if p["penaltis_mandante"] else (None, None)
        assert (j["pm"], j["pv"]) == pen
    confrontos = defaultdict(list)
    for p in sorted(ref["mata"], key=lambda p: (p["data_hora_programada"], int(p["numero_jogo"]))):
        confrontos[frozenset((p["id_clube_mandante"], p["id_clube_visitante"]))].append(p)
    assert sorted(len(v) for v in confrontos.values()) == [1, 1, 1, 1, 1, 1, 2]
    ganhou = {}
    for par, jogos in confrontos.items():
        g, perdeu, pts = vencedor(jogos)
        ganhou[par] = int(g)
        if len(jogos) == 2:
            final = (int(g), int(perdeu), pts)
    for j in mm:
        assert j["w"] == ganhou[frozenset((str(j["m"]), str(j["v"])))]
    assert d["meta"]["camp"] == final[0] and d["meta"]["vice"] == final[1] and d["meta"]["fpts"] == [final[2][str(final[0])], final[2][str(final[1])]]
    oficial_final = {int(o["posicao"]): int(o["id_clube"]) for o in ref["oficial"] if o["fase"] == "FINAL"}
    assert (d["meta"]["camp"], d["meta"]["vice"]) == (oficial_final[1], oficial_final[2])


@precisa_dados
def test_chaveamento_confere_1x8_2x7_3x6_4x5_e_cada_fase_so_tem_quem_venceu_a_anterior(montagem):
    d = montagem["clas"]
    topo = {t["p"]: t["c"] for t in d["tab"]}
    quartas = [j for j in d["mm"] if j["f"] == 2]
    assert {frozenset((j["m"], j["v"])) for j in quartas} == {frozenset((topo[1], topo[8])), frozenset((topo[2], topo[7])), frozenset((topo[3], topo[6])), frozenset((topo[4], topo[5]))}
    semis = [j for j in d["mm"] if j["f"] == 3]
    assert {c for j in semis for c in (j["m"], j["v"])} == {j["w"] for j in quartas}
    final = [j for j in d["mm"] if j["f"] == 4]
    assert {c for j in final for c in (j["m"], j["v"])} == {j["w"] for j in semis} == {d["meta"]["camp"], d["meta"]["vice"]}
    assert final[0]["m"] == final[1]["v"] and final[0]["v"] == final[1]["m"]


@precisa_dados
def test_meta_traz_regulamento_data_da_fpf_e_a_conferencia_da_regra_a19(montagem, ref):
    meta = montagem["clas"]["meta"]
    assert (meta["nq"], meta["nr"], meta["rod"]) == (8, 2, 8)
    assert meta["fpf"] == ref["oficial"][0]["atualizado_em"][:10] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["fpf"])
    a19 = ref["regras"]["A19"]
    assert a19["resultado"] == "ok" and meta["conf"] == [int(a19["verificados"]) - int(a19["ocorrencias"]), int(a19["verificados"])] == [16, 16]


@precisa_dados
def test_texto_nenhum_do_pacote_cita_arquivo_tabela_ou_pasta_internos(montagem):
    textos = [c[k] for c in montagem["clas"]["clubes"] for k in ("nome", "curto", "sigla")] + [j["e"] for j in montagem["clas"]["mm"]]
    for texto in textos:
        for ruim in INTERNOS:
            assert ruim not in texto, (ruim, texto)


def linha(id_, pontos, vitorias=0, saldo=0, gols_pro=0, vermelhos=0, amarelos=0):
    return {"id_clube": str(id_), "pontos": pontos, "vitorias": vitorias, "saldo": saldo, "gols_pro": gols_pro, "vermelhos": vermelhos, "amarelos": amarelos, "posicao": 0}


def test_empate_total_em_rodada_do_meio_fica_em_ordem_alfabetica_sem_olhar_acento_e_renumera_as_posicoes():
    m = carregar("montar_app13_ord", "13_montar_app.py")
    nomes = {1: "Santos", 2: "Água Santa", 3: "Bragantino", 4: "Zebra", 5: "Mirassol", 6: "São Paulo"}
    tabela = [linha(4, 9, 3, 5, 6), linha(1, 6, 2, 1, 3), linha(6, 6, 2, 1, 3), linha(2, 6, 2, 1, 3), linha(3, 4, 1, 0, 2, 0, 1), linha(5, 4, 1, 0, 2, 0, 2)]
    saida, grupos = m.ordem_da_rodada(tabela, nomes)
    assert [l["id_clube"] for l in saida] == ["4", "2", "1", "6", "3", "5"] and [l["posicao"] for l in saida] == [1, 2, 3, 4, 5, 6]
    assert grupos == [[2, 1, 6]]
    sem_empate, nenhum = m.ordem_da_rodada([linha(2, 3, 1, 1, 1), linha(1, 1, 0, 0, 1)], {1: "A", 2: "B"})
    assert [l["id_clube"] for l in sem_empate] == ["2", "1"] and nenhum == []


def test_desempates_explica_cada_par_pelo_primeiro_criterio_que_os_separa_e_para_se_so_o_sorteio_decidiria():
    m = carregar("montar_app13_des", "13_montar_app.py")
    base = {"pt": 10, "v": 3, "sg": 2, "gp": 5, "cv": 0, "ca": 4}
    tab = [{"c": 1, "p": 1, **base}, {"c": 2, "p": 2, **{**base, "v": 2}}, {"c": 3, "p": 3, **{**base, "v": 2, "sg": 1}}, {"c": 4, "p": 4, **{**base, "v": 2, "sg": 1, "gp": 4}}, {"c": 5, "p": 5, **{**base, "v": 2, "sg": 1, "gp": 4, "cv": 1}},
           {"c": 6, "p": 6, **{**base, "v": 2, "sg": 1, "gp": 4, "cv": 1, "ca": 5}}, {"c": 7, "p": 7, **{**base, "pt": 4}}]
    g = m.desempates(tab)
    assert len(g) == 1 and g[0]["p"] == 10 and g[0]["ids"] == [1, 2, 3, 4, 5, 6]
    assert [(p["a"], p["b"], p["c"], p["va"], p["vb"], p["iguais"]) for p in g[0]["pares"]] == [(1, 2, "v", 3, 2, []), (2, 3, "sg", 2, 1, ["v"]), (3, 4, "gp", 5, 4, ["v", "sg"]), (4, 5, "cv", 0, 1, ["v", "sg", "gp"]), (5, 6, "ca", 4, 5, ["v", "sg", "gp", "cv"])]
    iguais = [{"c": 1, "p": 1, **base}, {"c": 2, "p": 2, **base}]
    with pytest.raises(SystemExit, match="sorteio"):
        m.desempates(iguais)


# ---------- o montador para se os dados não fecharem ----------

def adulterar(monkeypatch, m, arquivo, mexer):
    original = m.ler_csv

    def leitor(caminho, *a, **k):
        linhas = original(caminho, *a, **k)
        if Path(caminho).name == arquivo:
            mexer(linhas)
        return linhas

    monkeypatch.setattr(m, "ler_csv", leitor)


@precisa_dados
def test_o_montador_para_se_a_tabela_oficial_deixar_de_bater_com_o_calculo_pelo_art_16(montagem, monkeypatch):
    m = montagem["m"]

    def trocar_gols(linhas):
        l = next(x for x in linhas if x["fase"] == "PRIMEIRA FASE" and x["posicao"] == "5")
        l["gols_pro"] = str(int(l["gols_pro"]) + 1)
        l["saldo"] = str(int(l["saldo"]) + 1)

    adulterar(monkeypatch, m, "fato_classificacao_oficial.csv", trocar_gols)
    with pytest.raises(SystemExit, match="não bate com a tabela oficial"):
        m.montar_dados_clas(montagem["versus"])


@precisa_dados
def test_o_montador_para_se_a_ordem_oficial_trocar_dois_clubes(montagem, monkeypatch):
    m = montagem["m"]

    def trocar_posicoes(linhas):
        a, b = (next(x for x in linhas if x["fase"] == "PRIMEIRA FASE" and x["posicao"] == p) for p in ("3", "4"))
        a["posicao"], b["posicao"] = "4", "3"

    adulterar(monkeypatch, m, "fato_classificacao_oficial.csv", trocar_posicoes)
    with pytest.raises(SystemExit):
        m.montar_dados_clas(montagem["versus"])


@precisa_dados
def test_o_montador_para_se_o_campeao_oficial_for_outro(montagem, monkeypatch):
    m = montagem["m"]

    def trocar_final(linhas):
        a, b = (next(x for x in linhas if x["fase"] == "FINAL" and x["posicao"] == p) for p in ("1", "2"))
        a["posicao"], b["posicao"] = "2", "1"

    adulterar(monkeypatch, m, "fato_classificacao_oficial.csv", trocar_final)
    with pytest.raises(SystemExit, match="vencedor|campeão"):
        m.montar_dados_clas(montagem["versus"])


@precisa_dados
def test_o_montador_para_se_a_regra_a19_deixar_de_dar_16_de_16(montagem, monkeypatch):
    m = montagem["m"]

    def estragar(linhas):
        l = next(x for x in linhas if x["codigo"] == "A19")
        l["resultado"], l["ocorrencias"] = "aberta", "1"

    adulterar(monkeypatch, m, "resultado_regra.csv", estragar)
    with pytest.raises(SystemExit, match="A19"):
        m.montar_dados_clas(montagem["versus"])


@precisa_dados
def test_o_montador_para_se_um_jogo_do_mata_mata_sumir(montagem, monkeypatch):
    m = montagem["m"]

    def tirar_jogo(linhas):
        i = next(k for k, x in enumerate(linhas) if "id_fase" in x and x["numero_jogo"] == "70")
        del linhas[i]

    adulterar(monkeypatch, m, "fato_partida.csv", tirar_jogo)
    with pytest.raises(SystemExit):
        m.montar_dados_clas(montagem["versus"])


# ---------- montagem da tela ----------

@precisa_dados
def test_fragmento_nao_deixa_marca_sobrando_e_so_age_quando_visivel(montagem):
    frag = montagem["frag"]
    assert not re.search(r"__[A-Z_]+__", frag)
    src = (PROTO / "classificacao" / "fragmento.html").read_text(encoding="utf-8")
    assert src.count("__DADOS__") == 1 and "height:100%;min-height:320px" in src and "if(!raiz.offsetParent)return;" in src
    assert "window.PA.mods.clas={entrar:entrar}" in src and 'id="clx"' in src
    for ruim in INTERNOS:
        assert ruim not in src, ruim
    assert "http://" not in src and "https://" not in src and "@import" not in src and "<link" not in src


@precisa_dados
def test_desenhos_por_cima_de_botoes_nao_capturam_cliques_nem_dicas():
    src = (PROTO / "classificacao" / "fragmento.html").read_text(encoding="utf-8")
    ligacoes = re.search(r"#clx \.br svg\{([^}]*)\}", src).group(1)
    assert "position:absolute" in ligacoes and "pointer-events:none" in ligacoes
    assert re.search(r"#clx \.tip\{[^}]*pointer-events:none", src)
    hit = re.search(r"#clx \.bp \.hit\{([^}]*)\}", src).group(1)
    assert "pointer-events:stroke" in hit and "stroke-linecap:round" in hit, "a faixa de clique do gráfico precisa cobrir também as pontas da linha"
    assert re.search(r"#clx \.bp \.ln,#clx \.bp \.pt\{pointer-events:none\}", src), "linha e bolinhas do gráfico não podem roubar o clique da faixa de clique"


@precisa_dados
def test_textos_da_tela_sao_todos_de_pelo_menos_16_pixels():
    src = (PROTO / "classificacao" / "fragmento.html").read_text(encoding="utf-8")
    tamanhos = [int(x) for x in re.findall(r"font-size:(\d+)px", src)] + [int(x) for x in re.findall(r"font:[^;{}]*?(\d+)px", src)]
    assert tamanhos and min(tamanhos) >= 16, sorted(set(tamanhos))


@precisa_dados
def test_pagina_do_app_leva_o_modulo_os_dados_e_o_botao_da_tela():
    m = carregar("montar_app13_clpg", "13_montar_app.py")
    dados = m.montar_todos_os_dados()
    frag = m.montar_fragmentos(dados)
    app = frag["app"]
    assert not re.search(r"__[A-Z_]+__", app)
    assert app.count('id="clx"') == 1 and app.count('<section class="mod" id="mod-clas">') == 1 and m.dados_json(dados["clas"]) in app and frag["clas"] in app
    assert '<button data-mod="clas"><span>Classificação</span></button>' in app
    nav = re.search(r"<nav[^>]*>(.*?)</nav>", app, re.S).group(1)
    assert re.findall(r'data-mod="(\w+)"', nav) == [t[0] for t in m.TELAS]


# ---------- comportamento (módulo simulado em Node) ----------

def kpis_da(h):
    achados = re.findall(r'<div class="kpi" style="left:(\d+)px;--kc:(#[0-9a-f]{6})" data-tip="([^"]*)"><h4>([^<]*)</h4><div class="v( tx)?">(.*?)</div><small>([^<]*)</small></div>', h)
    return [{"x": int(x), "cor": cor, "tip": decod(tip), "r": decod(r), "tx": bool(tx), "v": decod(sem_tags(v)), "s": decod(s)} for x, cor, tip, r, tx, v, s in achados]


def linhas_da_tabela(h):
    padrao = re.compile(r'<button class="tr z(q|r)?( sel| sem)?" style="--i:(\d+)" data-act="clube" data-id="(\d+)" data-tip="([^"]*)"><span class="ps">(\d+)</span><span class="cb">(.*?)<u>([^<]*)</u></span><b>(\d+)</b>((?:<i[^>]*>[^<]*</i>){10})</button>', re.S)
    saida = []
    for zona, sel, i, id_, tip, ps, logo, nome, pt, resto in padrao.findall(h):
        celulas = re.findall(r'<i( class="[^"]*")?>([^<]*)</i>', resto)
        saida.append({"zona": zona, "sel": sel.strip(), "i": int(i), "id": int(id_), "tip": decod(tip), "pos": int(ps), "logo": logo, "nome": decod(nome), "pt": int(pt), "cel": [c[1] for c in celulas], "cls": [c[0] for c in celulas]})
    return saida


def jogos_do_chaveamento(h):
    padrao = re.compile(r'<div class="gm( sel| sem)?" style="left:(\d+)px;top:([\d.]+)px;--i:(\d+)" data-tip="([^"]*)"><em>([^<]*)</em>'
                        r'<button class="tl( w)?( sel)?" data-act="clube" data-id="(\d+)">.*?<u>([^<]*)</u><b>(\d+)(?: <small>\((\d+)\)</small>)?</b></button>'
                        r'<button class="tl( w)?( sel)?" data-act="clube" data-id="(\d+)">.*?<u>([^<]*)</u><b>(\d+)(?: <small>\((\d+)\)</small>)?</b></button></div>', re.S)
    saida = []
    for g in padrao.findall(h):
        saida.append({"cls": g[0].strip(), "x": int(g[1]), "y": float(g[2]), "i": int(g[3]), "tip": decod(g[4]), "em": decod(g[5]),
                      "a": {"w": bool(g[6]), "sel": bool(g[7]), "id": int(g[8]), "nome": decod(g[9]), "g": int(g[10]), "pen": int(g[11]) if g[11] else None},
                      "b": {"w": bool(g[12]), "sel": bool(g[13]), "id": int(g[14]), "nome": decod(g[15]), "g": int(g[16]), "pen": int(g[17]) if g[17] else None}})
    return saida


def grafico_da(h):
    padrao = re.compile(r'<polyline class="ln([^"]*)" points="([^"]*)"/>((?:<circle class="pt[^"]*" cx="[^"]*" cy="[^"]*" r="[^"]*"/>)+)'
                        r'<polyline class="hit" points="([^"]*)" data-act="clube" data-id="(\d+)" data-tip="([^"]*)"/>'
                        r'<g class="fim([^"]*)" data-act="clube" data-id="(\d+)" data-tip="([^"]*)">(.*?)</g>', re.S)
    saida = []
    for ln, pts, circulos, hit, id_hit, tip_hit, fim, id_fim, tip_fim, corpo in padrao.findall(h):
        saida.append({"cls": ln.strip(), "pts": [tuple(float(v) for v in p.split(",")) for p in pts.split()], "hit": [tuple(float(v) for v in p.split(",")) for p in hit.split()], "id": int(id_hit), "id_fim": int(id_fim),
                      "circ": [(float(a), float(b), float(c)) for a, b, c in re.findall(r'cx="([^"]*)" cy="([^"]*)" r="([^"]*)"', circulos)], "classes_circ": re.findall(r'<circle class="pt([^"]*)"', circulos),
                      "fim": fim.strip(), "sigla": decod(re.search(r"<text[^>]*>([^<]*)</text>", corpo).group(1)), "tip": decod(tip_hit), "tip_fim": decod(tip_fim)})
    return saida


def classe_esperada(sel, id_):
    return "" if sel is None else "sel" if sel == id_ else "sem"


@precisa_dados
@precisa_node
def test_o_codigo_roda_no_node_sem_texto_estragado(saida):
    assert len(saida["estados"]) == 17 and saida["ids"] and len(saida["ids"]) == 16
    assert not any(e["ruim"] for e in saida["estados"]) and not saida["rodape"]["ruim"]


@precisa_dados
@precisa_node
def test_sete_quadros_com_os_numeros_da_tabela(saida, montagem, curto):
    d = montagem["clas"]
    tab = d["tab"]
    por_pos = {t["p"]: t for t in tab}
    esperados = {
        "Campeão": (curto[d["meta"]["camp"]], f"final: {d['meta']['fpts'][0]} a {d['meta']['fpts'][1]} em pontos"),
        "Vice-campeão": (curto[d["meta"]["vice"]], f"{next(t['p'] for t in tab if t['c'] == d['meta']['vice'])}º na 1ª fase"),
        "Melhor ataque": (lista([curto[t["c"]] for t in tab if t["gp"] == max(x["gp"] for x in tab)]), f"{max(x['gp'] for x in tab)} gols na 1ª fase"),
        "Melhor defesa": (lista([curto[t["c"]] for t in tab if t["gc"] == min(x["gc"] for x in tab)]), f"{min(x['gc'] for x in tab)} gols sofridos na 1ª fase"),
        "Empates em pontos": (str(len(d["emp"])), plural(sum(len(g["ids"]) for g in d["emp"]), "clube", "clubes") + " desempatados"),
        "Vão às quartas": ("8", "do 1º ao 8º lugar"),
        "Rebaixados": ("2", lista([curto[por_pos[p]["c"]] for p in (15, 16)])),
    }
    for e in saida["estados"]:
        k = kpis_da(e["kpis"])
        assert [x["r"] for x in k] == list(esperados) and [x["x"] for x in k] == [46 + i * 263 for i in range(7)]
        assert [(x["v"], x["s"]) for x in k] == list(esperados.values())
        assert all(x["tip"] and x["x"] + 250 <= 1874 for x in k)
    assert [x["tx"] for x in kpis_da(saida["estados"][0]["kpis"])] == [True, True, True, True, False, False, False]


@precisa_dados
@precisa_node
def test_dicas_de_rebaixados_e_de_empates_em_pontos_usam_ponto_no_singular(saida, montagem, curto):
    d = montagem["clas"]
    por_pos = {t["p"]: t for t in d["tab"]}
    k = {x["r"]: x for x in kpis_da(saida["estados"][0]["kpis"])}
    reb = k["Rebaixados"]["tip"].split("||")[2]
    assert reb == "@" + "\n".join(f"{p}º::{curto[por_pos[p]['c']]} · {plural(por_pos[p]['pt'], 'ponto', 'pontos')}" for p in (15, 16))
    assert any(por_pos[p]["pt"] == 1 for p in (15, 16)) and "1 ponto" in reb and "1 pontos" not in reb
    emp = k["Empates em pontos"]["tip"].split("||")[2]
    assert emp == "@" + "\n".join(f"{plural(len(g['ids']), 'clube', 'clubes')} com {plural(g['p'], 'ponto', 'pontos')}::{', '.join(curto[i] for i in g['ids'])}" for g in d["emp"])


@precisa_dados
@precisa_node
def test_tabela_mostra_16_linhas_na_ordem_oficial_com_as_celulas_certas(saida, montagem, curto):
    tab = montagem["clas"]["tab"]
    for e in saida["estados"]:
        linhas = linhas_da_tabela(e["p1"])
        assert [l["id"] for l in linhas] == [t["c"] for t in tab] and [l["i"] for l in linhas] == list(range(16))
        for l, t in zip(linhas, tab):
            assert l["pos"] == t["p"] and l["nome"] == curto[t["c"]] and l["pt"] == t["pt"]
            assert l["cel"] == [str(t["j"]), str(t["v"]), str(t["e"]), str(t["d"]), str(t["gp"]), str(t["gc"]), sinal(t["sg"]), pc(t["pt"], 3 * t["j"]), str(t["ca"]), str(t["cv"])]
            assert l["cls"][6].strip() == ('class="pos"' if t["sg"] > 0 else 'class="neg"' if t["sg"] < 0 else 'class="mut"')
            assert l["zona"] == ("q" if t["p"] <= 8 else "r" if t["p"] >= 15 else "")
            assert l["sel"] == classe_esperada(e["sel"], t["c"])
            assert "<img" in l["logo"] or 'class="sg"' in l["logo"]
    assert "Classificados às quartas (1º ao 8º)" in saida["estados"][0]["p1"] and "Rebaixados à A2 de 2027 (15º e 16º)" in saida["estados"][0]["p1"] and "16 clubes · 8 jogos cada" in saida["estados"][0]["p1"]


@precisa_dados
@precisa_node
def test_chaveamento_mostra_os_oito_jogos_com_placar_penaltis_e_vencedor(saida, montagem, curto):
    d = montagem["clas"]
    mm = {j["n"]: j for j in d["mm"]}
    ordem = saida["ordemQuartas"]
    quartas = [j for j in d["mm"] if j["f"] == 2]
    assert sorted(ordem) == sorted(j["n"] for j in quartas)
    semis = sorted((j for j in d["mm"] if j["f"] == 3), key=lambda j: j["n"])
    for k, sj in enumerate(semis):
        assert {mm[n]["w"] for n in ordem[2 * k:2 * k + 2]} == {sj["m"], sj["v"]}
    for e in saida["estados"]:
        jogos = jogos_do_chaveamento(e["p2"])
        assert len(jogos) == 6 and [g["i"] for g in jogos] == list(range(6))
        esperados = [mm[n] for n in ordem] + semis
        for g, j in zip(jogos, esperados):
            assert (g["a"]["id"], g["b"]["id"]) == (j["m"], j["v"]) and (g["a"]["g"], g["b"]["g"]) == (j["gm"], j["gv"]) and (g["a"]["pen"], g["b"]["pen"]) == (j["pm"], j["pv"])
            assert (g["a"]["w"], g["b"]["w"]) == (j["w"] == j["m"], j["w"] == j["v"]) and g["a"]["w"] != g["b"]["w"]
            assert g["em"] == f"{FASE[j['f']]} · {data_br(j['d'])}" and (g["a"]["nome"], g["b"]["nome"]) == (curto[j["m"]], curto[j["v"]])
            envolve = e["sel"] in (j["m"], j["v"])
            assert g["cls"] == ("" if e["sel"] is None else "sel" if envolve else "sem")
            assert (g["a"]["sel"], g["b"]["sel"]) == (e["sel"] == j["m"], e["sel"] == j["v"])
        assert [g["x"] for g in jogos] == [0, 0, 0, 0, 280, 280] and [g["y"] for g in jogos[:4]] == [0, 86, 172, 258]
        assert jogos[4]["y"] == (jogos[0]["y"] + jogos[1]["y"]) / 2 and jogos[5]["y"] == (jogos[2]["y"] + jogos[3]["y"]) / 2


@precisa_dados
@precisa_node
def test_final_mostra_os_dois_jogos_os_pontos_e_o_campeao(saida, montagem, curto):
    d = montagem["clas"]
    final = sorted((j for j in d["mm"] if j["f"] == 4), key=lambda j: j["n"])
    camp, vice = d["meta"]["camp"], d["meta"]["vice"]
    sigla = {int(c["id"]): c["sigla"] for c in d["clubes"]}
    for e in saida["estados"]:
        h = e["p2"]
        assert h.count('class="lg"') == 2
        lances = re.findall(r'<div class="lg"><span>([^<]*)</span><b>([^<]*)</b></div>', h)
        assert lances == [(("Volta " if k else "Ida ") + data_br(j["d"]), f"{sigla[j['m']]} {j['gm']} × {j['gv']} {sigla[j['v']]}") for k, j in enumerate(final)]
        assert f'<div class="pt">Pontos: <b>{sigla[camp]} {d["meta"]["fpts"][0]}</b> × <b>{d["meta"]["fpts"][1]} {sigla[vice]}</b></div>' in h
        assert f"★ Campeão: {curto[camp]}</u></button>" in h and f"campeão: {curto[camp]}</small>" in h
        classe = re.search(r'<div class="fn( sel| sem)?"', h).group(1)
        assert (classe or "").strip() == ("" if e["sel"] is None else "sel" if e["sel"] in (camp, vice) else "sem")
        assert h.count('data-act="clube"') == 12 + 1
    assert any(j["pm"] is not None for j in d["mm"])


@precisa_dados
@precisa_node
def test_grafico_tem_16_linhas_8_pontos_cada_nas_posicoes_certas_e_o_selecionado_por_cima(saida, montagem, curto):
    d = montagem["clas"]
    x0, dx = 84, (700 - 84) / 7
    for e in saida["estados"]:
        g = grafico_da(e["p3"])
        assert len(g) == 16 and sorted(l["id"] for l in g) == sorted(t["c"] for t in d["tab"])
        if e["sel"] is not None:
            assert g[-1]["id"] == e["sel"] and [l["id"] for l in g[:-1]] == [t["c"] for t in d["tab"] if t["c"] != e["sel"]]
        else:
            assert [l["id"] for l in g] == [t["c"] for t in d["tab"]]
        for l in g:
            pos = d["rod"][str(l["id"])]
            assert l["id"] == l["id_fim"] and len(l["pts"]) == len(l["hit"]) == len(l["circ"]) == 8
            for r, (x, y) in enumerate(l["pts"]):
                assert abs(x - (x0 + r * dx)) < 0.06 and abs(y - (10 + (pos[r] - 1) * 15.8)) < 0.06
            assert l["pts"] == l["hit"]
            assert [(c[0], c[1]) for c in l["circ"]] == l["pts"]
            sel = e["sel"] == l["id"]
            assert all(c[2] == (5 if sel else 3.5) for c in l["circ"])
            esperada = classe_esperada(e["sel"], l["id"])
            assert l["cls"] == esperada and set(c.strip() for c in l["classes_circ"]) == {esperada}
            assert l["fim"] == ("sem" if esperada == "sem" else "")
            assert l["sigla"] == next(c["sigla"] for c in d["clubes"] if int(c["id"]) == l["id"])
    for p in range(1, 17):
        assert f">{p}º</text>" in saida["estados"][0]["p3"]
    assert all(f">R{r}</text>" in saida["estados"][0]["p3"] for r in range(1, 9)) and "R9" not in saida["estados"][0]["p3"]


@precisa_dados
@precisa_node
def test_com_clube_destacado_o_cabecalho_o_botao_limpar_e_o_resto_esmaecem(saida, curto):
    nenhum = saida["estados"][0]
    assert "lim off" in nenhum["ctl"] and "destacado" not in nenhum["sub"]
    for e in saida["estados"][1:]:
        assert "lim off" not in e["ctl"] and e["sub"] == f"{curto[e['sel']]} destacado na tabela, no chaveamento e no gráfico · Esc solta"
        assert e["p1"].count(" sel\"") == 1 and e["p1"].count(" sem\"") == 15
        assert e["p3"].count('class="ln sel"') == 1 and e["p3"].count('class="ln sem"') == 15
    assert nenhum["sub"] == "1ª fase em pontos corridos · os 8 primeiros vão às quartas · os 2 últimos caem para a A2 de 2027"
    assert nenhum["p1"].count(" sel\"") == 0 and nenhum["p1"].count(" sem\"") == 0


@precisa_dados
@precisa_node
def test_dica_de_cada_clube_conta_a_campanha_o_desempate_e_o_caminho_no_mata_mata(saida, montagem, curto):
    d = montagem["clas"]
    tab = {t["c"]: t for t in d["tab"]}
    mm = sorted(d["mm"], key=lambda j: j["n"])
    nenhum = saida["estados"][0]
    for l in linhas_da_tabela(nenhum["p1"]):
        t, tip = tab[l["id"]], l["tip"]
        secoes = tip.split("||")
        assert secoes[0] == f"{curto[t['c']]} · {t['p']}º lugar na 1ª fase"
        linhas = dict(x.split("::") for x in secoes[1][1:].split("\n"))
        assert linhas == {"Pontos": f"{t['pt']} em 8 jogos", "Vitórias, empates, derrotas": f"{t['v']} · {t['e']} · {t['d']}", "Gols pró e contra": f"{t['gp']} e {t['gc']} (saldo {sinal(t['sg'])})",
                          "Aproveitamento": pc(t["pt"], 24), "Cartões": f"amarelos {t['ca']} · vermelhos {t['cv']}"}
        sit = "Classificado às quartas de final." if t["p"] <= 8 else "Rebaixado à A2 de 2027." if t["p"] >= 15 else "Ficou fora do mata-mata e não caiu."
        assert secoes[2] == sit
        pares = [p for g in d["emp"] for p in g["pares"] if l["id"] in (p["a"], p["b"])]
        desempate = [s for s in secoes if s.startswith("Desempate: ")]
        assert len(desempate) == (1 if pares else 0)
        for p in pares:
            f = lambda c, v: sinal(v) if c == "sg" else str(v)
            ant = ""
            if p["iguais"]:
                ant = ", depois de empatar em " + lista([CRIT[c] for c in p["iguais"]]) + f" ({f(p['iguais'][0], tab[p['a']][p['iguais'][0]])} a {f(p['iguais'][0], tab[p['b']][p['iguais'][0]])})"
            frase = f"{curto[p['a']]} ficou à frente de {curto[p['b']]} no critério {CRIT[p['c']]} ({f(p['c'], p['va'])} a {f(p['c'], p['vb'])}){ant}"
            assert frase in desempate[0]
        jogos = [j for j in mm if l["id"] in (j["m"], j["v"]) and j["f"] < 4]
        caminho = [s for s in secoes if s.startswith("@") and "Quartas" in s or s.startswith("@") and "Semifinal" in s or s.startswith("@Final")]
        if jogos or t["c"] in (d["meta"]["camp"], d["meta"]["vice"]):
            esperado = []
            for j in jogos:
                adv = j["v"] if j["m"] == l["id"] else j["m"]
                placar = f"{j['gm']} × {j['gv']}" + (f" (pênaltis {j['pm']} a {j['pv']})" if j["pm"] is not None else "")
                esperado.append(f"{FASE[j['f']]}::{'passou' if j['w'] == l['id'] else 'caiu'} contra {curto[adv]} ({placar})")
            if t["c"] in (d["meta"]["camp"], d["meta"]["vice"]):
                camp = t["c"] == d["meta"]["camp"]
                a, b = d["meta"]["fpts"]
                esperado.append(f"Final::{'campeão' if camp else 'vice'}, {f'{a} a {b}' if camp else f'{b} a {a}'} em pontos contra {curto[d['meta']['vice'] if camp else d['meta']['camp']]}")
            assert caminho == ["@" + "\n".join(esperado)], (curto[t["c"]], caminho)
        else:
            assert caminho == []
        assert secoes[-1].startswith("~Clique para destacar este clube")


@precisa_dados
@precisa_node
def test_empate_total_numa_rodada_do_meio_aparece_na_dica_dos_clubes_e_no_cabecalho_do_grafico(saida, montagem, curto):
    d = montagem["clas"]
    grupos = [(r, g) for r, gs in enumerate(d["rt"]) for g in gs]
    assert grupos, "os dados reais têm ao menos um empate total (rodada 1)"
    h = saida["estados"][0]["p3"]
    assert "1ª fase · empate total em ordem alfabética</small>" in h
    for e in saida["estados"]:
        tips = {g["id"]: g["tip"] for g in grafico_da(e["p3"])}
        for c in d["tab"]:
            secoes = tips[c["c"]].split("||")
            linhas = dict(x.split("::") for x in secoes[1][1:].split("\n"))
            emp = {r: g for r, g in grupos if c["c"] in g}
            for r in range(8):
                esperado = f"{d['rod'][str(c['c'])][r]}º lugar · {plural(d['rpt'][str(c['c'])][r], 'ponto', 'pontos')}"
                if r in emp:
                    esperado += " · empate total com " + lista([curto[x] for x in emp[r] if x != c["c"]])
                assert linhas[f"Depois da rodada {r + 1}"] == esperado
            assert any(x.startswith("~Empate total") for x in secoes) == bool(emp)
            assert secoes[-1] == "~Clique para destacar este clube."
    r, g = grupos[0]
    nomes = [curto[x] for x in g]
    assert nomes == sorted(nomes, key=sem_acento) and [d["rod"][str(x)][r] for x in g] == list(range(d["rod"][str(g[0])][r], d["rod"][str(g[0])][r] + len(g)))


@precisa_dados
@precisa_node
def test_dica_do_jogo_traz_data_estadio_placar_penaltis_e_quem_passou(saida, montagem, curto):
    d = montagem["clas"]
    mm = {j["n"]: j for j in d["mm"]}
    jogos = jogos_do_chaveamento(saida["estados"][0]["p2"])
    ordem = saida["ordemQuartas"] + sorted(j["n"] for j in d["mm"] if j["f"] == 3)
    for g, n in zip(jogos, ordem):
        j = mm[n]
        secoes = g["tip"].split("||")
        assert secoes[0] == f"{FASE[j['f']]} · {curto[j['m']]} x {curto[j['v']]}"
        linhas = [x.split("::") for x in secoes[1][1:].split("\n")]
        esperado = [["Jogo", f"{n} · {data_longa(j['d'])} · {j['h']}"], ["Estádio", j["e"]], ["Placar", f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}"]]
        if j["pm"] is not None:
            esperado.append(["Pênaltis", f"{j['pm']} a {j['pv']}"])
        assert linhas == esperado
        assert secoes[2] == f"Passou: {curto[j['w']]}" + (" (nos pênaltis)." if j["pm"] is not None else ".")


@precisa_dados
@precisa_node
def test_rodape_e_ajuda_trazem_a_conferencia_e_o_passo_a_passo(saida, montagem):
    meta = montagem["clas"]["meta"]
    r = saida["rodape"]
    assert "conferida pelo Art. 16 em 16 de 16 clubes" in r["rod"] and "Projeto independente, sem vínculo com a FPF" in r["rod"]
    tip = decod(re.search(r'data-tip="([^"]*)"', r["rod"]).group(1))
    assert "Posições iguais à FPF::16 de 16" in tip and f"Classificação da FPF atualizada em::{data_longa(meta['fpf'])}" in tip
    assert "Como ler esta tela" in r["aj"] and r["aj"].count("<li>") == 4 and re.search(r'<button[^>]*data-act="ajuda-fechar"[^>]*data-tip="[^"]+"[^>]*>Entendi</button>', r["aj"])
    for palavra in ("P, J, V, E, D", "GP, GC e SG", "Aproveitamento", "CA e CV", "Desempate (Art. 16)"):
        assert palavra in r["aj"]
    assert "Como é o campeonato" in r["subTip"]


def modelo(sel, acao, id_):
    if acao == "clube":
        n = int(id_) if id_ not in (None, "") else None
        return sel if n is None or n not in IDS_VALIDOS else None if sel == n else n
    return None if acao == "limpar" else sel


IDS_VALIDOS = set()


@precisa_dados
@precisa_node
def test_cliques_nos_botoes_gerados_fazem_o_que_o_rotulo_diz(saida, montagem):
    ids = saida["ids"]
    IDS_VALIDOS.clear()
    IDS_VALIDOS.update(ids)
    assert set(saida["acoesVistas"]) == {"clube", "limpar", "ajuda", "ajuda-fechar"}
    assert len(saida["cliques"]) == 125
    por_ponto = defaultdict(set)
    for c in saida["cliques"]:
        a, d = c["antes"], c["depois"]
        assert c["tag"] or c["rot"] == "clique fora da ajuda", c["rot"]
        if c["act"] == "clube":
            assert d["sel"] == modelo(a["sel"], "clube", c["id"]) and d["ajuda"] == a["ajuda"] and int(c["id"]) in ids, c["rot"]
            por_ponto[c["tag"]].add(int(c["id"]))
        elif c["act"] == "limpar":
            assert d == {"sel": None, "ajuda": a["ajuda"]}
        elif c["act"] == "ajuda":
            assert d == {"sel": a["sel"], "ajuda": True}
        elif c["act"] == "ajuda-fechar":
            assert d == {"sel": a["sel"], "ajuda": False}
        else:
            assert c["rot"] == "clique fora da ajuda" and a["ajuda"] is True and d == {"sel": a["sel"], "ajuda": False}
    assert set(por_ponto) == {"button.tr", "polyline.hit", "g.fim", "button.tl", "button.cp"}
    assert por_ponto["button.tr"] == por_ponto["polyline.hit"] == por_ponto["g.fim"] == set(ids)
    assert por_ponto["button.tl"] == set(saida["noChaveamento"]) and len(saida["noChaveamento"]) == 8 and por_ponto["button.cp"] == {montagem["clas"]["meta"]["camp"]}
    for c in saida["cliques"]:
        if c["rot"].startswith(("linha da tabela de novo", "linha do grafico de novo", "rotulo do grafico de novo", "time no chaveamento de novo", "botao do campeao de novo")):
            assert c["antes"]["sel"] == int(c["id"]) and c["depois"]["sel"] is None, c["rot"]
        elif c["rot"].startswith(("linha da tabela ", "linha do grafico ", "rotulo do grafico ", "time no chaveamento ", "botao do campeao")):
            assert c["antes"]["sel"] is None and c["depois"]["sel"] == int(c["id"]), c["rot"]
    troca = next(c for c in saida["cliques"] if c["rot"].startswith("troca direto"))
    assert troca["antes"]["sel"] == ids[2] and troca["depois"]["sel"] == ids[5]
    assert next(c for c in saida["cliques"] if c["rot"] == "limpar")["depois"]["sel"] is None
    fora = next(c for c in saida["cliques"] if c["rot"] == "clique fora da ajuda")
    assert fora["antes"]["ajuda"] is True and fora["depois"]["ajuda"] is False
    dentro = next(c for c in saida["cliques"] if c["rot"] == "clique dentro da janela da ajuda")
    assert dentro["antes"] == {"sel": ids[0], "ajuda": True} and dentro["depois"] == {"sel": ids[0], "ajuda": False}


@precisa_dados
@precisa_node
def test_clube_inexistente_ou_sem_numero_nao_muda_o_estado(saida):
    assert saida["clubeInexistente"] == saida["clubeSemId"] == saida["clubeTextoInvalido"] == {"sel": None, "ajuda": False}


@precisa_dados
@precisa_node
def test_teclas_esc_e_backspace_soltam_o_clube_e_a_ajuda_fecha_primeiro(saida):
    t = {x["rot"]: x for x in saida["teclas"]}
    ids = saida["ids"]
    livre = {"sel": None, "ajuda": False}
    assert t["esc sem clube"]["tratou"] is False and t["esc sem clube"]["estado"] == livre
    assert t["esc solta"]["antes"] == {"sel": ids[3], "ajuda": False} and t["esc solta"]["tratou"] is True and t["esc solta"]["estado"] == livre
    assert t["backspace solta"]["tratou"] is True and t["backspace solta"]["estado"] == livre
    assert t["backspace sem clube"]["tratou"] is False
    assert (t["abre com ?"]["tratou"], t["abre com ?"]["estado"]["ajuda"]) == (True, True) and (t["esc fecha a ajuda"]["tratou"], t["esc fecha a ajuda"]["estado"]["ajuda"]) == (True, False)
    assert t["h abre"]["estado"]["ajuda"] is True and t["enter fecha"]["estado"]["ajuda"] is False
    assert t["h com ctrl nao abre"]["tratou"] is False and t["h com ctrl nao abre"]["estado"]["ajuda"] is False and t["outra tecla"]["tratou"] is False
    assert t["esc com ajuda e clube fecha so a ajuda"]["antes"] == {"sel": ids[1], "ajuda": True} and t["esc com ajuda e clube fecha so a ajuda"]["estado"] == {"sel": ids[1], "ajuda": False}
    assert t["outra tecla com ajuda aberta"]["tratou"] is False and t["outra tecla com ajuda aberta"]["estado"] == {"sel": ids[1], "ajuda": True}
    assert t["backspace com ajuda aberta nao solta"]["tratou"] is False and t["backspace com ajuda aberta nao solta"]["estado"] == {"sel": ids[1], "ajuda": True}
    assert t["? fecha"]["tratou"] is True and t["? fecha"]["estado"] == {"sel": ids[1], "ajuda": False}


@precisa_dados
@precisa_node
def test_teclado_do_documento_so_age_com_a_tela_visivel(saida):
    k = saida["teclaNoDocumento"]
    assert k["escPrevenido"] is True and k["selDepoisDoEsc"] is None
    assert k["escondidoPrevenido"] is False and k["selEscondido"] is not None


@precisa_dados
@precisa_node
def test_toda_dica_abre_com_titulo_sem_texto_estragado_nem_nome_interno(saida):
    assert len(saida["tips"]) == 82 and saida["tipEscondeAoSair"] is True
    for t in saida["tips"]:
        assert t["visivel"] is True and t["html"] == t["tipHtml"] and t["html"].startswith("<b>") and t["tip"].split("||")[0]
        assert not re.search(r"NaN|undefined|Infinity|\[object|null", t["tip"]), t["tip"][:80]
        for ruim in INTERNOS:
            assert ruim not in t["tip"], (ruim, t["tip"][:80])


@precisa_dados
@precisa_node
def test_dica_escapa_html_e_monta_titulo_tabela_paragrafo_e_nota(saida):
    assert saida["tipHtml"]["completo"] == '<b>Título</b><div class="tv"><div><span>A</span><em>1</em></div><div><span>B</span><em>2</em></div></div><span>Parágrafo</span><small>Nota</small>'
    assert saida["tipHtml"]["escapado"] == "<b>&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;</b>"


@precisa_dados
@precisa_node
def test_sem_escudos_a_tela_cai_para_a_sigla_colorida_em_todas_as_linhas(montagem):
    s = rodar(montagem, "semlogos")
    nenhum = s["estados"][0]
    assert not s["rodape"]["ruim"] and not any(e["ruim"] for e in s["estados"])
    assert nenhum["p1"].count("<img") == 0 and nenhum["p1"].count('<span class="sg" style="background:') == 16
    assert nenhum["p3"].count("<image") == 0 and nenhum["p3"].count("<circle cx=") == 16
    com_logo = rodar(montagem)["estados"][0]
    assert com_logo["p1"].count("<img") == 16 and com_logo["p3"].count("<image") == 16 and com_logo["p2"].count("<img") >= 12
