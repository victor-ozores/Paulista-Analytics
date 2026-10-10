import colorsys
import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
PROTO = RAIZ / "prototype"
FASE_COD = {"PRIMEIRA FASE": 1, "QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}
LIMITE_TESTADO = 800_000  # TESTADO: o maior texto já visto renderizando no Power BI Desktop tem 795.218 caracteres (a página com oito telas); passar disso exige abrir a página nova no Desktop e só então subir este número
precisa_dados = pytest.mark.skipif(not (PROC / "fato_ingresso.csv").exists() or not (PROC / "ref_indicadores.csv").exists(), reason="rode scripts/03b, 04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")


def carregar(nome, arq):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def centavos(v):
    return int((Decimal(v) * 100).to_integral_value())


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def milhar(n):
    return f"{n:,}".replace(",", ".")


def pct_texto(a, b):
    return "—" if b <= 0 else f"{100 * a / b:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + "%"


# ---------- tabelas e cálculo independente ----------

@pytest.fixture(scope="module")
def tab():
    L = lambda n: ler_csv(PROC / f"{n}.csv")
    return {"partidas": {p["id_partida"]: p for p in L("fato_partida")}, "fase": {f["id_fase"]: FASE_COD[f["nome_fase"]] for f in L("dim_fase")}, "estadio": {e["id_estadio"]: e["nome_fpf"] for e in L("dim_estadio")},
            "ingressos": L("fato_ingresso"), "despesas": L("fato_despesa"), "rateio": L("fato_rateio"), "clubes": L("dim_clube"), "ref": L("ref_indicadores")}


def esperado(tab, meta, ids):
    ids = set(ids)
    cat = {n: i for i, n in enumerate(meta["cat"])}
    grp = {n: i for i, n in enumerate(meta["grp"])}
    rub = {n: i for i, n in enumerate(meta["rub"])}
    ps = [tab["partidas"][i] for i in ids]
    r = {"n": len(ps), "pu": sum(int(p["publico_boletim"]) for p in ps), "pg": sum(int(p["publico_pagante"]) for p in ps), "rb": sum(centavos(p["renda_bruta"]) for p in ps), "ds": sum(centavos(p["despesas_total"]) for p in ps), "rl": sum(centavos(p["renda_liquida"]) for p in ps),
         "neg": sum(1 for p in ps if Decimal(p["renda_liquida"]) < 0), "ci": [0] * len(cat), "cr": [0] * len(cat), "gd": [0] * len(grp), "bd": [0, 0, 0], "vi": 0, "vr": 0, "dd": 0, "lq": 0}
    ru = defaultdict(int)
    for i in tab["ingressos"]:
        if i["id_partida"] in ids:
            r["ci"][cat[i["categoria"]]] += int(i["ingressos"])
            r["cr"][cat[i["categoria"]]] += centavos(i["arrecadacao"])
            if i["setor_visitante"] == "1":
                r["vi"] += int(i["ingressos"])
                r["vr"] += centavos(i["arrecadacao"])
    for d in tab["despesas"]:
        if d["id_partida"] in ids:
            r["gd"][grp[d["grupo"]]] += centavos(d["valor"])
            r["bd"][int(d["bloco_codigo"][1]) - 1] += centavos(d["valor"])
            ru[rub[d["rubrica"]]] += centavos(d["valor"])
    for x in tab["rateio"]:
        if x["id_partida"] in ids:
            r["dd"] += centavos(x["deducao_inss"]) + centavos(x["deducao_outras"])
            r["lq"] += centavos(x["liquido"])
    r["ru"] = [[k, v] for k, v in sorted(ru.items())]
    if ps:
        r["pmax"], r["pmin"] = max(int(p["publico_boletim"]) for p in ps), min(int(p["publico_boletim"]) for p in ps)
    return r


def passa(tab, f, p, i, ignorar=()):
    """Filtro escrito de novo em Python, sem olhar o JavaScript."""
    fase1 = tab["fase"][p["id_fase"]] == 1
    if f.get("fase", 0) == 1 and not fase1:
        return False
    if f.get("fase", 0) == 2 and fase1:
        return False
    if f.get("rodadas") and int(p["rodada"]) not in f["rodadas"]:
        return False
    if f.get("estadios") and tab["estadio"][p["id_estadio"]] not in f["estadios"]:
        return False
    if f.get("dias") and date.fromisoformat(p["data_jogo"]).isoweekday() not in f["dias"]:
        return False
    if f.get("horas") and p["hora_programada"] not in f["horas"]:
        return False
    rl = Decimal(p["renda_liquida"])
    if f.get("res") == 1 and not rl < 0:
        return False
    if f.get("res") == 2 and not rl >= 0:
        return False
    clubes = f.get("clubes") or []
    if clubes and "clube" not in ignorar:
        m, v, como = p["id_clube_mandante"] in clubes, p["id_clube_visitante"] in clubes, f.get("como", "m")
        if (como == "m" and not m) or (como == "v" and not v) or (como == "mv" and not (m or v)):
            return False
    if f.get("jogo") and "jogo" not in ignorar and i != f["jogo"]:
        return False
    return True


def ids_do_recorte(tab, f, ignorar=()):
    return [i for i, p in tab["partidas"].items() if passa(tab, f, p, i, ignorar)]


def esperado_por_clube(tab, meta, f):
    como = f.get("como", "m")
    saida = {c["id_clube"]: {"n": 0, "pu": 0, "rb": 0, "rl": 0, "pg": 0, "vi": 0} for c in tab["clubes"]}
    for i in ids_do_recorte(tab, f, ignorar=("clube", "jogo")):
        e, p = esperado(tab, meta, [i]), tab["partidas"][i]
        for idc in ({"m": [p["id_clube_mandante"]], "v": [p["id_clube_visitante"]], "mv": [p["id_clube_mandante"], p["id_clube_visitante"]]}[como]):
            s = saida[idc]
            s["n"] += 1
            s["pu"] += e["pu"]
            s["rb"] += e["rb"]
            s["rl"] += e["rl"]
            s["pg"] += e["pg"]
            s["vi"] += e["vi"]
    return saida


# ---------- casos enviados ao JavaScript ----------

def gerar_casos(tab, dados):
    clubes = [c["id"] for c in dados["clubes"]]
    nome = {c["curto"]: c["id"] for c in dados["clubes"]}
    cor, pal, san = nome["Corinthians"], nome["Palmeiras"], nome["Santos"]
    estadios = sorted({tab["estadio"][p["id_estadio"]] for p in tab["partidas"].values()})
    dias = sorted({date.fromisoformat(p["data_jogo"]).isoweekday() for p in tab["partidas"].values()})
    horas = sorted({p["hora_programada"] for p in tab["partidas"].values()})
    combos = [{}, {"fase": 1}, {"fase": 2}]
    for como in ("m", "v", "mv"):
        combos += [{"clubes": [c], "como": como} for c in clubes]
        combos += [{"clubes": [cor, pal], "como": como}, {"clubes": [cor, pal, san], "como": como}, {"clubes": [nome["Novorizontino"], nome["Botafogo"], nome["Mirassol"], nome["Guarani"]], "como": como}]
    combos += [{"rodadas": [r]} for r in range(1, 13)] + [{"rodadas": [1, 2, 3]}, {"rodadas": [9, 10, 11, 12]}, {"rodadas": [8, 9]}]
    combos += [{"dias": [d]} for d in dias] + [{"dias": [6, 7]}]
    combos += [{"horas": [h]} for h in horas] + [{"horas": ["16:00", "20:30"]}]
    combos += [{"estadios": [e]} for e in estadios] + [{"estadios": estadios[:2]}]
    combos += [{"res": 1}, {"res": 2}, {"res": 1, "fase": 1}, {"res": 2, "fase": 2}, {"clubes": [cor], "como": "v", "res": 2}, {"clubes": [pal, san], "como": "mv", "dias": [7], "fase": 1}]
    combos += [{"metrica": "ren"}, {"metrica": "ren", "res": 1}, {"metrica": "ren", "fase": 2}, {"metrica": "ren", "clubes": [nome["Capivariano"]], "como": "m"}, {"metrica": "ren", "clubes": [cor], "como": "mv"}]
    rnd = random.Random(2026)
    for _ in range(160):
        f = {"fase": rnd.choice([0, 0, 1, 2]), "como": rnd.choice(["m", "v", "mv"]), "rank": rnd.choice(["pub", "ren", "liq", "vis"]), "metrica": rnd.choice(["ing", "ren"])}
        if rnd.random() < .6:
            f["clubes"] = rnd.sample(clubes, rnd.randint(1, 4))
        if rnd.random() < .3:
            f["rodadas"] = rnd.sample(range(1, 13), rnd.randint(1, 3))
        if rnd.random() < .3:
            f["dias"] = rnd.sample(dias, rnd.randint(1, 2))
        if rnd.random() < .3:
            f["horas"] = rnd.sample(horas, rnd.randint(1, 2))
        if rnd.random() < .3:
            f["estadios"] = rnd.sample(estadios, rnd.randint(1, 3))
        if rnd.random() < .25:
            f["res"] = rnd.choice([1, 2])
        combos.append(f)
    primeiro = min(tab["partidas"].values(), key=lambda p: (p["data_hora_programada"], int(p["numero_jogo"])))["id_partida"]
    render = [{"nome": n, "filtros": f} for n, f in (("todos", {}), ("dois clubes", {"clubes": [cor, pal]}), ("visitante", {"clubes": [cor], "como": "v", "rank": "vis"}), ("mata-mata sábado e domingo", {"fase": 2, "dias": [6, 7], "rank": "liq", "metrica": "ren"}),
                                                      ("prejuízo", {"res": 1, "rank": "ren"}), ("jogo", {"jogo": primeiro}), ("20h30 em estádio", {"horas": ["20:30"], "estadios": estadios[:3], "como": "mv", "clubes": [san]}))]
    return {"combos": combos, "render": render}


@pytest.fixture(scope="module")
def montagem(tmp_path_factory):
    m = carregar("montar_app13", "13_montar_app.py")
    versus = m.modulo_versus().montar_dados()
    dados = m.montar_todos_os_dados(versus)
    frag = m.montar_fragmentos(dados)
    pasta = tmp_path_factory.mktemp("app")
    (pasta / "financeiro.html").write_text(m.pagina("t", m.logos_js(versus) + frag["fin"]), encoding="utf-8")
    (pasta / "app.html").write_text(m.pagina("t", frag["app"]), encoding="utf-8")
    return {"m": m, "versus": versus, "fin": dados["fin"], "conf": dados["conf"], "clas": dados["clas"], "frag_versus": frag["vs"], "frag_fin": frag["fin"], "frag_conf": frag["conf"], "frag_clas": frag["clas"], "app": frag["app"], "pasta": pasta}


@pytest.fixture(scope="module")
def casos(montagem, tab):
    c = gerar_casos(tab, montagem["fin"])
    (montagem["pasta"] / "casos.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    return c


@pytest.fixture(scope="module")
def saida(montagem, casos):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_fin.js"), str(montagem["pasta"] / "financeiro.html"), str(montagem["pasta"] / "casos.json")], capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr[-1500:]
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def meta(saida):
    return saida["meta"]


# ---------- pacote de dados ----------

@precisa_dados
def test_pacote_fecha_com_o_gabarito_e_com_as_tabelas(montagem, tab):
    d = montagem["fin"]
    js = d["jogos"]
    assert len(js) == 72 and len(d["clubes"]) == 16 and len(d["cat"]) == 6 and len(d["grp"]) == 10 and len(d["rub"]) == 43
    assert sum(j["pu"] for j in js) == 784369 and sum(j["rb"] for j in js) == 4473000380 and sum(j["ds"] for j in js) == 2040474714 and sum(j["rl"] for j in js) == 2432525666
    assert [j["i"] for j in js] == sorted(tab["partidas"], key=lambda i: (tab["partidas"][i]["data_hora_programada"], int(tab["partidas"][i]["numero_jogo"])))
    meta = {"cat": [c["n"] for c in d["cat"]], "grp": [g["n"] for g in d["grp"]], "rub": [r[0] for r in d["rub"]]}
    for j in js:
        e = esperado(tab, meta, [j["i"]])
        for k in ("pu", "pg", "rb", "ds", "rl", "ci", "cr", "gd", "bd", "vi", "vr", "dd", "lq"):
            assert j[k] == e[k], (j["n"], k)
        assert j["rb2"] == e["ru"], j["n"]


@precisa_dados
def test_categorias_e_grupos_do_pacote_seguem_os_arquivos_de_referencia(montagem):
    d = montagem["fin"]
    assert [c["n"] for c in d["cat"]] == ["Inteira", "Meia-entrada", "Sócio-torcedor", "Cadeira e camarote", "Gratuidade por lei", "Outros"]
    assert all(c["t"] and "data/referencia" not in c["t"] and "A45" not in c["t"] for c in d["cat"])
    assert [g["v"] for g in d["grp"]] == sorted((g["v"] for g in d["grp"]), reverse=True)
    assert "Sem grupo" not in [g["n"] for g in d["grp"]]
    assert all(0 <= r[1] < 10 and 0 <= r[2] < 3 for r in d["rub"])


@precisa_dados
def test_pacote_nao_leva_escudos_porque_eles_vem_do_duelo(montagem):
    assert "data:image" not in json.dumps(montagem["fin"])
    assert set(montagem["fin"]["clubes"][0]) == {"id", "nome", "curto", "sigla", "cor"}


# ---------- montagem das páginas ----------

@precisa_dados
def test_pagina_do_app_traz_as_tres_telas_sem_marca_sobrando_e_ids_unicos(montagem):
    app = montagem["app"]
    assert not re.search(r"__[A-Z_]+__", app)
    ids = re.findall(r'\bid="([^"]+)"', re.sub(r"<script>[\s\S]*?</script>", "", app))
    assert len(ids) == len(set(ids)), [i for i in set(ids) if ids.count(i) > 1]
    for esperado_id in ("pa", "mod-vg", "mod-vs", "mod-clas", "mod-gl", "mod-ds", "mod-jg", "mod-fin", "mod-conf", "vgx", "vsx", "clx", "glx", "dsx", "jgx", "fnx", "cnx"):
        assert esperado_id in ids
    assert app.count('data-mod="vg"') == 1 and app.count('data-mod="vs"') == 1 and app.count('data-mod="clas"') == 1 and app.count('data-mod="gl"') == 1 and app.count('data-mod="ds"') == 1 and app.count('data-mod="jg"') == 1 and app.count('data-mod="fin"') == 1 and app.count('data-mod="conf"') == 2  # o botao da barra e o selo
    assert app.index('id="vsx"') < app.index('id="vgx"') < app.index('id="clx"') < app.index('id="glx"') < app.index('id="dsx"') < app.index('id="jgx"') < app.index('id="fnx"') < app.index('id="cnx"')
    assert app.index("window.PA.shell=true") < app.index('id="vsx"')


@precisa_dados
def test_pagina_do_app_cabe_no_limite_planejado_para_o_visual(montagem):
    assert len(montagem["app"]) < LIMITE_TESTADO


@precisa_dados
def test_selo_da_barra_usa_as_regras_do_resultado(montagem):
    m = montagem["fin"]["meta"]
    assert f"{m['regras']} regras · {m['aber']} abertas" in montagem["app"]
    assert m["regras"] == 45


@precisa_dados
@precisa_node
def test_javascript_de_todos_os_blocos_tem_sintaxe_valida(montagem, tmp_path):
    scripts = re.findall(r"<script>([\s\S]*?)</script>", montagem["app"])
    assert len(scripts) == 10
    for n, codigo in enumerate(scripts):
        arq = tmp_path / f"s{n}.js"
        arq.write_text(codigo, encoding="utf-8")
        proc = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, (n, proc.stderr[-400:])


@precisa_dados
def test_versus_dentro_do_app_ocupa_o_modulo_e_so_age_quando_visivel():
    frag = (PROTO / "versus" / "fragmento.html").read_text(encoding="utf-8")
    assert "height:100%;min-height:320px" in frag and "height:100vh" not in frag
    assert "if(!raiz.offsetParent)return;" in frag
    assert "if(window.PA)window.PA.clubes=D.clubes;" in frag
    fin = (PROTO / "financeiro" / "fragmento.html").read_text(encoding="utf-8")
    assert "height:100%;min-height:320px" in fin and "if(!raiz.offsetParent)return;" in fin


@precisa_dados
def test_textos_da_tela_nao_citam_arquivos_nem_regras_internas():
    fin = (PROTO / "financeiro" / "fragmento.html").read_text(encoding="utf-8")
    for proibido in ("data/referencia", ".csv", "A45", "fato_", "scripts/"):
        assert proibido not in fin, proibido


# ---------- filtros: o recorte de cada combinação bate com as tabelas ----------

@precisa_dados
@precisa_node
def test_cada_recorte_tem_os_mesmos_jogos_e_as_mesmas_somas_das_tabelas(saida, casos, tab, montagem, meta):
    campos = ("n", "pu", "pg", "rb", "ds", "rl", "dd", "lq", "vi", "vr", "neg", "pmax", "pmin", "ci", "cr", "gd", "bd", "ru")
    ordem = [j["i"] for j in montagem["fin"]["jogos"]]
    assert len(saida["combos"]) == len(casos["combos"]) >= 250
    vazios = 0
    for c in saida["combos"]:
        f = c["filtros"]
        certos = set(ids_do_recorte(tab, f))
        assert c["ids"] == [i for i in ordem if i in certos], f
        e = esperado(tab, meta, certos)
        if not certos:
            vazios += 1
            assert c["n"] == 0
            continue
        for k in campos:
            assert c[k] == e[k], (f, k)
    assert vazios < len(saida["combos"]) // 3
    assert len(saida["jogos"]) == 72
    for j in saida["jogos"]:
        e = esperado(tab, meta, [j["jogo"]])
        for k in campos:
            assert j[k] == e[k], (j["jogo"], k)


@precisa_dados
@precisa_node
def test_ranking_por_clube_bate_com_as_tabelas_em_casa_fora_e_nos_dois(saida, tab, meta):
    for c in saida["combos"]:
        f = c["filtros"]
        certo = esperado_por_clube(tab, meta, f)
        achado = {x["id"]: {k: x[k] for k in ("n", "pu", "rb", "rl", "pg", "vi")} for x in c["rk"]}
        assert achado == certo, f


@precisa_dados
@precisa_node
def test_ranking_de_casa_bate_com_o_gabarito_de_publico_medio_do_clube(saida, tab):
    ref = {l["id_clube"]: Decimal(l["valor"]) for l in tab["ref"] if l["escopo"] == "clube" and l["id_indicador"] == "I32"}
    todos = next(c for c in saida["combos"] if c["filtros"] == {})
    assert len(todos["rk"]) == 16
    for x in todos["rk"]:
        assert round(x["pu"] / x["n"]) == round(ref[x["id"]]), x["id"]


@precisa_dados
@precisa_node
def test_nenhum_painel_mostra_valor_quebrado_e_todos_tem_a_estrutura_esperada(saida):
    for c in saida["combos"] + saida["jogos"]:
        i = c["info"]
        assert not i["ruim"], c.get("filtros")
        if c["n"] == 0:
            assert i["vazio"]
            continue
        assert (i["legenda"], i["barras"], i["grupos"], i["blocos"], i["clubes"], i["kpis"]) == (6, 5, 10, 3, 16, 7)
        assert i["tips"] >= 40
        assert 1 <= i["fatias"] <= 6
        assert i["comoOn"] in ("m", "v", "mv")


@precisa_dados
@precisa_node
def test_cabecalho_mostra_filtros_ligados_limpar_e_o_nome_do_ranking(saida):
    nome = {"m": "Por mandante", "v": "Por visitante", "mv": "Por clube"}
    for c in saida["combos"]:
        f, i = c["filtros"], c["info"]
        assert c["temFiltro"] == bool(f.get("fase") or f.get("clubes") or f.get("rodadas") or f.get("estadios") or f.get("dias") or f.get("horas") or f.get("res"))
        assert i["limparVisivel"] == c["temFiltro"]
        grupos = sum(1 for k in ("clubes", "rodadas", "estadios", "dias", "horas") if f.get(k)) + (1 if f.get("res") else 0)
        assert c["nFiltros"] == grupos
        assert i["comoApagado"] == (not f.get("clubes"))
        assert i["filtrosN"] == grupos and i["filtrosAtivo"] == bool(grupos)
        assert i["filtrosLegenda"] == (("1 ligado" if grupos == 1 else f"{grupos} ligados") if grupos else "mais opções")
        assert i["botoesDoCabecalho"] == {"fase": 3, "como": 3, "filtros": 1, "limpar": 1, "ajuda": 1}
        como = f.get("como", "m")
        assert i["tituloRanking"] == nome[como] and i["comoOn"] == como
        assert i["classeRanking"] == "m-" + f.get("rank", "pub")


@precisa_dados
@precisa_node
def test_clubes_escolhidos_aparecem_marcados_no_ranking_e_na_janela_de_filtros(saida):
    for c in saida["combos"]:
        f, i, d = c["filtros"], c["info"], c["dialogo"]
        assert not d["ruim"]
        assert i["selecionados"] == len(f.get("clubes", []))
        assert (d["clubes"], d["rod"], d["dia"], d["hora"], d["est"], d["res"]) == (16, 12, 6, 12, 16, 3)
        assert (d["clubesOn"], d["rodOn"], d["diaOn"], d["horaOn"], d["estOn"]) == (len(f.get("clubes", [])), len(f.get("rodadas", [])), len(f.get("dias", [])), len(f.get("horas", [])), len(f.get("estadios", [])))
        assert d["resOn"] == str(f.get("res", 0)) and d["comoOn"] == f.get("como", "m")
        assert d["titulo"] == f"{c['n']} jogo{'' if c['n'] == 1 else 's'} no recorte"
        sem_jogo = [x for x in c["rk"] if not x["n"] and x["id"] not in f.get("clubes", [])]
        assert d["clubesOff"] == len(sem_jogo)


@precisa_dados
@precisa_node
def test_jogo_escolhido_aparece_marcado_e_mostra_so_ele(saida):
    for j in saida["jogos"]:
        assert j["info"]["jogosSel"] == 1 and j["info"]["limparVisivel"] and j["n"] == 1 and j["info"]["selecionados"] == 1


@precisa_dados
@precisa_node
def test_opcoes_da_janela_de_filtros_vem_dos_dados_com_as_contagens_certas(saida, tab):
    o = saida["opc"]
    assert [x["v"] for x in o["rod"]] == list(range(1, 13)) and [x["q"] for x in o["rod"]] == [8] * 8 + [4, 2, 1, 1]
    assert [x["t"] for x in o["rod"]][8:] == ["Quartas", "Semifinal", "Final ida", "Final volta"] and o["rod"][0]["t"] == "1ª"
    assert [(x["v"], x["t"], x["q"]) for x in o["dia"]] == [(1, "Segunda", 1), (2, "Terça", 3), (3, "Quarta", 8), (4, "Quinta", 7), (6, "Sábado", 21), (7, "Domingo", 32)]
    horas = defaultdict(int)
    est = defaultdict(int)
    for p in tab["partidas"].values():
        horas[p["hora_programada"]] += 1
        est[tab["estadio"][p["id_estadio"]]] += 1
    assert [(x["v"], x["q"]) for x in o["hora"]] == sorted(horas.items())
    assert [(x["v"], x["q"]) for x in o["est"]] == sorted(est.items(), key=lambda kv: (-kv[1], sem_acento(kv[0])))
    assert sum(x["q"] for x in o["hora"]) == sum(x["q"] for x in o["est"]) == 72


@precisa_dados
@precisa_node
def test_lista_de_jogos_vem_ordenada_pela_coluna_e_desempata_pelo_numero_do_jogo(saida, tab):
    assert len(saida["ordem"]) == 8
    num = {i: int(p["numero_jogo"]) for i, p in tab["partidas"].items()}
    for o in saida["ordem"]:
        assert len(o["ids"]) == 72
        v = o["valores"]
        assert v == sorted(v, reverse=(o["dir"] == -1))
        for a, b in zip(range(71), range(1, 72)):
            if v[a] == v[b]:
                assert num[o["ids"][a]] < num[o["ids"][b]]


# ---------- descrição do recorte, cliques e teclado ----------

@precisa_dados
@precisa_node
def test_descricao_do_recorte_em_palavras(saida, tab):
    d = saida["descricoes"]
    assert len(d) == 19
    textos = [x["texto"] for x in d]
    n = lambda i: d[i]["n"]
    assert textos[0] == "Todas as fases · 72 jogos do Paulistão A1 2026"
    assert textos[1] == "1ª fase · 64 jogos do Paulistão A1 2026"
    assert textos[2] == "Corinthians como mandante · 4 jogos"
    assert textos[3] == "Corinthians e Palmeiras como mandantes · 11 jogos"
    assert textos[4] == "Corinthians, Palmeiras e Santos como mandantes · 15 jogos"
    assert textos[5] == f"Corinthians, Palmeiras e mais 2 como mandantes · {n(5)} jogos"
    assert textos[6] == f"Corinthians como visitante · {n(6)} jogos"
    assert textos[7] == f"Corinthians e Palmeiras (em casa ou fora) · {n(7)} jogos"
    assert textos[8] == "rodadas 1 e 2 e quartas de final · 20 jogos"
    assert textos[9] == "rodada 3 · 8 jogos"
    assert textos[10] == "sábado e domingo · 53 jogos"
    assert textos[11] == "às 20:30 · 24 jogos"
    assert textos[12] == "às 16:00 e 20:30 · 33 jogos"
    assert textos[13] == f"4 horários · {n(13)} jogos"
    assert textos[14].endswith(" · 7 jogos") and textos[15] == "2 estádios · 14 jogos"
    assert textos[16] == "só jogos no prejuízo · 15 jogos"
    assert textos[17] == f"Mata-mata · só jogos com lucro · {n(17)} jogos"
    assert textos[18] == "São Bernardo 4 × 0 Capivariano · 1ª fase · rodada 1 · 10/01/2026"
    for x in d:
        assert x["n"] == len(ids_do_recorte(tab, x["filtros"])), x["filtros"]


@precisa_dados
@precisa_node
def test_cliques_somam_e_tiram_clubes_e_os_filtros_extras_mudam_o_recorte(saida, tab, montagem):
    a = saida["acoes"]
    e = lambda i: a[i]["estado"]
    cor, pal, san, cap = (next(c["id"] for c in montagem["fin"]["clubes"] if c["curto"] == nm) for nm in ("Corinthians", "Palmeiras", "Santos", "Capivariano"))
    assert (e(0)["clubes"], e(0)["n"]) == ([cor], 4)
    assert (e(1)["clubes"], e(1)["n"]) == ([cor, pal], 11)
    assert (e(2)["clubes"], e(2)["n"]) == ([pal], 7)
    assert (e(3)["clubes"], e(3)["n"]) == ([pal, cor], 11)
    assert (e(4)["clubes"], e(4)["n"]) == ([pal, cor, san], 15)
    assert e(5)["como"] == "v" and e(6)["como"] == "mv" and e(7)["como"] == "m" and e(7)["n"] == 15
    assert (e(8)["jogo"], e(8)["n"], e(8)["clubes"]) == (a[8]["passo"][1], 1, [pal, cor, san])
    assert (e(9)["jogo"], e(9)["n"]) == (None, 15)
    assert e(10)["jogo"] == a[8]["passo"][1] and e(10)["n"] == 1
    assert (e(11)["clubes"], e(11)["jogo"], e(11)["n"]) == ([cor, san], None, 8)
    assert (e(12)["clubes"], e(12)["fase"], e(12)["n"], e(12)["temFiltro"]) == ([], 0, 72, False)
    assert (e(13)["fase"], e(13)["n"]) == (2, 8)
    assert (e(14)["clubes"], e(14)["n"]) == ([], 8)
    assert (e(15)["fase"], e(15)["n"]) == (0, 72)
    assert e(16)["clubes"] == [cap] and e(16)["n"] == sum(1 for p in tab["partidas"].values() if p["id_clube_mandante"] == cap)
    assert (e(17)["clubes"], e(17)["n"]) == ([], 72)
    assert (e(18)["rodadas"], e(18)["n"]) == ([9], 4)
    assert (e(19)["rodadas"], e(19)["n"]) == ([9, 10], 6)
    assert (e(20)["rodadas"], e(20)["n"]) == ([10], 2)
    assert e(21)["dias"] == [7] and e(22)["dias"] == [6, 7] and e(23)["horas"] == ["20:30"] and e(24)["estadios"] == [saida["meta"]["estadios"][0]]
    assert e(25)["res"] == 1 and e(26)["res"] == 0
    assert (e(27)["n"], e(27)["rodadas"], e(27)["dias"], e(27)["horas"], e(27)["estadios"], e(27)["res"], e(27)["nFiltros"]) == (72, [], [], [], [], 0, 0)
    assert (e(28)["res"], e(28)["n"]) == (1, 15)
    assert (e(29)["jogo"], e(29)["n"]) == (a[29]["passo"][1], 1)
    assert (e(30)["res"], e(30)["jogo"], e(30)["n"]) == (2, None, 57)
    assert (e(31)["n"], e(31)["temFiltro"]) == (72, False)
    assert e(32)["metrica"] == "ren" and e(33)["rank"] == "vis"
    assert (e(34)["ord"], e(34)["dir"]) == ("pu", -1) and e(35)["dir"] == 1 and (e(36)["ord"], e(36)["dir"]) == ("d", 1)
    filtros_de = lambda s: {"fase": s["fase"], "clubes": s["clubes"], "como": s["como"], "rodadas": s["rodadas"], "estadios": s["estadios"], "dias": s["dias"], "horas": s["horas"], "res": s["res"], "jogo": s["jogo"]}
    for x in a:
        assert x["estado"]["n"] == len(ids_do_recorte(tab, filtros_de(x["estado"]))), x["passo"]


@precisa_dados
@precisa_node
def test_com_como_visitante_ou_os_dois_entram_os_jogos_certos(saida, tab, montagem):
    cor = next(c["id"] for c in montagem["fin"]["clubes"] if c["curto"] == "Corinthians")
    pal = next(c["id"] for c in montagem["fin"]["clubes"] if c["curto"] == "Palmeiras")
    contagem = {}
    for c in saida["combos"]:
        f = c["filtros"]
        if f.get("clubes") in ([cor], [cor, pal]) and set(f) <= {"clubes", "como"}:
            contagem[(tuple(f["clubes"]), f.get("como", "m"))] = c["n"]
    jogos = list(tab["partidas"].values())
    assert contagem[((cor,), "m")] == sum(1 for p in jogos if p["id_clube_mandante"] == cor) == 4
    assert contagem[((cor,), "v")] == sum(1 for p in jogos if p["id_clube_visitante"] == cor)
    assert contagem[((cor,), "mv")] == contagem[((cor,), "m")] + contagem[((cor,), "v")]
    assert contagem[((cor, pal), "mv")] == sum(1 for p in jogos if {p["id_clube_mandante"], p["id_clube_visitante"]} & {cor, pal})
    entre_si = sum(1 for p in jogos if {p["id_clube_mandante"], p["id_clube_visitante"]} == {cor, pal})
    assert entre_si > 0 and contagem[((cor, pal), "mv")] == contagem[((cor, pal), "m")] + contagem[((cor, pal), "v")] - sum(1 for p in jogos if p["id_clube_mandante"] in (cor, pal) and p["id_clube_visitante"] in (cor, pal))


@precisa_dados
@precisa_node
def test_escape_solta_jogo_depois_clubes_fecha_filtros_e_ajuda(saida):
    t = saida["tecla"]
    assert t[0] == {"abriuFiltros": True, "conteudo": True}
    assert t[1] == {"outraTecla": False, "aindaAberto": True}
    assert t[2] == {"escape": True, "fechado": True}
    assert t[3]["tratou"] and t[3]["depois"]["jogo"] is None and len(t[3]["depois"]["clubes"]) == 2 and t[3]["depois"]["n"] == 11
    assert t[4]["tratou"] and t[4]["depois"]["clubes"] == [] and t[4]["depois"]["n"] == 72
    assert not t[5]["tratou"]
    assert t[6] == {"abrir": True, "aberta": True, "fechou": True, "fechada": True, "hcomCtrl": False}
    assert t[7] == {"qAbertoComFiltros": False, "ajudaFechada": True}


# ---------- números exibidos e cores ----------

@precisa_dados
@precisa_node
def test_numeros_dos_quadros_de_cima_no_todo_e_no_jogo_no_prejuizo(saida):
    kpi = saida["kpi"]
    assert [x[:4] for x in kpi["todos"]["fmt"]] == [["pu", "784.369", "", ""], ["pm", "10.894", "", ""], ["rb", "44,73", "R$", "mi"], ["ds", "20,40", "R$", "mi"], ["rl", "24,33", "R$", "mi"], ["tk", "58,74", "R$", ""], ["vi", "69.685", "", ""]]
    assert [x[:4] for x in kpi["jogo1"]["fmt"]] == [["pu", "1.175", "", ""], ["pm", "1.175", "", ""], ["rb", "28,6", "R$", "mil"], ["ds", "42,1", "R$", "mil"], ["rl", "13,5", "−R$", "mil"], ["tk", "24,41", "R$", ""], ["vi", "72", "", ""]]
    assert "−R$ 13.503,80" in kpi["jogo1"]["html"] and "147,2% da renda bruta" in kpi["jogo1"]["html"]
    assert "Todas as fases · 72 jogos" in kpi["todos"]["sub"] and "Corinthians como mandante · 4 jogos" in kpi["corinthians"]["sub"] and "São Bernardo 4 × 0 Capivariano" in kpi["jogo1"]["sub"]
    assert "Corinthians e Palmeiras como mandantes · 11 jogos" in kpi["corinthians e palmeiras"]["sub"]
    assert "sem jogos" in kpi["vazio"]["html"] and "Nenhum" not in kpi["vazio"]["html"]


def matiz(hexa):
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


FAMILIA = {"verde": (100, 160), "vermelho": (340, 360), "amarelo": (38, 56), "ciano": (180, 200), "roxo": (250, 290)}


def na_familia(hexa, nome):
    h = matiz(hexa)
    lo, hi = FAMILIA[nome]
    return lo <= h <= hi or (nome == "vermelho" and h <= 6)


@precisa_dados
@precisa_node
def test_cores_do_dinheiro_verde_despesa_vermelha_ticket_amarelo(saida):
    padrao = dict((k, c) for k, c in saida["cores"]["kpiPadrao"])
    assert na_familia(padrao["rb"], "verde") and na_familia(padrao["rl"], "verde")
    assert na_familia(padrao["ds"], "vermelho")
    assert na_familia(padrao["tk"], "amarelo")
    assert na_familia(padrao["pu"], "ciano") and na_familia(padrao["pm"], "ciano") and na_familia(padrao["vi"], "roxo")
    assert padrao["rb"] != padrao["rl"]
    cor_do = {nome: dict((x[0], x[4]) for x in k["fmt"]) for nome, k in saida["kpi"].items()}
    assert na_familia(cor_do["todos"]["rl"], "verde") and na_familia(cor_do["jogo1"]["rl"], "vermelho")
    assert na_familia(cor_do["jogo1"]["ds"], "vermelho") and na_familia(cor_do["jogo1"]["rb"], "verde") and na_familia(cor_do["jogo1"]["tk"], "amarelo")
    itens = {c["nome"]: {i["n"]: i["cor"] for i in c["itens"]} for c in saida["cascata"]}
    t = itens["todos"]
    assert na_familia(t["Renda bruta"], "verde") and na_familia(t["Renda líquida"], "verde") and na_familia(t["Líquido a receber"], "verde")
    assert na_familia(t["Despesas"], "vermelho") and na_familia(t["Deduções"], "vermelho")
    assert t["Renda bruta"] != t["Renda líquida"] and t["Despesas"] != t["Deduções"]
    p = itens["jogo1"]
    assert na_familia(p["Renda líquida"], "vermelho") and na_familia(p["Líquido a receber"], "vermelho") and na_familia(p["Renda bruta"], "verde")


@precisa_dados
def test_cores_do_desenho_da_tela_no_css():
    fonte = (PROTO / "financeiro" / "fragmento.html").read_text(encoding="utf-8")
    css = fonte.split("</style>")[0]
    v = dict(re.findall(r"--(\w+):(#[0-9a-f]{6})", css))
    assert na_familia(v["ver"], "verde") and na_familia(v["verc"], "verde") and na_familia(v["verm"], "vermelho") and na_familia(v["vermc"], "vermelho")
    assert "--pc" not in css
    assert re.search(r"\.gr \.g \.tr u\{[^}]*var\(--vermc\),var\(--verm\)", css)
    assert re.search(r"\.rk\.m-ren\{--b1:#[0-9a-f]{6};--b2:var\(--verc\)\}", css) and re.search(r"\.rk\.m-liq\{--b1:var\(--verc\);--b2:var\(--ver\)\}", css)
    assert re.search(r"\.rk \.r\.neg \.tr u\{background:linear-gradient\(90deg,var\(--vermc\),var\(--verm\)\)\}", css)
    assert re.search(r"\.lg \.l:not\(\.cab\)>span:nth-child\(4\)\{color:var\(--verc\)\}", css) and re.search(r"\.lg \.l:not\(\.cab\)>span:nth-child\(5\)\{color:var\(--gold\)\}", css)
    assert re.search(r"\.jr \.n\.rb\{color:var\(--verc\)\}", css) and re.search(r"\.jr \.n\.lq\{color:var\(--ver\)\}", css) and re.search(r"\.jr \.n\.neg\{color:var\(--verm\)\}", css)
    assert na_familia(re.search(r"--gold:(#[0-9a-f]{6})", css).group(1), "amarelo")
    blocos = re.search(r"var BLOCO_COR=\[([^\]]*)\]", fonte).group(1)
    assert len(re.findall(r"#[0-9a-f]{6}", blocos)) == 3 and all(na_familia(c, "vermelho") for c in re.findall(r"#[0-9a-f]{6}", blocos))


@precisa_dados
@pytest.mark.parametrize("pasta,prefixo", [("visao_geral", "vgx"), ("classificacao", "clx"), ("gols", "glx"), ("disciplina", "dsx"), ("jogos", "jgx"), ("financeiro", "fnx"), ("conferencia", "cnx")])
def test_barra_de_cima_dos_paineis_e_branca_e_a_dos_quadros_continua_colorida(pasta, prefixo):
    css = (PROTO / pasta / "fragmento.html").read_text(encoding="utf-8").split("</style>")[0]
    painel = re.search(rf"#{prefixo} \.pn\{{([^}}]*)\}}", css).group(1)
    assert "border-top:4px solid #fff;" in painel
    regras = re.findall(rf"#{prefixo} \.p\d\{{([^}}]*)\}}", css)
    assert regras, "cada painel tem a sua regra de posição"
    for regra in regras:
        assert "border" not in regra and "--" not in regra, regra
    kpi = re.search(rf"#{prefixo} \.kpi\{{([^}}]*)\}}", css)
    assert kpi is not None or prefixo == "jgx", "só a tela Jogos não tem quadros de número"
    if kpi:
        assert "border-top:4px solid var(--kc)" in kpi.group(1)


def filtros_do_estado(s):
    return {"fase": s["fase"], "clubes": s["clubes"], "como": s["como"], "rodadas": s["rodadas"], "estadios": s["estadios"], "dias": s["dias"], "horas": s["horas"], "res": s["res"], "jogo": s["jogo"]}


@precisa_dados
@precisa_node
def test_centro_da_rosca_mostra_o_total_certo_em_texto_curto_que_cabe_no_furo(saida):
    so_ing = re.compile(r"^<b>([^<]*)</b><small>ingressos</small>$")
    so_ren = re.compile(r'^<small class="mo">R\$</small><b class="sm">([^<]*)</b><small>de renda bruta</small>$')
    vistos = {"ing": 0, "ren": 0}
    for c in saida["combos"] + saida["jogos"] + saida["jogosRenda"]:
        if c["n"] == 0:
            continue
        centro = c["info"]["centro"]
        m = so_ing.match(centro)
        if m:
            vistos["ing"] += 1
            assert m.group(1) == milhar(c["pu"]) and len(m.group(1)) <= 7, centro
            continue
        m = so_ren.match(centro)
        assert m, centro
        vistos["ren"] += 1
        texto = m.group(1)
        assert "R$" not in texto and len(texto) <= 8, texto
        confere(texto, c["rb"] / 100)
    assert vistos["ing"] > 100 and vistos["ren"] > 100


NOMES_QUADROS = ["Público total", "Público médio", "Renda bruta", "Despesas", "Renda líquida", "Ticket médio", "Torcida visitante"]


def kpi_como_escrito(texto):
    return re.sub(r"(mil|mi)$", r" \1", texto)


@precisa_dados
@precisa_node
def test_quadros_de_cima_escritos_na_tela_batem_com_as_tabelas_em_todos_os_recortes(saida, tab, meta):
    for c in saida["combos"] + saida["jogos"]:
        f = c["filtros"] if "filtros" in c else {"jogo": c["jogo"]}
        e = esperado(tab, meta, ids_do_recorte(tab, f))
        n = e["n"]
        k = dict(c["info"]["kpiTextos"])
        assert list(k) == NOMES_QUADROS, f
        assert k["Público total"] == milhar(e["pu"]), f
        confere(kpi_como_escrito(k["Público médio"]), e["pu"] / n if n else 0)
        confere(kpi_como_escrito(k["Renda bruta"]), e["rb"] / 100)
        confere(kpi_como_escrito(k["Despesas"]), e["ds"] / 100)
        confere(kpi_como_escrito(k["Renda líquida"]), e["rl"] / 100)
        confere(kpi_como_escrito(k["Ticket médio"]), e["rb"] / e["pg"] / 100 if e["pg"] else 0)
        assert k["Torcida visitante"] == milhar(e["vi"]), f


@precisa_dados
@precisa_node
def test_janela_de_filtros_tem_cabecalho_fixo_e_resumo_igual_aos_quadros_de_cima(saida):
    for c in saida["combos"] + saida["jogos"]:
        d, i = c["dialogo"], c["info"]
        assert d["cabecalhoFixo"], c.get("filtros")
        assert [x[0] for x in d["resumo"]] == NOMES_QUADROS
        assert d["resumo"] == i["kpiTextos"], c.get("filtros")
        assert d["aviso"] == (bool(c["filtros"].get("jogo")) if "filtros" in c else True)


@precisa_dados
@precisa_node
def test_qualquer_filtro_solta_o_jogo_escolhido_na_lista(saida):
    a = saida["acoes"]
    ini, idj = saida["passosLibera"]["primeiro"], saida["passosLibera"]["jogo"]
    e = lambda k: a[ini + k]["estado"]
    for k in (0, 2, 4, 6, 8, 10, 14, 17):
        assert a[ini + k]["passo"][0] == "jogo" and e(k)["jogo"] == idj and e(k)["n"] == 1, k
    for k in (1, 3, 5, 7, 9, 11, 15):
        assert e(k)["jogo"] is None and e(k)["n"] >= 1, a[ini + k]["passo"]
    assert [a[ini + k]["passo"][0] for k in (1, 3, 5, 7, 9, 11, 15)] == ["fase", "f-rod", "f-dia", "f-hora", "f-est", "f-res", "como"]
    assert e(1)["n"] > 1 and e(3)["n"] > 1 and e(15)["n"] > 1
    assert e(11)["n"] <= e(9)["n"] <= e(7)["n"] <= e(5)["n"] <= e(3)["n"] <= e(1)["n"]
    assert e(18)["jogo"] == idj and e(18)["como"] == "v" and e(18)["n"] == 1
    assert e(19)["jogo"] == idj and e(19)["como"] == "m"
    assert e(20)["jogo"] is None and e(20)["n"] == 72


ACOES_DA_TELA = {"fase", "como", "metrica", "rank", "ord", "clube", "jogo", "limpar", "f-limpar", "filtros", "f-fechar", "f-rod", "f-dia", "f-hora", "f-est", "f-res", "ajuda"}


@precisa_dados
@precisa_node
def test_todo_botao_da_tela_tem_uma_acao_conhecida(saida):
    assert set(saida["acoesVistas"]) == ACOES_DA_TELA


@precisa_dados
@precisa_node
def test_cliques_nos_botoes_do_html_levam_ao_estado_esperado(saida, tab, montagem):
    cl = saida["cliques"]
    assert len(cl) > 150
    listas = {"f-rod": ("rodadas", int), "f-dia": ("dias", int), "f-hora": ("horas", str), "f-est": ("estadios", str)}
    vistos = defaultdict(int)
    opc = saida["opc"]
    nome_clube = {c["id"]: c["curto"] for c in montagem["fin"]["clubes"]}
    for x in cl:
        a, d, v, i, rot, act, r = x["antes"], x["depois"], x["v"], x["id"], x["rot"], x["act"], x["rotulo"]
        vistos[act] += 1
        if act in ("f-rod", "f-dia", "f-hora"):
            o = next(o for o in opc[{"f-rod": "rod", "f-dia": "dia", "f-hora": "hora"}[act]] if str(o["v"]) == v)
            assert r == f"{o['t']}{o['q']}", rot
        elif act == "f-est":
            o = next(o for o in opc["est"] if o["v"] == v)
            assert r == f"{o['t']}{o['q']}", rot
        elif act == "f-res":
            assert r.startswith(["Todos", "Só prejuízo", "Só lucro"][int(v)]), rot
        elif act == "fase":
            assert r == ["Todas", "1ª fase", "Mata-mata"][int(v)], rot
        elif act == "como":
            assert r == {"m": "Mandante", "v": "Visitante", "mv": "Os dois"}[v], rot
        elif act == "clube":
            assert nome_clube[i] in r, rot
        elif act == "jogo":
            p = tab["partidas"][i]
            assert nome_clube[p["id_clube_mandante"]] in r and nome_clube[p["id_clube_visitante"]] in r, rot
        elif act == "metrica":
            assert r == {"ing": "Ingressos", "ren": "Renda"}[v], rot
        elif act == "rank":
            assert r == {"pub": "Público", "ren": "Renda", "liq": "Líquida", "vis": "Visitante"}[v], rot
        elif act == "ord":
            assert r.startswith({"d": "Data", "pu": "Público", "rb": "Renda", "rl": "Líquida"}[v]), rot
        elif act == "filtros":
            assert r.startswith("Filtros"), rot
        elif act in ("limpar", "f-limpar"):
            assert r in ("Limpar", "Limpar tudo"), rot
        elif act == "f-fechar":
            assert r == "Pronto", rot
        resto = lambda s, fora: {k: s[k] for k in s if k not in fora}
        if act in listas:
            campo, tipo = listas[act]
            assert (tipo(v) in a[campo]) != (tipo(v) in d[campo]), rot
            assert resto(d, (campo, "n")) == resto(a, (campo, "n")), rot
        elif act == "f-res":
            assert d["res"] == int(v) and resto(d, ("res", "n")) == resto(a, ("res", "n")), rot
        elif act == "fase":
            assert d["fase"] == int(v) and resto(d, ("fase", "n")) == resto(a, ("fase", "n")), rot
        elif act == "clube":
            assert (i in a["clubes"]) != (i in d["clubes"]) and d["jogo"] is None, rot
            assert resto(d, ("clubes", "n", "jogo")) == resto(a, ("clubes", "n", "jogo")), rot
        elif act == "como":
            assert d["como"] == v and resto(d, ("como", "n")) == resto(a, ("como", "n")), rot
        elif act == "filtros":
            assert d["dialogo"] is True and resto(d, ("dialogo",)) == resto(a, ("dialogo",)), rot
        elif act == "f-fechar":
            assert d["dialogo"] is False and resto(d, ("dialogo",)) == resto(a, ("dialogo",)), rot
        elif act in ("limpar", "f-limpar"):
            assert (d["fase"], d["clubes"], d["rodadas"], d["estadios"], d["dias"], d["horas"], d["res"], d["jogo"], d["n"]) == (0, [], [], [], [], [], 0, None, 72), rot
            assert d["dialogo"] == a["dialogo"], rot
        elif act == "jogo":
            assert (d["jogo"] == i) != (a["jogo"] == i) and (d["n"] == 1 if d["jogo"] else True), rot
        elif act in ("metrica", "rank", "ord"):
            assert resto(d, ()) == resto(a, ()), rot
        else:
            assert act is None and a["dialogo"] is True and d["dialogo"] is False and resto(d, ("dialogo",)) == resto(a, ("dialogo",)), rot
        assert d["n"] == len(ids_do_recorte(tab, filtros_do_estado(d))), rot
    assert set(vistos) == (ACOES_DA_TELA - {"ajuda"}) | {None}
    assert vistos[None] == 1 and vistos["f-rod"] == 24 and vistos["f-dia"] == 12 and vistos["f-hora"] == 24 and vistos["f-est"] == 32 and vistos["f-res"] == 3


@precisa_dados
@precisa_node
def test_cascata_fecha_em_cada_recorte(saida):
    for c in saida["cascata"]:
        it = {i["n"]: i for i in c["itens"]}
        assert it["Renda bruta"]["v"] + it["Despesas"]["v"] == it["Renda líquida"]["v"], c["nome"]
        assert it["Renda líquida"]["v"] + it["Deduções"]["v"] == it["Líquido a receber"]["v"], c["nome"]
        assert it["Despesas"]["de"] == it["Renda bruta"]["ate"] and it["Deduções"]["de"] == it["Renda líquida"]["ate"]
    todos = {i["n"]: i["v"] for i in next(c for c in saida["cascata"] if c["nome"] == "todos")["itens"]}
    assert todos["Renda bruta"] == 4473000380 and todos["Despesas"] == -2040474714 and todos["Renda líquida"] == 2432525666 and todos["Deduções"] == -15353540 and todos["Líquido a receber"] == 2432525666 - 15353540
    assert next(c for c in saida["cascata"] if c["nome"] == "jogo1")["itens"][2]["v"] == -1350380


@precisa_dados
@precisa_node
def test_formatos_de_valor_e_tooltip(saida):
    assert saida["mi"] == [[0, "0,00", "R$ 0,00"], [99, "0,99", "R$ 0,99"], [100, "1,00", "R$ 1,00"], [99999, "999,99", "R$ 999,99"], [100000, "1,0 mil", "R$ 1.000,00"], [123456, "1,2 mil", "R$ 1.234,56"], [9995000, "100 mil", "R$ 99.950,00"], [9994900, "99,9 mil", "R$ 99.949,00"],
                           [10000000, "100 mil", "R$ 100.000,00"], [79012345, "790 mil", "R$ 790.123,45"], [99999999, "1,00 mi", "R$ 999.999,99"], [100000000, "1,00 mi", "R$ 1.000.000,00"], [4473000380, "44,73 mi", "R$ 44.730.003,80"], [-5000, "−50,00", "−R$ 50,00"], [-1350380, "−13,5 mil", "−R$ 13.503,80"]]
    assert saida["tipHtml"]["completo"] == '<b>Título</b><div class="tv"><div class="li"><span>A</span><em>1</em></div><div><span>B</span><em>2</em></div></div><span>Parágrafo</span><small>Nota</small>'
    assert "<b>x</b>" not in saida["tipHtml"]["escapado"] and "&lt;b&gt;x&lt;/b&gt; &amp;" in saida["tipHtml"]["escapado"]


# ---------- o que a tela escreve bate com os dados (valores exibidos, não só somas) ----------

def pt(texto):
    """Lê um número escrito como a tela escreve (1.234,56 | −13,5 mil | 44,73 mi | 24,7%) e devolve (valor, tolerância de arredondamento)."""
    t = texto.strip().replace("−", "-").replace("R$", "").replace("%", "").strip()
    mult = 1
    if t.endswith(" mi"):
        mult, t = 1_000_000, t[:-3]
    elif t.endswith(" mil"):
        mult, t = 1_000, t[:-4]
    casas = len(t.split(",")[1]) if "," in t else 0
    valor = float(t.replace(".", "").replace(",", "."))
    return valor * mult, 0.5 * 10 ** (-casas) * mult + 1e-9


def confere(texto, certo):
    valor, tol = pt(texto)
    assert abs(valor - certo) <= tol, (texto, certo)


def linhas_legenda(h):
    return re.findall(r'<div class="l(?: zero)?" style="--i:\d+;--k:#[0-9a-f]+"[^>]*><span><i></i><u>([^<]*)</u></span><span class="pc">([^<]*)</span><span>([^<]*)</span><span>([^<]*)</span><span>([^<]*)</span></div>', h)


def linhas_despesa(h):
    return re.findall(r'<div class="g" style="--i:\d+;--w:[\d.]+%"[^>]*><span>([^<]*)</span><div class="tr"><u></u></div><em>([^<]*)<b>([^<]*)</b></em></div>', h)


def linhas_ranking(h):
    return re.findall(r'<button class="r[^"]*" style="--i:\d+;--w:[\d.]+%" data-act="clube" data-id="(\d+)"[^>]*><i>(\d*)</i>.*?<b>([^<]*)</b><div class="tr"><u></u></div><em>([^<]*)</em></button>', h)


def linhas_jogos(h):
    return re.findall(r'<button class="jr[^"]*" style="--i:\d+" data-act="jogo" data-id="(\d+)"[^>]*><span class="d">([^<]*)</span><span class="t">(?:<span class="sg"[^>]*>[^<]*</span>|<img[^>]*>)?([^<]*)</span><span class="pl">(\d+) × (\d+)</span><span class="t v">(?:<span class="sg"[^>]*>[^<]*</span>|<img[^>]*>)?([^<]*)</span><span class="n">([^<]*)</span><span class="n rb">([^<]*)</span><span class="n (?:lq|neg)">([^<]*)</span></button>', h)


def linhas_kpi(h):
    return re.findall(r'<h4>([^<]*)</h4><div class="v">(?:<em>([^<]*)</em>)?<span data-i="\d">([^<]*)</span>(?:<em class="u">([^<]*)</em>)?</div><small>([^<]*)</small>', h)


@precisa_dados
@precisa_node
def test_valores_escritos_nos_paineis_batem_com_as_tabelas(saida, tab, meta, montagem):
    assert len(saida["render"]) == 7
    nome_clube = {c["id"]: c["curto"] for c in montagem["fin"]["clubes"]}
    for r in saida["render"]:
        f = r["filtros"]
        ids = ids_do_recorte(tab, f)
        e = esperado(tab, meta, ids)
        n = e["n"]
        assert n > 0, r["nome"]
        # quadros de cima
        k = linhas_kpi(r["kpis"])
        assert [x[0] for x in k] == ["Público total", "Público médio", "Renda bruta", "Despesas", "Renda líquida", "Ticket médio", "Torcida visitante"], r["nome"]
        assert k[0][2] == milhar(e["pu"]) and k[0][4] == f"{n} jogo{'' if n == 1 else 's'}"
        confere(k[1][2], e["pu"] / n)
        for pos, valor in ((2, e["rb"] / 100), (3, e["ds"] / 100), (4, e["rl"] / 100)):
            numero, tol = pt(k[pos][2] + (" " + k[pos][3] if k[pos][3] else ""))
            assert abs(numero - abs(valor)) <= tol, (r["nome"], pos)
            assert k[pos][1] == ("−R$" if valor < 0 else "R$")
        numero, tol = pt(k[5][2])
        assert abs(numero - e["rb"] / 100 / e["pg"]) <= tol and k[5][4] == f"{milhar(e['pg'])} ingressos pagos"
        assert k[6][2] == milhar(e["vi"]) and k[6][4] == f"{pct_texto(e['vi'], e['pu'])} do público"
        assert k[3][4] == f"{pct_texto(e['ds'], e['rb'])} da renda bruta"
        # quem paga o quê
        arr_chave = "cr" if f.get("metrica") == "ren" else "ci"
        total = sum(e[arr_chave])
        leg = linhas_legenda(r["p1"])
        assert [x[0] for x in leg] == meta["cat"]
        for i, (nm, pcn, ing, ren, prc) in enumerate(leg):
            assert ing == milhar(e["ci"][i])
            if e[arr_chave][i]:
                confere(pcn, 100 * e[arr_chave][i] / total)
            else:
                assert pcn == "0,0%"
            if e["cr"][i]:
                confere(ren, e["cr"][i] / 100)
            else:
                assert ren == "—"
            if e["cr"][i] and e["ci"][i]:
                confere(prc, e["cr"][i] / e["ci"][i] / 100)
            else:
                assert prc == "—"
        # para onde vai a despesa
        desp = linhas_despesa(r["p3"])
        assert [x[0] for x in desp] == meta["grp"]
        for i, (nm, valor, parte) in enumerate(desp):
            confere(valor, e["gd"][i] / 100)
            confere(parte, 100 * e["gd"][i] / e["ds"])
        # ranking
        rk = linhas_ranking(r["p4"])
        por_clube = esperado_por_clube(tab, meta, f)
        rank = f.get("rank", "pub")
        valor_de = {"pub": lambda s: s["pu"] / s["n"] if s["n"] else 0, "ren": lambda s: s["rb"] / 100, "liq": lambda s: s["rl"] / 100, "vis": lambda s: s["vi"]}[rank]
        assert len(rk) == 16
        for pos, (idc, ordem, nm, texto) in enumerate(rk):
            s = por_clube[idc]
            assert nm == nome_clube[idc]
            if s["n"]:
                assert ordem == str(pos + 1)
                confere(texto, valor_de(s))
            else:
                assert (ordem, texto) == ("", "—")
        com_jogos = [valor_de(por_clube[x[0]]) for x in rk if por_clube[x[0]]["n"]]
        assert com_jogos == sorted(com_jogos, reverse=True)
        # lista de jogos
        lista = linhas_jogos(r["p5"])
        assert len(lista) == len(ids_do_recorte(tab, f, ignorar=("jogo",)))
        for idj, data, mand, gm, gv, vis, publico, renda, liq in lista:
            p = tab["partidas"][idj]
            assert data == f"{p['data_jogo'][8:10]}/{p['data_jogo'][5:7]}" and (int(gm), int(gv)) == (int(p["gols_mandante"]), int(p["gols_visitante"]))
            assert publico == milhar(int(p["publico_boletim"]))
            confere(renda, float(p["renda_bruta"]))
            confere(liq, float(p["renda_liquida"]))
            assert liq.startswith("−") == (Decimal(p["renda_liquida"]) < 0)
            assert mand == nome_clube[p["id_clube_mandante"]] and vis == nome_clube[p["id_clube_visitante"]]


@precisa_dados
@precisa_node
def test_rotulos_da_cascata_e_tooltips_trazem_os_valores_do_recorte(saida, tab, meta):
    for r in saida["render"]:
        e = esperado(tab, meta, ids_do_recorte(tab, r["filtros"]))
        textos = re.findall(r'<text x="[\d.]+" y="[-\d.]+" text-anchor="middle">([^<]*)</text><text class="m"', r["p2"])
        assert len(textos) == 5
        for texto, valor in zip(textos, (e["rb"], -e["ds"], e["rl"], -e["dd"], e["lq"])):
            confere(texto.replace("R$ ", ""), valor / 100)
            assert texto.startswith("−") == (valor < 0)
        tips = re.findall(r'<rect class="br[^"]*"[^>]*data-tip="([^"]*)"', r["p2"])
        assert len(tips) == 5 and all("Valor" in t for t in tips)


# ---------- barra de navegação ----------

@precisa_dados
def test_o_duelo_carrega_os_escudos_antes_das_telas_que_os_usam(montagem):
    app = montagem["app"]
    fonte = app.index("window.PA.clubes=D.clubes")
    leituras = [m.start() for m in re.finditer(r"window\.PA\.clubes\.forEach", app)]
    assert len(leituras) >= 4 and all(fonte < i for i in leituras), "uma tela leria os escudos antes de o Duelo publicá-los e mostraria só a letra do clube"
    assert app.index('id="mod-vs"') < min(app.index(f'id="mod-{k}"') for k in ("vg", "clas", "gl", "ds", "jg", "fin"))


@precisa_dados
def test_nenhuma_tela_usa_nome_de_classe_que_a_barra_ja_usa():
    shell = (PROTO / "app" / "shell.html").read_text(encoding="utf-8")
    da_barra = set(re.findall(r"#pa \.([a-z][\w-]*)", shell))
    assert {"barra", "marca", "nav", "selo", "mods", "mod"} <= da_barra
    for pasta in ("visao_geral", "versus", "classificacao", "gols", "disciplina", "jogos", "financeiro", "conferencia"):
        fonte = (PROTO / pasta / "fragmento.html").read_text(encoding="utf-8")
        usadas = {c for lista in re.findall(r'class=\\?"([^"\\]*)', fonte) for c in lista.split()}
        usadas |= set(re.findall(r"classList\.(?:add|toggle)\('([\w-]+)'", fonte))
        assert not (usadas & da_barra), (pasta, usadas & da_barra)


def test_nome_de_cada_botao_da_barra_fica_em_uma_linha_e_a_barra_nao_encolhe_os_botoes():
    shell = (PROTO / "app" / "shell.html").read_text(encoding="utf-8")
    assert re.search(r"#pa \.nav button\{[^}]*white-space:nowrap", shell) and re.search(r"#pa \.nav\{[^}]*flex:none", shell) and re.search(r"#pa \.selo\{[^}]*flex:none", shell)


@precisa_dados
@precisa_node
@pytest.mark.parametrize("hash_", ["", "#vs", "#clas", "#gl", "#ds", "#jg", "#fin", "#conf", "#inexistente"])
def test_barra_alterna_as_oito_telas_marca_a_atual_e_o_selo_leva_a_conferencia(montagem, hash_):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_shell.js"), str(montagem["pasta"] / "app.html"), hash_], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 0, proc.stderr[-800:]
    s = json.loads(proc.stdout)
    assert s["flag"] is True and s["temIr"] == "function"
    chaves = ["vg", "vs", "clas", "gl", "ds", "jg", "fin", "conf"]
    assert chaves == [t[0] for t in montagem["m"].TELAS]
    n = len(chaves)
    ix = {k: i for i, k in enumerate(chaves)}
    quem = lambda e: tuple(e[k] for k in chaves)
    botao = lambda e: tuple(e["b" + k] for k in chaves)
    so = lambda k: tuple(i == ix[k] for i in range(n))
    corrente = lambda k: [("page" if i == ix[k] else None) for i in range(n)]
    esperado_inicio = {"": "vg", "#vs": "vs", "#clas": "clas", "#gl": "gl", "#ds": "ds", "#jg": "jg", "#fin": "fin", "#conf": "conf", "#inexistente": "vg"}[hash_]
    assert quem(s["inicio"]) == so(esperado_inicio) and botao(s["inicio"]) == so(esperado_inicio) and s["inicio"]["corrente"] == corrente(esperado_inicio)
    base = s["inicio"]["entrou"]
    assert quem(s["aposFin"]) == so("fin") and botao(s["aposFin"]) == so("fin") and s["aposFin"]["corrente"] == corrente("fin") and s["aposFin"]["entrou"] == base + 1
    assert quem(s["aposVs"]) == so("vs") and botao(s["aposVs"]) == so("vs") and s["aposVs"]["corrente"] == corrente("vs")
    assert s["aposInvalido"] == s["aposVs"]
    assert quem(s["aposIrFin"]) == so("fin") and s["aposIrFin"]["entrou"] == s["aposFin"]["entrou"] + 1
    assert quem(s["aposClas"]) == so("clas") and botao(s["aposClas"]) == so("clas") and s["aposClas"]["corrente"] == corrente("clas") and s["aposClas"]["entrou"] == s["aposIrFin"]["entrou"] + 1
    assert quem(s["aposConf"]) == so("conf") and botao(s["aposConf"]) == so("conf") and s["aposConf"]["corrente"] == corrente("conf") and s["aposConf"]["entrou"] == s["aposClas"]["entrou"] + 1
    assert quem(s["aposGl"]) == so("gl") and botao(s["aposGl"]) == so("gl") and s["aposGl"]["corrente"] == corrente("gl") and s["aposGl"]["entrou"] == s["aposConf"]["entrou"] + 1
    assert quem(s["aposDs"]) == so("ds") and botao(s["aposDs"]) == so("ds") and s["aposDs"]["corrente"] == corrente("ds") and s["aposDs"]["entrou"] == s["aposGl"]["entrou"] + 1
    assert quem(s["aposJg"]) == so("jg") and botao(s["aposJg"]) == so("jg") and s["aposJg"]["corrente"] == corrente("jg") and s["aposJg"]["entrou"] == s["aposDs"]["entrou"] + 1
    assert quem(s["aposVg"]) == so("vg") and botao(s["aposVg"]) == so("vg") and s["aposVg"]["corrente"] == corrente("vg") and s["aposVg"]["entrou"] == s["aposJg"]["entrou"] + 1
    assert quem(s["aposSelo"]) == so("conf") and botao(s["aposSelo"]) == so("conf")  # o selo leva a conferencia e acende o botao dela
    assert s["aposSelo"]["entrou"] == s["aposVg"]["entrou"] + 1
    assert quem(s["aposIrClas"]) == so("clas") and s["aposIrClas"]["entrou"] == s["aposSelo"]["entrou"] + 1
    assert quem(s["aposIrVg"]) == so("vg") and s["aposIrVg"]["entrou"] == s["aposIrClas"]["entrou"] + 1


@precisa_dados
@precisa_node
def test_cada_botao_da_barra_tem_dica_que_demora_um_instante_e_some_ao_sair_ao_perder_o_foco_ou_ao_clicar(montagem):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_shell.js"), str(montagem["pasta"] / "app.html"), ""], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 0, proc.stderr[-800:]
    s = json.loads(proc.stdout)
    chaves = ["vg", "vs", "clas", "gl", "ds", "jg", "fin", "conf"]
    shell = (PROTO / "app" / "shell.html").read_text(encoding="utf-8")
    rotulos = dict(re.findall(r'<button data-mod="(\w+)"[^>]*><span>([^<]*)</span></button>', shell))
    assert list(rotulos) == chaves == list(s["dicas"])
    internos = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")
    textos = {}
    for k in chaves:
        d = s["dicas"][k]
        achado = re.fullmatch(r"<b>([^<]+)</b>(.+)", d["html"])
        assert achado, (k, d["html"])
        titulo, frase = achado.groups()
        textos[k] = (titulo, frase)
        assert titulo.startswith(rotulos[k]) and frase.endswith(".") and len(frase) > 40 and not any(i in frase for i in internos), k
        assert (d["antesDoAtraso"], d["ligada"], d["aposSair"]) == (False, True, False), k
        assert d["top"] == "84px", k
    assert len({t for t, _ in textos.values()}) == 8 and len({f for _, f in textos.values()}) == 8
    assert (s["dicas"]["vg"]["left"], s["dicas"]["vs"]["left"], s["dicas"]["conf"]["left"]) == ("12px", "200px", "1588px")
    assert s["trocaRapida"] == s["dicas"]["vs"]["html"] and s["fundo"] is False
    assert s["foco"] == {"ligada": True, "html": s["dicas"]["jg"]["html"]} and s["focoFora"] is False
    assert s["aposClique"] is False and s["cliqueAntesDoAtraso"] is False



def test_botao_entendi_da_ajuda_de_cada_tela_e_o_pronto_do_publico_e_renda_tem_dica():
    for pasta in ("visao_geral", "versus", "classificacao", "gols", "disciplina", "jogos", "financeiro", "conferencia"):
        fonte = (PROTO / pasta / "fragmento.html").read_text(encoding="utf-8")
        assert len(re.findall(r"data-act=\"ajuda-fechar\"'\+tp\('Fechar','[^']+'\)\+'>Entendi", fonte)) == 1, pasta
    financeiro = (PROTO / "financeiro" / "fragmento.html").read_text(encoding="utf-8")
    assert len(re.findall(r"data-act=\"f-fechar\"'\+tp\('Pronto','[^']+'\)\+'><span>Pronto</span>", financeiro)) == 1


def test_ajuda_do_duelo_nao_traz_o_botao_de_medir_quadros_por_segundo_mas_a_tecla_f_continua():
    duelo = (PROTO / "versus" / "fragmento.html").read_text(encoding="utf-8")
    assert "Medir desempenho" not in duelo and 'data-act="fps"' not in duelo and "a==='fps'" not in duelo
    assert "if(k==='f'&&!ev.ctrlKey&&!ev.metaKey){alternarFps();return}" in duelo


def test_botao_versus_da_escolha_do_duelo_tem_dica():
    duelo = (PROTO / "versus" / "fragmento.html").read_text(encoding="utf-8")
    assert len(re.findall(r"<button class=\"lutar\" data-act=\"lutar\"'\+tp\('Abrir o duelo','[^']+'\)\+'>VERSUS</button>", duelo)) == 1
