import importlib.util
import json
import math
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
from referencia_nomes import curto_das_pessoas  # noqa: E402

PROC = RAIZ / "data" / "processed"
PROTO = RAIZ / "prototype"
precisa_dados = pytest.mark.skipif(not all((PROC / n).exists() for n in ("fato_classificacao_oficial.csv", "fato_partida.csv", "fato_evento.csv", "resultado_regra.csv", "ref_indicadores.csv")), reason="rode scripts/04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
INTERNOS = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")
FS = {"t": "Todas as fases", "p": "1ª fase", "m": "Mata-mata"}
FASE = {1: "1ª fase", 2: "Quartas de final", 3: "Semifinal", 4: "Final"}
COD_FASE = {"PRIMEIRA FASE": 1, "QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}


def carregar(nome, arq):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sem_tags(t):
    return re.sub(r"<[^>]*>", "", t)


def decod(t):
    return t.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def fmt(n, c=0):
    v = Decimal(n).quantize(Decimal(1).scaleb(-c), rounding=ROUND_HALF_UP)
    return f"{v:,.{c}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def plural(n, u, p):
    return f"{fmt(n)} " + (u if n == 1 else p)


def lista(a):
    return a[0] if len(a) == 1 else ", ".join(a[:-1]) + " e " + a[-1]


def data_br(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}"


def data_longa(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}/{a}"


def reais(cent):
    return "R$ " + fmt(Decimal(cent) / 100, 2)


def pct(a, b):
    return fmt(Decimal(100 * a) / b, 1) + "%"


# ---------- referência recalculada aqui, direto das tabelas tratadas ----------

@pytest.fixture(scope="module")
def ref():
    fases = {f["id_fase"]: COD_FASE[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = ler_csv(PROC / "fato_partida.csv")
    eventos = ler_csv(PROC / "fato_evento.csv")
    cartoes = defaultdict(lambda: [0, 0])
    for e in eventos:
        c = cartoes[e["id_partida"]]
        if e["tipo_evento"] == "amarelo":
            c[0] += 1
        elif e["tipo_evento"] == "segundo_amarelo":
            c[0] -= 1
            c[1] += 1
        elif e["tipo_evento"] == "vermelho":
            c[1] += 1
    jogos = []
    for p in sorted(partidas, key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"]))):
        jogos.append({"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "m": int(p["id_clube_mandante"]), "v": int(p["id_clube_visitante"]), "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]),
                      "pu": int(p["publico_boletim"]), "pg": int(p["publico_pagante"]), "rb": int((Decimal(p["renda_bruta"]) * 100).to_integral_value()), "am": cartoes[p["id_partida"]][0], "vm": cartoes[p["id_partida"]][1], "_id": p["id_partida"]})
    return {"jogos": jogos, "eventos": eventos, "fases": fases, "partidas": partidas, "oficial": ler_csv(PROC / "fato_classificacao_oficial.csv"), "regras": {r["codigo"]: r for r in ler_csv(PROC / "resultado_regra.csv")},
            "clubes": {int(c["id_clube"]): c for c in ler_csv(PROC / "dim_clube.csv")}}


def recorte(ref, f):
    return [j for j in ref["jogos"] if f == "t" or (f == "p" and j["f"] == 1) or (f == "m" and j["f"] > 1)]


def resumo(js):
    n = len(js)
    g = sum(j["gm"] + j["gv"] for j in js)
    pu, pg, rb = sum(j["pu"] for j in js), sum(j["pg"] for j in js), sum(j["rb"] for j in js)
    am, vm = sum(j["am"] for j in js), sum(j["vm"] for j in js)
    return {"n": n, "g": g, "pu": pu, "pg": pg, "rb": rb, "am": am, "vm": vm, "a": sum(1 for j in js if j["gm"] > j["gv"]), "e": sum(1 for j in js if j["gm"] == j["gv"]), "b": sum(1 for j in js if j["gm"] < j["gv"]),
            "gpj": Decimal(g) / n, "pm": Decimal(pu) / n, "tk": Decimal(rb) / pg, "cpj": Decimal(am + vm) / n}


def artilheiros(ref):
    curto = curto_das_pessoas(ref["eventos"]).__getitem__
    fase = {p["id_partida"]: ref["fases"][p["id_fase"]] for p in ref["partidas"]}
    por = defaultdict(lambda: {"g1": 0, "g2": 0, "c": Counter()})
    for e in ref["eventos"]:
        if e["tipo_evento"] in ("gol", "gol_penalti", "gol_falta"):
            a = por[e["pessoa"]]
            a["g1" if fase[e["id_partida"]] == 1 else "g2"] += 1
            a["c"][int(e["id_clube"])] += 1

    return [{"p": p, "a": curto(p), "c": a["c"].most_common(1)[0][0], "g1": a["g1"], "g2": a["g2"]} for p, a in por.items()]


def gols_no_recorte(a, f):
    return a["g1"] + a["g2"] if f == "t" else a["g1"] if f == "p" else a["g2"]


@pytest.fixture(scope="module")
def montagem(tmp_path_factory):
    m = carregar("montar_app13_vg", "13_montar_app.py")
    versus = m.modulo_versus().montar_dados()
    clas, conf = m.montar_dados_clas(versus), m.montar_dados_conf()
    vg = m.montar_dados_vg(versus, clas, conf)
    frag = (PROTO / "visao_geral" / "fragmento.html").read_text(encoding="utf-8").replace("__DADOS__", m.dados_json(vg))
    pasta = tmp_path_factory.mktemp("vg")
    (pasta / "vg.html").write_text(m.pagina("t", m.logos_js(versus) + frag), encoding="utf-8")
    return {"m": m, "versus": versus, "clas": clas, "conf": conf, "vg": vg, "frag": frag, "pasta": pasta}


@pytest.fixture(scope="module")
def curto(montagem):
    return {int(c["id"]): c["curto"] for c in montagem["vg"]["clubes"]}


def rodar(montagem, *extra):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_vg.js"), str(montagem["pasta"] / "vg.html"), *extra], capture_output=True, text=True, encoding="utf-8", timeout=600)
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
    js = montagem["vg"]["jogos"]
    esperado = [{k: v for k, v in j.items() if not k.startswith("_")} for j in ref["jogos"]]
    assert js == esperado and len(js) == 72
    assert [j["d"] for j in js] == sorted(j["d"] for j in js)


@precisa_dados
def test_artilheiros_do_pacote_sao_os_dos_eventos_sem_gol_contra(montagem, ref):
    art = montagem["vg"]["art"]
    esperado = artilheiros(ref)
    chave = lambda x: (-(x["g1"] + x["g2"]), x["p"])
    assert art == sorted(esperado, key=chave) and len(art) == 111
    total = sum(a["g1"] + a["g2"] for a in art)
    assert total == 166 and total + sum(1 for e in ref["eventos"] if e["tipo_evento"] == "gol_contra") == sum(j["gm"] + j["gv"] for j in ref["jogos"])
    assert all(a["a"] and a["p"] for a in art)


@precisa_dados
def test_campeao_e_conferencia_do_pacote_vem_da_tabela_oficial_e_das_regras(montagem, ref):
    meta = montagem["vg"]["meta"]
    final = {int(o["posicao"]): int(o["id_clube"]) for o in ref["oficial"] if o["fase"] == "FINAL"}
    assert (meta["camp"], meta["vice"]) == (final[1], final[2])
    jogos_final = [j for j in ref["jogos"] if j["f"] == 4]
    pts = Counter()
    for j in jogos_final:
        pts[j["m"]] += 3 if j["gm"] > j["gv"] else 1 if j["gm"] == j["gv"] else 0
        pts[j["v"]] += 3 if j["gv"] > j["gm"] else 1 if j["gm"] == j["gv"] else 0
    assert meta["fpts"] == [pts[meta["camp"]], pts[meta["vice"]]]
    por_resultado = Counter(r["resultado"] for r in ref["regras"].values())
    assert (meta["regras"], meta["ok"], meta["expl"], meta["aber"], meta["info"]) == (len(ref["regras"]), por_resultado["ok"], por_resultado["explicada"], por_resultado["aberta"], por_resultado["info"]) == (45, 35, 7, 2, 1)
    a22, a19 = ref["regras"]["A22"], ref["regras"]["A19"]
    assert meta["placar"] == [int(a22["verificados"]) - int(a22["ocorrencias"]), int(a22["verificados"])] == [72, 72]
    assert meta["classif"] == [int(a19["verificados"]) - int(a19["ocorrencias"]), int(a19["verificados"])] == [16, 16]
    assert [m["n"] for m in montagem["vg"]["mm"]] == [j["n"] for j in montagem["clas"]["mm"]] and len(montagem["vg"]["mm"]) == 8


@precisa_dados
def test_totais_do_pacote_batem_com_o_gabarito_geral_e_por_fase(montagem, ref):
    gab = [l for l in ler_csv(PROC / "ref_indicadores.csv")]
    geral = {l["id_indicador"]: Decimal(l["valor"]) for l in gab if l["escopo"] == "geral"}
    por_fase = {(l["id_indicador"], l["chave"]): Decimal(l["valor"]) for l in gab if l["escopo"] == "fase"}
    js = montagem["vg"]["jogos"]
    r = resumo(js)
    assert (r["n"], r["g"], r["pu"], r["pg"], r["am"], r["vm"]) == (geral["I01"], geral["I02"], geral["I10"], geral["I14"], geral["I20"], geral["I21"])
    assert (r["a"], r["e"], r["b"]) == (geral["I04"], geral["I05"], geral["I06"]) and Decimal(r["rb"]) / 100 == geral["I16"]
    assert round(r["gpj"], 4) == round(geral["I03"], 4) and round(r["pm"], 4) == round(geral["I11"], 4) and round(r["cpj"], 4) == round(geral["I22"], 4)
    assert (max(j["pu"] for j in js), min(j["pu"] for j in js)) == (geral["I12"], geral["I13"])
    assert round(Decimal(r["rb"]) / 100 / r["pg"], 2) == geral["I18"]
    assert sum(1 for j in js if j["gm"] + j["gv"] == 0) == geral["I26"]
    nomes = {1: "PRIMEIRA FASE", 2: "QUARTAS DE FINAL", 3: "SEMIFINAL", 4: "FINAL"}
    for f, nome in nomes.items():
        x = resumo([j for j in js if j["f"] == f])
        assert (x["n"], x["g"], x["pu"]) == (por_fase[("I01", nome)], por_fase[("I02", nome)], por_fase[("I10", nome)])
        assert Decimal(x["rb"]) / 100 == por_fase[("I16", nome)] and round(x["cpj"], 4) == round(por_fase[("I22", nome)], 4)


@precisa_dados
def test_clubes_do_pacote_sao_os_da_classificacao(montagem):
    assert montagem["vg"]["clubes"] == montagem["clas"]["clubes"] and len(montagem["vg"]["clubes"]) == 16
    for c in montagem["vg"]["clubes"]:
        for k in ("nome", "curto", "sigla"):
            for ruim in INTERNOS:
                assert ruim not in c[k]


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
    return montagem["m"].montar_dados_vg(montagem["versus"], montagem["clas"], montagem["conf"])


@precisa_dados
def test_o_montador_para_se_um_placar_deixar_de_bater_com_o_gabarito(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "7")
        l["gols_mandante"] = str(int(l["gols_mandante"]) + 1)

    adulterar(monkeypatch, montagem["m"], "fato_partida.csv", mexer)
    with pytest.raises(SystemExit, match="gabarito"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_o_publico_ou_a_renda_nao_baterem(montagem, monkeypatch):
    def publico(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "9")
        l["publico_boletim"] = str(int(l["publico_boletim"]) + 1)

    adulterar(monkeypatch, montagem["m"], "fato_partida.csv", publico)
    with pytest.raises(SystemExit, match="público"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_a_renda_bruta_de_uma_fase_nao_bater(montagem, monkeypatch):
    def renda(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "70")
        l["renda_bruta"] = str(Decimal(l["renda_bruta"]) + 1)

    adulterar(monkeypatch, montagem["m"], "fato_partida.csv", renda)
    with pytest.raises(SystemExit, match="renda bruta"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_gol_de_atleta_sumir_dos_eventos(montagem, monkeypatch):
    def tirar(linhas):
        i = next(k for k, x in enumerate(linhas) if x["tipo_evento"] == "gol")
        del linhas[i]

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", tirar)
    with pytest.raises(SystemExit):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_cartao_sumir_dos_eventos(montagem, monkeypatch):
    def tirar(linhas):
        i = next(k for k, x in enumerate(linhas) if x["tipo_evento"] == "amarelo")
        del linhas[i]

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", tirar)
    with pytest.raises(SystemExit, match="amarelos"):
        refazer(montagem)


# ---------- montagem da tela ----------

@precisa_dados
def test_fragmento_nao_deixa_marca_sobrando_e_so_age_quando_visivel(montagem):
    frag = montagem["frag"]
    assert not re.search(r"__[A-Z_]+__", frag)
    src = (PROTO / "visao_geral" / "fragmento.html").read_text(encoding="utf-8")
    assert src.count("__DADOS__") == 1 and "height:100%;min-height:320px" in src and "if(!raiz.offsetParent)return;" in src
    assert "window.PA.mods.vg={entrar:entrar}" in src and 'id="vgx"' in src
    for ruim in INTERNOS:
        assert ruim not in src, ruim
    assert "http://" not in src and "https://" not in src and "@import" not in src and "<link" not in src


@precisa_dados
def test_textos_da_tela_sao_todos_de_pelo_menos_16_pixels():
    src = (PROTO / "visao_geral" / "fragmento.html").read_text(encoding="utf-8")
    tamanhos = [int(x) for x in re.findall(r"font-size:(\d+)px", src)] + [int(x) for x in re.findall(r"font:[^;{}]*?(\d+)px", src)]
    assert tamanhos and min(tamanhos) >= 16, sorted(set(tamanhos))


@precisa_dados
def test_desenhos_nao_roubam_o_clique_nem_a_dica_e_o_texto_nao_tem_numero_fixo_de_jogos_ou_gols():
    src = (PROTO / "visao_geral" / "fragmento.html").read_text(encoding="utf-8")
    assert re.search(r"#vgx \.tip\{[^}]*pointer-events:none", src)
    rola = re.search(r"#vgx \.rola\{([^}]*)\}", src).group(1)
    assert "overflow-y:auto" in rola and "scrollbar-width:thin" in rola, "a lista da artilharia precisa de barra de rolagem visível"
    assert re.search(r"padding-right:(1[2-9]|[2-9]\d)px", rola), "o conteúdo da lista precisa de folga em relação à barra de rolagem"
    assert re.search(r"#vgx \.rw::after\{[^}]*pointer-events:none", src), "o esmaecido do fim da lista não pode tampar o clique"
    assert re.search(r"#vgx \.bars text\{[^}]*pointer-events:none", src), "os números sobre as barras não podem roubar a dica da barra"
    assert re.search(r"#vgx \.bars \.med\{[^}]*pointer-events:none", src) and re.search(r"#vgx \.bars \.base\{[^}]*pointer-events:none", src), "as linhas do gráfico não podem roubar a dica"
    js = src[src.index("<script>"):]
    for fixo in ("72 jogos", "168 gols", "64 jogos", "64 na", "8 rodadas", "4 quartas"):
        assert fixo not in js, fixo


@precisa_dados
def test_pagina_do_app_leva_a_tela_como_a_primeira_e_abre_nela():
    m = carregar("montar_app13_vgpg", "13_montar_app.py")
    dados = m.montar_todos_os_dados()
    frag = m.montar_fragmentos(dados)
    app = frag["app"]
    assert not re.search(r"__[A-Z_]+__", app)
    assert app.count('id="vgx"') == 1 and app.count('<section class="mod on" id="mod-vg">') == 1 and app.count('<section class="mod" id="mod-vs">') == 1
    assert m.dados_json(dados["vg"]) in app and frag["vg"] in app
    nav = re.search(r"<nav[^>]*>(.*?)</nav>", app, re.S).group(1)
    assert re.findall(r'data-mod="(\w+)"', nav) == [t[0] for t in m.TELAS] and '<button data-mod="vg" class="on" aria-current="page"><span>Visão geral</span></button>' in nav
    assert "if(!mods[h])h='vg';" in app


# ---------- comportamento (módulo simulado em Node) ----------

def kpis_da(h):
    achados = re.findall(r'<div class="kpi" style="left:(\d+)px;top:(\d+)px;--kc:(#[0-9a-f]{6})" data-tip="([^"]*)"><h4>([^<]*)</h4><div class="v">([^<]*(?:<em>[^<]*</em>)?)</div><small>([^<]*)</small></div>', h)
    return [{"x": int(x), "y": int(y), "cor": cor, "tip": decod(tip), "r": decod(r), "v": decod(sem_tags(v)), "s": decod(s)} for x, y, cor, tip, r, v, s in achados]


def barras_da(h):
    padrao = re.compile(r'<g data-tip="([^"]*)"><rect class="slot" x="([\d.]+)" y="0" width="([\d.]+)" height="([\d.]+)"/><rect class="(bq|bm)" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/></g>'
                        r'<text class="vl" x="([\d.]+)" y="([\d.-]+)" text-anchor="middle">([^<]*)</text><text x="[\d.]+" y="[\d.]+" text-anchor="middle">([^<]*)</text>')
    saida = []
    for tip, sx, sw, sh, cls, x, y, w, hh, tx, ty, val, rot in padrao.findall(h):
        saida.append({"tip": decod(tip), "slot": (float(sx), float(sw)), "cls": cls, "x": float(x), "y": float(y), "w": float(w), "h": float(hh), "val": val, "rot": rot})
    med = re.search(r'<line class="med" x1="0" y1="([\d.]+)" x2="716" y2="([\d.]+)"/>', h)
    legenda = re.search(r'<text x="0" y="[\d.]+">([^<]*)</text></svg>', h).group(1)
    return saida, float(med.group(1)), decod(legenda)


def artilheiros_da(h):
    padrao = re.compile(r'<div class="ar" data-tip="([^"]*)"><span class="ps">(\d+)</span><span class="esc">(.*?)</span><div class="tx"><b>([^<]*)</b><small>([^<]*)</small><div class="br"><i class="q" style="width:([\d.]+)%"></i><i class="m" style="width:([\d.]+)%"></i></div></div><span class="gl">(\d+)</span></div>', re.S)
    linhas = [{"tip": decod(t), "pos": int(p), "logo": lg, "nome": decod(n), "sub": decod(s), "q": float(q), "m": float(m), "g": int(g)} for t, p, lg, n, s, q, m, g in padrao.findall(h)]
    mais = re.search(r'<div class="mais" data-tip="([^"]*)">([^<]*)</div>', h)
    return linhas, (decod(mais.group(1)), decod(mais.group(2))) if mais else None


def recordes_da(h):
    padrao = re.compile(r'<div class="rc" data-tip="([^"]*)"><h4>([^<]*)</h4><div class="v">([^<]*)</div><small>([^<]*)</small></div>')
    return [{"tip": decod(t), "r": decod(r), "v": decod(v), "s": decod(s)} for t, r, v, s in padrao.findall(h)]


def tabela_tip(secao):
    assert secao.startswith("@")
    return [tuple(x.split("::")) for x in secao[1:].split("\n")]


def ficha(j, curto):
    quem = f"1ª fase · rodada {j['r']}" if j["f"] == 1 else FASE[j["f"]]
    return [("Jogo", f"{j['n']} · {data_longa(j['d'])}"), ("Fase", quem), ("Placar", f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}"), ("Público", fmt(j["pu"]))]


@precisa_dados
@precisa_node
def test_o_codigo_roda_no_node_sem_texto_estragado(saida):
    assert set(saida["fases"]) == {"t", "p", "m"} and not any(f["ruim"] for f in saida["fases"].values())
    assert all(all(f["tem"]) for f in saida["fases"].values())


@precisa_dados
@precisa_node
def test_oito_quadros_com_os_numeros_de_cada_recorte_e_a_dica_com_os_tres_recortes(saida, ref):
    esp_sub = {"t": f"{len([j for j in ref['jogos'] if j['f'] == 1])} na 1ª fase e {len([j for j in ref['jogos'] if j['f'] > 1])} no mata-mata", "p": "8 rodadas, pontos corridos", "m": "quartas, semifinais e final"}
    rs = {f: resumo(recorte(ref, f)) for f in "tpm"}
    for f in "tpm":
        r = rs[f]
        k = kpis_da(saida["fases"][f]["kpis"])
        esperados = [("Jogos", fmt(r["n"]), esp_sub[f]), ("Gols", fmt(r["g"]), "sem contar pênaltis da disputa"), ("Gols por jogo", fmt(r["gpj"], 2), "média do recorte"), ("Público total", fmt(r["pu"]), "ingressos do boletim"),
                     ("Público médio", fmt(r["pm"]), "por jogo"), ("Renda bruta", "R$ " + fmt(Decimal(r["rb"]) / 10**8, 2) + " mi", reais(r["rb"])), ("Ticket médio", reais(r["tk"]), "por pagante"),
                     ("Cartões por jogo", fmt(r["cpj"], 2), f"{fmt(r['am'])} amarelos e {fmt(r['vm'])} vermelhos")]
        assert [(x["r"], x["v"], x["s"]) for x in k] == esperados, f
        assert [(x["x"], x["y"]) for x in k] == [((i % 4) * 298, (i // 4) * 128) for i in range(8)]
        assert all(x["x"] + 281 <= 1175 and x["y"] + 116 <= 244 for x in k)
        valores = {
            "Jogos": lambda x: fmt(x["n"]), "Gols": lambda x: fmt(x["g"]), "Gols por jogo": lambda x: fmt(x["gpj"], 2), "Público total": lambda x: fmt(x["pu"]), "Público médio": lambda x: fmt(x["pm"]), "Renda bruta": lambda x: reais(x["rb"]),
            "Ticket médio": lambda x: reais(x["tk"]), "Cartões por jogo": lambda x: fmt(x["cpj"], 2)}
        for q in k:
            secoes = q["tip"].split("||")
            assert secoes[0] == q["r"]
            assert tabela_tip(secoes[2]) == [("Todas as fases", valores[q["r"]](rs["t"])), ("1ª fase", valores[q["r"]](rs["p"])), ("Mata-mata", valores[q["r"]](rs["m"]))]
            assert secoes[-1].startswith("~Este número muda com o filtro de fase")


@precisa_dados
@precisa_node
def test_bloco_do_campeao_mostra_o_caminho_e_nao_muda_com_o_filtro(saida, montagem, ref, curto):
    meta = montagem["vg"]["meta"]
    camp, vice = meta["camp"], meta["vice"]
    mm = sorted((j for j in ref["jogos"] if j["f"] > 1 and camp in (j["m"], j["v"])), key=lambda j: j["n"])
    pen = {int(p["numero_jogo"]): (p["penaltis_mandante"], p["penaltis_visitante"]) for p in ref["partidas"] if p["penaltis_mandante"]}
    esperado = []
    for j in mm:
        if j["f"] == 4:
            continue
        adv = j["v"] if j["m"] == camp else j["m"]
        placar = f"{j['gm']} × {j['gv']}" if j["m"] == camp else f"{j['gv']} × {j['gm']}"
        txt = f"{curto[camp]} {placar} {curto[adv]}"
        if j["n"] in pen:
            a, b = (int(pen[j["n"]][0]), int(pen[j["n"]][1])) if j["m"] == camp else (int(pen[j["n"]][1]), int(pen[j["n"]][0]))
            txt += f" (pênaltis {a} a {b})"
        esperado.append((FASE[j["f"]], txt))
    legs = " e ".join((f"{j['gm']} × {j['gv']}" if j["m"] == camp else f"{j['gv']} × {j['gm']}") for j in mm if j["f"] == 4)
    esperado.append(("Final", f"{legs} contra {curto[vice]}"))
    blocos = [saida["fases"][f]["paineis"][0] for f in "tpm"]
    assert blocos[0] == blocos[1] == blocos[2]
    h = blocos[0]
    assert re.search(rf'<div class="nm">{re.escape(curto[camp])}</div><div class="vc">Vice-campeão: <b>{re.escape(curto[vice])}</b> · final em pontos: <b>{meta["fpts"][0]} a {meta["fpts"][1]}</b></div>', h)
    assert [(decod(a), decod(b)) for a, b in re.findall(r'<div><span>([^<]*)</span><b>([^<]*)</b></div>', h.split('<div class="cam">')[1])] == esperado
    assert "não muda com o filtro" in h
    tip = decod(re.search(r'<div class="cmp" data-tip="([^"]*)"', h).group(1)).split("||")
    assert tip[0] == "Campeão e caminho" and tabela_tip(tip[2]) == esperado


@precisa_dados
@precisa_node
def test_caminho_do_campeao_mostra_os_penaltis_quando_o_jogo_foi_decidido_neles(saida, ref, curto):
    s = saida["campeaoSintetico"]
    camp = s["camp"]
    assert curto[camp] == "Corinthians"
    jogo = next(j for j in ref["jogos"] if j["f"] == 2 and camp in (j["m"], j["v"]))
    pm, pv = next((int(p["penaltis_mandante"]), int(p["penaltis_visitante"])) for p in ref["partidas"] if int(p["numero_jogo"]) == jogo["n"])
    assert pm != pv
    a, b = (pm, pv) if jogo["m"] == camp else (pv, pm)
    adv = jogo["v"] if jogo["m"] == camp else jogo["m"]
    gols = f"{jogo['gm']} × {jogo['gv']}" if jogo["m"] == camp else f"{jogo['gv']} × {jogo['gm']}"
    linhas = [(decod(f), decod(t)) for f, t in re.findall(r'<div><span>([^<]*)</span><b>([^<]*)</b></div>', s["p0"].split('<div class="cam">')[1])]
    assert linhas[0] == ("Quartas de final", f"Corinthians {gols} {curto[adv]} (pênaltis {a} a {b})")
    assert linhas[1][0] == "Semifinal" and "pênaltis" not in linhas[1][1]
    assert '<div class="nm">Corinthians</div>' in s["p0"]


@precisa_dados
@precisa_node
def test_grafico_tem_uma_barra_por_rodada_com_a_media_de_gols_do_jogo_e_a_dica_dos_jogos(saida, ref, curto):
    todas = defaultdict(list)
    for j in ref["jogos"]:
        todas[j["r"]].append(j)
    ymax = math.ceil(max(sum(x["gm"] + x["gv"] for x in js) / len(js) for js in todas.values()))
    for f in "tpm":
        js = recorte(ref, f)
        por = defaultdict(list)
        for j in js:
            por[j["r"]].append(j)
        rodadas = sorted(por)
        barras, ym, legenda = barras_da(saida["fases"][f]["paineis"][1])
        assert len(barras) == len(rodadas) == {"t": 12, "p": 8, "m": 4}[f]
        rotulo = lambda r: f"R{r}" if r <= 8 else {9: "QF", 10: "SF", 11: "F1", 12: "F2"}[r]
        slot = 716 / len(rodadas)
        for i, (b, r) in enumerate(zip(barras, rodadas)):
            gols = sum(x["gm"] + x["gv"] for x in por[r])
            media = Decimal(gols) / len(por[r])
            assert b["rot"] == rotulo(r) and b["val"] == fmt(media, 1) and b["cls"] == ("bq" if r <= 8 else "bm")
            assert abs(b["h"] - float(media) / ymax * 160) < 0.06 and abs(b["y"] - (200 - float(media) / ymax * 160)) < 0.06
            assert abs(b["slot"][0] - i * slot) < 0.01 and abs(b["slot"][1] - slot) < 0.01 and abs(b["x"] + b["w"] / 2 - (i + 0.5) * slot) < 0.1
            secoes = b["tip"].split("||")
            nome = f"Rodada {r} · 1ª fase" if r <= 8 else {9: "Quartas de final", 10: "Semifinal", 11: "Final · jogo de ida", 12: "Final · jogo de volta"}[r]
            assert secoes[0] == nome and secoes[1] == f"{plural(gols, 'gol', 'gols')} em {plural(len(por[r]), 'jogo', 'jogos')} ({fmt(media, 2)} por jogo)"
            assert tabela_tip(secoes[2]) == [(data_br(x["d"]), f"{curto[x['m']]} {x['gm']} × {x['gv']} {curto[x['v']]}") for x in por[r]]
        r_ = resumo(js)
        assert abs(ym - (200 - float(r_["gpj"]) / ymax * 160)) < 0.06
        assert legenda == f"QF quartas · SF semifinal · F1 e F2 final · tracejado: média {fmt(r_['gpj'], 2)}"
        assert f"{FS[f]} · {plural(len(rodadas), 'rodada', 'rodadas')}</small>" in saida["fases"][f]["paineis"][1]
    assert max(b["h"] for b in barras_da(saida["fases"]["t"]["paineis"][1])[0]) <= 160


@precisa_dados
@precisa_node
def test_mando_mostra_vitorias_empates_e_derrotas_do_mandante_em_cada_recorte(saida, ref):
    for f in "tpm":
        r = resumo(recorte(ref, f))
        h = saida["fases"][f]["paineis"][2]
        n = r["n"]
        larguras = [float(x) for x in re.findall(r'<div class="[abc]" style="width:([\d.]+)%">', h)]
        assert all(abs(l - 100 * v / n) < 0.01 for l, v in zip(larguras, (r["a"], r["e"], r["b"]))) and abs(sum(larguras) - 100) < 0.01
        textos = re.findall(r'<div class="[abc]" style="width:[\d.]+%">([^<]*)</div>', h)
        assert textos == [str(v) if 100 * v / n >= 14 else "" for v in (r["a"], r["e"], r["b"])]
        numeros = re.findall(r'<div style="--cc:[^"]*"><b>([^<]*)</b><span>([^<]*)</span><small>([^<]*)</small></div>', h)
        assert numeros == [(pct(r["a"], n), "Mandante", plural(r["a"], "vitória", "vitórias")), (pct(r["e"], n), "Empate", plural(r["e"], "jogo", "jogos")), (pct(r["b"], n), "Visitante", plural(r["b"], "vitória", "vitórias"))]
        tip = decod(re.search(r'<div class="md" data-tip="([^"]*)"', h).group(1)).split("||")
        assert tabela_tip(tip[2]) == [("Vitória do mandante", f"{plural(r['a'], 'jogo', 'jogos')} · {pct(r['a'], n)}"), ("Empate no tempo regulamentar", f"{plural(r['e'], 'jogo', 'jogos')} · {pct(r['e'], n)}"), ("Vitória do visitante", f"{plural(r['b'], 'jogo', 'jogos')} · {pct(r['b'], n)}")]
        assert f"{FS[f]} · {plural(n, 'jogo', 'jogos')}</small>" in h and "No mata-mata, quem empata vai aos pênaltis" in h


@precisa_dados
@precisa_node
def test_artilharia_lista_todos_os_atletas_do_recorte_em_ordem_com_rolagem_e_sem_linha_de_empatados(saida, ref, curto):
    art = artilheiros(ref)
    for f in "tpm":
        l = sorted((a for a in art if gols_no_recorte(a, f) > 0), key=lambda a: (-gols_no_recorte(a, f), a["p"]))
        h = saida["fases"][f]["paineis"][3]
        linhas, linha_mais = artilheiros_da(h)
        assert linha_mais is None and 'class="mais"' not in h
        assert len(linhas) == len(l) and len(l) > 5
        assert '<div class="rw"><div class="rola" data-r="ar" style="max-height:484px">' in h
        assert f"{FS[f]} · {plural(len(l), 'atleta', 'atletas')}</small>" in h
        maximo = gols_no_recorte(l[0], f)
        for i, (x, a) in enumerate(zip(linhas, l)):
            g = gols_no_recorte(a, f)
            sub = curto[a["c"]] + (f" · {a['g1']} + {a['g2']} no mata-mata" if f == "t" and a["g2"] > 0 else "")
            assert (x["pos"], x["nome"], x["sub"], x["g"]) == (i + 1, a["a"], sub, g)
            q, m = (a["g1"] if f != "m" else 0), (a["g2"] if f != "p" else 0)
            assert abs(x["q"] - 100 * q / maximo) < 0.01 and abs(x["m"] - 100 * m / maximo) < 0.01
            assert "<img" in x["logo"] or 'class="sg"' in x["logo"]
            secoes = x["tip"].split("||")
            assert secoes[0] == f"{a['p']} · {curto[a['c']]}" and tabela_tip(secoes[1]) == [("Gols na 1ª fase", str(a["g1"])), ("Gols no mata-mata", str(a["g2"])), ("Total no campeonato", str(a["g1"] + a["g2"]))]
            assert secoes[-1] == "~Gol contra não entra na artilharia."
    assert [g for g in (gols_no_recorte(a, "t") for a in art) if g > 0].count(4) >= 3


@precisa_dados
@precisa_node
def test_recordes_do_recorte_goleada_publico_maior_e_menor_e_jogos_sem_gols(saida, ref, curto):
    for f in "tpm":
        js = recorte(ref, f)
        rec = recordes_da(saida["fases"][f]["paineis"][4])
        assert [x["r"] for x in rec] == ["Maior goleada", "Maior público", "Menor público", "Jogos sem gols"]
        margem = max(abs(j["gm"] - j["gv"]) for j in js)
        gl = [j for j in js if abs(j["gm"] - j["gv"]) == margem]
        jogo = lambda j: f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}"
        quem = lambda j: f"1ª fase · rodada {j['r']}" if j["f"] == 1 else FASE[j["f"]]
        assert margem > 0
        assert rec[0]["v"] == jogo(gl[0]) and rec[0]["s"] == data_longa(gl[0]["d"]) + " · " + quem(gl[0]) + (f" · e mais {len(gl) - 1}" if len(gl) > 1 else "")
        secoes = rec[0]["tip"].split("||")
        assert secoes[0] == "Maior goleada" and tabela_tip(secoes[1]) == ficha(gl[0], curto)
        nota = f"~Outros {len(gl) - 1} jogo(s) com a mesma diferença de {margem} gols: " + "; ".join(jogo(j) for j in gl[1:]) + "." if len(gl) > 1 else f"~Diferença de {margem} gols."
        assert secoes[2] == nota
        pmax, pmin = max(j["pu"] for j in js), min(j["pu"] for j in js)
        jm, jn = next(j for j in js if j["pu"] == pmax), next(j for j in js if j["pu"] == pmin)
        assert (rec[1]["v"], rec[1]["s"]) == (f"{fmt(pmax)} pessoas", f"{jogo(jm)} · {data_br(jm['d'])}") and (rec[2]["v"], rec[2]["s"]) == (f"{fmt(pmin)} pessoas", f"{jogo(jn)} · {data_br(jn['d'])}")
        assert tabela_tip(rec[1]["tip"].split("||")[1]) == ficha(jm, curto) and tabela_tip(rec[2]["tip"].split("||")[1]) == ficha(jn, curto)
        sem = [j for j in js if j["gm"] + j["gv"] == 0]
        assert rec[3]["v"] == plural(len(sem), "jogo", "jogos")
        if sem:
            assert rec[3]["s"] == f"{curto[sem[0]['m']]} × {curto[sem[0]['v']]}" + (f" e mais {len(sem) - 1}" if len(sem) > 1 else "")
            assert tabela_tip(rec[3]["tip"].split("||")[1]) == [(data_br(j["d"]), f"0 × 0 {curto[j['m']]} e {curto[j['v']]}") for j in sem]
        else:
            assert rec[3]["s"] == "nenhum 0 × 0" and rec[3]["tip"].split("||")[1] == "Nenhum jogo 0 × 0 neste recorte."


@precisa_dados
@precisa_node
def test_cabecalho_botoes_de_fase_limpar_e_selo_de_conferencia(saida, ref, montagem):
    meta = montagem["vg"]["meta"]
    for f in "tpm":
        r = resumo(recorte(ref, f))
        sub = saida["fases"][f]["sub"]
        assert sub == (f"Paulistão A1 2026 em uma olhada · {plural(r['n'], 'jogo', 'jogos')}, {plural(r['g'], 'gol', 'gols')} e o campeão" if f == "t" else f"{FS[f]} · {plural(r['n'], 'jogo', 'jogos')} · {plural(r['g'], 'gol', 'gols')}")
        ctl = saida["fases"][f]["ctl"]
        chips = re.findall(r'<button class="chp( on)?" data-act="fase" data-v="(\w)"[^>]*><span>([^<]*)</span></button>', ctl)
        assert [(c[1], c[2], bool(c[0])) for c in chips] == [(k, FS[k], k == f) for k in "tpm"]
        assert ("lim off" in ctl) == (f == "t") and 'data-act="ajuda"' in ctl
        tips = {c[1]: decod(re.search(rf'data-v="{c[1]}" data-tip="([^"]*)"', ctl).group(1)).split("||") for c in chips}
        assert tips["t"][1] == plural(len(recorte(ref, "t")), "jogo", "jogos") + " do campeonato." and tips["p"][1] == plural(len(recorte(ref, "p")), "jogo", "jogos") + " da 1ª fase, em pontos corridos."
        assert tips["m"][1] == plural(len(recorte(ref, "m")), "jogo", "jogos") + " de quartas, semifinais e final."
        selo = saida["fases"][f]["paineis"][5]
        assert sem_tags(selo).startswith(f"✔ {meta['regras']} regras · {meta['ok']} sem ocorrência · {meta['expl']} explicadas · {meta['aber']} abertas")
        assert f"Placares iguais à FPF: {meta['placar'][0]} de {meta['placar'][1]} · posições: {meta['classif'][0]} de {meta['classif'][1]}." in sem_tags(selo) and 'data-act="conf"' in selo
        assert saida["fases"][f]["paineis"][5] == saida["fases"]["t"]["paineis"][5]


@precisa_dados
@precisa_node
def test_rodape_e_ajuda_explicam_a_tela(saida):
    r = saida["rodape"]
    assert "totais conferidos com o cálculo independente dos indicadores" in r["rod"] and "Projeto independente, sem vínculo com a FPF" in r["rod"]
    assert "Como ler esta tela" in r["aj"] and r["aj"].count("<li>") == 4 and re.search(r'<button[^>]*data-act="ajuda-fechar"[^>]*data-tip="[^"]+"[^>]*>Entendi</button>', r["aj"])
    for palavra in ("Gols por jogo", "Mando", "Público e renda", "Cartões", "Artilharia"):
        assert palavra in r["aj"]


def modelo(fase, acao, v):
    if acao == "fase":
        return v if v in ("t", "p", "m") else fase
    return "t" if acao == "limpar" else fase


@precisa_dados
@precisa_node
def test_cliques_nos_botoes_gerados_levam_ao_estado_esperado(saida):
    assert set(saida["acoesVistas"]) == {"fase", "limpar", "ajuda", "ajuda-fechar", "conf"}
    assert len(saida["cliques"]) == 17
    for c in saida["cliques"]:
        a, d = c["antes"], c["depois"]
        if c["act"] == "fase":
            assert d == {"fase": modelo(a["fase"], "fase", c["v"]), "ajuda": a["ajuda"]}, c["rot"]
        elif c["act"] == "limpar":
            assert d == {"fase": "t", "ajuda": a["ajuda"]}, c["rot"]
        elif c["act"] == "ajuda":
            assert d == {"fase": a["fase"], "ajuda": True}
        elif c["act"] == "ajuda-fechar":
            assert d == {"fase": a["fase"], "ajuda": False}
        elif c["act"] == "conf":
            assert d == a
        else:
            assert c["rot"] == "clique fora da ajuda" and a["ajuda"] is True and d == {"fase": a["fase"], "ajuda": False}
    assert [c["idas"] for c in saida["cliques"] if c["act"] == "conf"] == [1, 2] and saida["idas"] == ["conf", "conf", "conf"]
    assert [c["depois"]["fase"] for c in saida["cliques"][:7]] == ["t", "p", "p", "m", "t", "m", "t"]
    assert saida["faseInvalida"] == saida["faseNula"] == saida["faseProto"] == {"fase": "t", "ajuda": False}


@precisa_dados
@precisa_node
def test_teclas_esc_e_backspace_voltam_para_todas_as_fases_e_a_ajuda_fecha_primeiro(saida):
    t = {x["rot"]: x for x in saida["teclas"]}
    livre = {"fase": "t", "ajuda": False}
    assert t["esc sem filtro"]["tratou"] is False and t["esc sem filtro"]["estado"] == livre
    assert t["esc solta"]["antes"] == {"fase": "m", "ajuda": False} and t["esc solta"]["tratou"] is True and t["esc solta"]["estado"] == livre
    assert t["backspace solta"]["antes"]["fase"] == "p" and t["backspace solta"]["tratou"] is True and t["backspace solta"]["estado"] == livre
    assert t["backspace sem filtro"]["tratou"] is False
    assert (t["abre com ?"]["tratou"], t["abre com ?"]["estado"]["ajuda"]) == (True, True) and (t["esc fecha a ajuda"]["tratou"], t["esc fecha a ajuda"]["estado"]["ajuda"]) == (True, False)
    assert t["h abre"]["estado"]["ajuda"] is True and t["enter fecha"]["estado"]["ajuda"] is False
    assert t["h com ctrl nao abre"]["tratou"] is False and t["h com ctrl nao abre"]["estado"]["ajuda"] is False and t["outra tecla"]["tratou"] is False
    assert t["esc com ajuda e filtro fecha so a ajuda"]["antes"] == {"fase": "m", "ajuda": True} and t["esc com ajuda e filtro fecha so a ajuda"]["estado"] == {"fase": "m", "ajuda": False}
    assert t["backspace com ajuda aberta nao solta"]["tratou"] is False and t["backspace com ajuda aberta nao solta"]["estado"] == {"fase": "m", "ajuda": True}
    assert t["espaco fecha a ajuda"]["tratou"] is True and t["espaco fecha a ajuda"]["estado"] == {"fase": "m", "ajuda": False}
    k = saida["teclaNoDocumento"]
    assert k == {"escPrevenido": True, "faseDepoisDoEsc": "t", "escondidoPrevenido": False, "faseEscondido": "p"}


@precisa_dados
@precisa_node
def test_toda_dica_abre_com_titulo_sem_texto_estragado_nem_nome_interno(saida):
    tips = saida["tips"]
    assert len(tips) > 120 and saida["tipEscondeAoSair"] is True
    for t in tips:
        assert t["visivel"] is True and t["html"] == t["tipHtml"] and t["html"].startswith("<b>") and t["tip"].split("||")[0], t["rot"]
        assert not re.search(r"NaN|undefined|Infinity|\[object|null", t["tip"]), t["tip"][:80]
        for ruim in INTERNOS:
            assert ruim not in t["tip"], (ruim, t["tip"][:80])
    assert {t["f"] for t in tips} == {"t", "p", "m"} and {t["rot"] for t in tips} >= {"kpis", "p0", "p1", "p2", "p3", "p4", "p5", "controles", "rodape", "cabecalho"}


@precisa_dados
@precisa_node
def test_dica_escapa_html_e_monta_titulo_tabela_paragrafo_e_nota(saida):
    assert saida["tipHtml"]["completo"] == '<b>Título</b><div class="tv"><div><span>A</span><em>1</em></div><div><span>B</span><em>2</em></div></div><span>Parágrafo</span><small>Nota</small>'
    assert saida["tipHtml"]["escapado"] == "<b>&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;</b>"


@precisa_dados
@precisa_node
def test_sem_escudos_a_tela_cai_para_a_sigla_colorida(montagem):
    s = rodar(montagem, "semlogos")
    t = s["fases"]["t"]
    assert not any(f["ruim"] for f in s["fases"].values())
    assert t["paineis"][0].count("<img") == 0 and 'class="sg"' in t["paineis"][0] and t["paineis"][3].count("<img") == 0 and t["paineis"][3].count('class="sg"') == 111
    com = rodar(montagem)["fases"]["t"]
    assert com["paineis"][0].count("<img") == 1 and com["paineis"][3].count("<img") == 111
