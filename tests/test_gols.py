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
from referencia_nomes import curto_das_pessoas  # noqa: E402

PROC = RAIZ / "data" / "processed"
PROTO = RAIZ / "prototype"
precisa_dados = pytest.mark.skipif(not all((PROC / n).exists() for n in ("fato_partida.csv", "fato_evento.csv", "ref_indicadores.csv", "dim_fase.csv")), reason="rode scripts/04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
INTERNOS = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")
FS = {"t": "Todas as fases", "p": "1ª fase", "m": "Mata-mata"}
FASE = {1: "1ª fase", 2: "Quartas de final", 3: "Semifinal", 4: "Final"}
COD_FASE = {"PRIMEIRA FASE": 1, "QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}
NOME_FAIXA = ["1 a 15", "16 a 30", "31 a 45", "46 a 60", "61 a 75", "76 a 90 e acréscimos"]
TIPOS = {"gol": "g", "gol_penalti": "p", "gol_falta": "f", "gol_contra": "c"}


def carregar(nome, arq):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def decod(t):
    return t.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def sem_tags(t):
    return re.sub(r"<[^>]*>", "", t)


def fmt(n, c=0):
    v = Decimal(n).quantize(Decimal(1).scaleb(-c), rounding=ROUND_HALF_UP)
    return f"{v:,.{c}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def plural(n, u, p):
    return f"{fmt(n)} " + (u if n == 1 else p)


def lista(a):
    return a[0] if len(a) == 1 else ", ".join(a[:-1]) + " e " + a[-1]


def pct(a, b):
    return fmt(Decimal(100 * a) / b, 1) + "%" if b > 0 else "—"


def sinal(n):
    return "+" + fmt(n) if n > 0 else "−" + fmt(-n) if n < 0 else "0"


def data_br(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}"


def data_longa(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}/{a}"


def faixa(mn):
    return 0 if mn <= 15 else 1 if mn <= 30 else 2 if mn <= 45 else 3 if mn <= 60 else 4 if mn <= 75 else 5


def tabela_tip(secao):
    assert secao.startswith("@"), secao[:60]
    return [tuple(x.split("::")) for x in secao[1:].split("\n")]


# ---------- referência recalculada aqui, direto das tabelas tratadas ----------

@pytest.fixture(scope="module")
def ref():
    fases = {f["id_fase"]: COD_FASE[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = ler_csv(PROC / "fato_partida.csv")
    eventos = ler_csv(PROC / "fato_evento.csv")
    jogos = []
    for p in sorted(partidas, key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"]))):
        jogos.append({"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "m": int(p["id_clube_mandante"]), "v": int(p["id_clube_visitante"]), "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]), "_id": p["id_partida"]})
    numero = {p["id_partida"]: int(p["numero_jogo"]) for p in partidas}
    curto = curto_das_pessoas(eventos).__getitem__

    gols = [{"j": numero[e["id_partida"]], "mn": int(e["minuto"]), "pe": 1 if e["periodo"] == "1T" else 2, "t": TIPOS[e["tipo_evento"]], "c": int(e["id_clube_creditado"]), "k": int(e["id_clube"]), "p": e["pessoa"], "a": curto(e["pessoa"])}
            for e in eventos if e["tipo_evento"] in TIPOS]
    ordem = {j["n"]: i for i, j in enumerate(jogos)}
    gols.sort(key=lambda g: (ordem[g["j"]], g["mn"], g["pe"], g["p"]))
    return {"jogos": jogos, "gols": gols, "por_n": {j["n"]: j for j in jogos}}


def jogos_do_recorte(ref, f, c):
    return [j for j in ref["jogos"] if (f == "t" or (f == "p" and j["f"] == 1) or (f == "m" and j["f"] > 1)) and (c is None or c in (j["m"], j["v"]))]


def gols_do_recorte(ref, f, c):
    ns = {j["n"] for j in jogos_do_recorte(ref, f, c)}
    return [g for g in ref["gols"] if g["j"] in ns]


def resumo(ref, f, c):
    js = jogos_do_recorte(ref, f, c)
    gs = gols_do_recorte(ref, f, c)
    meus = gs if c is None else [g for g in gs if g["c"] == c]
    sof = [] if c is None else [g for g in gs if g["c"] != c]
    fx, fs = [0] * 6, [0] * 6
    ft = [Counter() for _ in range(6)]
    for g in meus:
        fx[faixa(g["mn"])] += 1
        ft[faixa(g["mn"])][g["t"]] += 1
    for g in sof:
        fs[faixa(g["mn"])] += 1
    q = lambda t: sum(1 for g in meus if g["t"] == t)
    n = len(js)
    return {"n": n, "g": len(meus), "sof": len(sof), "pen": q("p"), "fal": q("f"), "aut": q("c"), "sem": sum(1 for j in js if j["gm"] + j["gv"] == 0), "gpj": Decimal(len(meus)) / n if n else Decimal(0), "fx": fx, "fs": fs, "ft": ft, "js": js, "meus": meus}


@pytest.fixture(scope="module")
def montagem(tmp_path_factory):
    m = carregar("montar_app13_gl", "13_montar_app.py")
    versus = m.modulo_versus().montar_dados()
    gl = m.montar_dados_gl(versus)
    frag = (PROTO / "gols" / "fragmento.html").read_text(encoding="utf-8").replace("__DADOS__", m.dados_json(gl))
    pasta = tmp_path_factory.mktemp("gl")
    (pasta / "gl.html").write_text(m.pagina("t", m.logos_js(versus) + frag), encoding="utf-8")
    return {"m": m, "versus": versus, "gl": gl, "frag": frag, "pasta": pasta}


@pytest.fixture(scope="module")
def curto(montagem):
    return {int(c["id"]): c["curto"] for c in montagem["gl"]["clubes"]}


@pytest.fixture(scope="module")
def sigla(montagem):
    return {int(c["id"]): c["sigla"] for c in montagem["gl"]["clubes"]}


def rodar(montagem, *extra):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_gl.js"), str(montagem["pasta"] / "gl.html"), *extra], capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr[-1500:]
    s = json.loads(proc.stdout)
    assert not s.get("semGancho")
    return s


@pytest.fixture(scope="module")
def saida(montagem):
    return rodar(montagem)


def estado_de(saida, f, c):
    return next(e for e in saida["estados"] if e["f"] == f and e["c"] == c)


# ---------- pacote de dados ----------

@precisa_dados
def test_jogos_do_pacote_sao_os_72_das_tabelas_campo_a_campo(montagem, ref):
    esperado = [{k: v for k, v in j.items() if not k.startswith("_")} for j in ref["jogos"]]
    assert montagem["gl"]["jogos"] == esperado and len(esperado) == 72


@precisa_dados
def test_gols_do_pacote_sao_os_168_dos_eventos_um_a_um(montagem, ref):
    atl = montagem["gl"]["atl"]
    gols = montagem["gl"]["gols"]
    assert len(gols) == len(ref["gols"]) == 168
    for g, e in zip(gols, ref["gols"]):
        assert (g["j"], g["mn"], g["pe"], g["t"], g["c"], g["k"]) == (e["j"], e["mn"], e["pe"], e["t"], e["c"], e["k"])
        assert atl[g["a"]]["p"] == e["p"] and atl[g["a"]]["a"] == e["a"]
    assert Counter(g["t"] for g in gols) == {"g": 150, "p": 13, "f": 3, "c": 2}
    assert [a["p"] for a in atl] == sorted({e["p"] for e in ref["gols"]}) and len(atl) == 112


@precisa_dados
def test_cada_jogo_tem_tantos_gols_creditados_a_cada_lado_quanto_o_placar_diz(montagem, ref):
    por = Counter((g["j"], g["c"]) for g in montagem["gl"]["gols"])
    for j in ref["jogos"]:
        assert por[(j["n"], j["m"])] == j["gm"] and por[(j["n"], j["v"])] == j["gv"], j["n"]
    assert all(g["t"] == "c" or g["k"] == g["c"] for g in montagem["gl"]["gols"])
    assert all(g["t"] != "c" or g["k"] != g["c"] for g in montagem["gl"]["gols"])


@precisa_dados
def test_totais_do_pacote_batem_com_o_gabarito_por_faixa_de_minuto_por_fase_e_por_tipo(montagem, ref):
    gab = ler_csv(PROC / "ref_indicadores.csv")
    geral = {l["id_indicador"]: Decimal(l["valor"]) for l in gab if l["escopo"] == "geral"}
    faixas = {l["chave"]: int(Decimal(l["valor"])) for l in gab if l["escopo"] == "faixa_minuto"}
    r = resumo(ref, "t", None)
    assert dict(zip(["01-15", "16-30", "31-45", "46-60", "61-75", "76-90+"], r["fx"])) == faixas == {"01-15": 22, "16-30": 22, "31-45": 24, "46-60": 27, "61-75": 26, "76-90+": 47}
    assert r["g"] == geral["I02"] and r["pen"] == geral["I25"] and r["sem"] == geral["I26"]
    assert sum(1 for g in montagem["gl"]["gols"] if g["pe"] == 1) == 68 == sum(r["fx"][:3])
    por_fase = {l["chave"]: int(Decimal(l["valor"])) for l in gab if l["escopo"] == "fase" and l["id_indicador"] == "I02"}
    for f, nome in {1: "PRIMEIRA FASE", 2: "QUARTAS DE FINAL", 3: "SEMIFINAL", 4: "FINAL"}.items():
        assert sum(1 for g in montagem["gl"]["gols"] if ref["por_n"][g["j"]]["f"] == f) == por_fase[nome]
    art = Counter(montagem["gl"]["atl"][g["a"]]["p"] for g in montagem["gl"]["gols"] if g["t"] != "c")
    assert dict(art) == {l["chave"]: int(Decimal(l["valor"])) for l in gab if l["escopo"] == "artilheiro"}


@precisa_dados
def test_gols_pro_e_contra_da_primeira_fase_batem_com_a_tabela_oficial(montagem, ref):
    oficial = {int(o["id_clube"]): o for o in ler_csv(PROC / "fato_classificacao_oficial.csv") if o["fase"] == "PRIMEIRA FASE"}
    pro, con = Counter(), Counter()
    for j in jogos_do_recorte(ref, "p", None):
        pro[j["m"]] += j["gm"]
        con[j["m"]] += j["gv"]
        pro[j["v"]] += j["gv"]
        con[j["v"]] += j["gm"]
    assert len(oficial) == 16 and all((pro[c], con[c]) == (int(o["gols_pro"]), int(o["gols_contra"])) for c, o in oficial.items())


@precisa_dados
def test_clubes_e_nomes_do_pacote_nao_citam_nada_interno(montagem):
    assert len(montagem["gl"]["clubes"]) == 16
    for texto in [c[k] for c in montagem["gl"]["clubes"] for k in ("nome", "curto", "sigla")] + [a[k] for a in montagem["gl"]["atl"] for k in ("p", "a")]:
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
    return montagem["m"].montar_dados_gl(montagem["versus"])


@precisa_dados
def test_o_montador_para_se_um_gol_sumir_dos_eventos(montagem, monkeypatch):
    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", lambda ls: ls.pop(next(k for k, x in enumerate(ls) if x["tipo_evento"] == "gol")))
    with pytest.raises(SystemExit):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_o_placar_de_um_jogo_mudar(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "7")
        l["gols_visitante"] = str(int(l["gols_visitante"]) + 1)

    adulterar(monkeypatch, montagem["m"], "fato_partida.csv", mexer)
    with pytest.raises(SystemExit):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_gol_trocar_de_faixa_de_minuto(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["tipo_evento"] == "gol" and 0 < int(x["minuto"]) <= 15)
        l["minuto"] = "20"

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="faixa de minuto"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_penalti_virar_gol_comum(montagem, monkeypatch):
    def mexer(linhas):
        next(x for x in linhas if x["tipo_evento"] == "gol_penalti")["tipo_evento"] = "gol"

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="pênalti"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_gol_for_creditado_ao_clube_errado(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["tipo_evento"] == "gol")
        l["id_clube_creditado"] = l["id_clube"] = next(c for c in ("3388", "58") if c != l["id_clube"])

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit):
        refazer(montagem)


# ---------- montagem da tela ----------

@precisa_dados
def test_fragmento_nao_deixa_marca_sobrando_e_so_age_quando_visivel(montagem):
    assert not re.search(r"__[A-Z_]+__", montagem["frag"])
    src = (PROTO / "gols" / "fragmento.html").read_text(encoding="utf-8")
    assert src.count("__DADOS__") == 1 and "height:100%;min-height:320px" in src and "if(!raiz.offsetParent)return;" in src
    assert "window.PA.mods.gl={entrar:entrar}" in src and 'id="glx"' in src
    for ruim in INTERNOS:
        assert ruim not in src, ruim
    assert "http://" not in src and "https://" not in src and "@import" not in src and "<link" not in src


@precisa_dados
def test_textos_da_tela_sao_todos_de_pelo_menos_16_pixels():
    src = (PROTO / "gols" / "fragmento.html").read_text(encoding="utf-8")
    tamanhos = [int(x) for x in re.findall(r"font-size:(\d+)px", src)] + [int(x) for x in re.findall(r"font:[^;{}]*?(\d+)px", src)]
    assert tamanhos and min(tamanhos) >= 16, sorted(set(tamanhos))


@precisa_dados
def test_desenhos_nao_roubam_o_clique_nem_a_dica():
    src = (PROTO / "gols" / "fragmento.html").read_text(encoding="utf-8")
    assert re.search(r"#glx \.tip\{[^}]*pointer-events:none", src)
    rola = re.search(r"#glx \.rola\{([^}]*)\}", src).group(1)
    assert "overflow-y:auto" in rola and "scrollbar-width:thin" in rola, "as listas precisam de barra de rolagem visível"
    assert re.search(r"padding-right:(1[2-9]|[2-9]\d)px", rola), "o conteúdo das listas precisa de folga em relação à barra de rolagem"
    assert re.search(r"#glx \.rw::after\{[^}]*pointer-events:none", src), "o esmaecido do fim da lista não pode tampar o clique"
    for seletor in (r"#glx \.campo text", r"#glx \.campo \.lin", r"#glx \.campo \.col"):
        assert re.search(seletor + r"\{[^}]*pointer-events:none", src), seletor
    js = src[src.index("<script>"):]
    for fixo in ("72 jogos", "168 gols", "64 jogos", "1ª fase · 64"):
        assert fixo not in js, fixo


@precisa_dados
def test_pagina_do_app_leva_a_tela_entre_a_classificacao_e_a_disciplina():
    m = carregar("montar_app13_glpg", "13_montar_app.py")
    dados = m.montar_todos_os_dados()
    frag = m.montar_fragmentos(dados)
    app = frag["app"]
    assert not re.search(r"__[A-Z_]+__", app)
    assert app.count('id="glx"') == 1 and app.count('<section class="mod" id="mod-gl">') == 1 and m.dados_json(dados["gl"]) in app and frag["gl"] in app
    nav = re.search(r"<nav[^>]*>(.*?)</nav>", app, re.S).group(1)
    assert re.findall(r'data-mod="(\w+)"', nav) == [t[0] for t in m.TELAS] and "gl" in [t[0] for t in m.TELAS]
    assert '<button data-mod="gl"><span>Gols</span></button>' in nav


# ---------- comportamento (módulo simulado em Node) ----------

def kpis_da(h):
    achados = re.findall(r'<div class="kpi" style="left:([\d.]+)px;--kc:(#[0-9a-f]{6})" data-tip="([^"]*)"><h4>([^<]*)</h4><div class="v">([^<]*)</div><small>([^<]*)</small></div>', h)
    return [{"x": float(x), "tip": decod(t), "r": decod(r), "v": decod(v), "s": decod(s)} for x, cor, t, r, v, s in achados]


def zonas_da(h):
    padrao = re.compile(r'<g class="zona" data-tip="([^"]*)"><rect x="([\d.]+)" y="44" width="([\d.]+)" height="150" fill="rgba\(255,111,163,([\d.]+)\)"/><text class="cn" x="[\d.]+" y="(\d+)" text-anchor="middle">(\d+)</text>'
                        r'<text class="cp" x="[\d.]+" y="\d+" text-anchor="middle">([^<]*)</text>(?:<text x="[\d.]+" y="172" text-anchor="middle">sofridos (\d+)</text>)?</g>')
    topo = re.findall(r'<text class="ct" x="[\d.]+" y="20" text-anchor="middle">([^<]*)</text>', h)
    rotulos = re.findall(r'<text x="[\d.]+" y="218" text-anchor="middle">([^<]*)</text>', h)
    return [{"tip": decod(t), "x": float(x), "w": float(w), "alfa": float(a), "n": int(n), "pct": decod(p), "sof": int(s) if s else None} for t, x, w, a, yy, n, p, s in padrao.findall(h)], [decod(t) for t in topo], rotulos


def jogos_para_ver_da(h):
    colunas = h.split("<h4")[1:]
    saida = []
    for col in colunas:
        titulo = re.search(r">([^<]*)</h4>", col).group(1)
        itens = [{"tip": decod(t), "valor": int(v), "jogo": decod(b), "sub": decod(s)} for t, v, b, s in re.findall(r'<div class="jg" data-tip="([^"]*)"><span class="pl">(\d+)</span><div class="tx"><b>([^<]*)</b><small>([^<]*)</small></div></div>', col)]
        mais = re.search(r'<div class="mais" data-tip="([^"]*)">([^<]*)</div>', col)
        saida.append({"titulo": decod(titulo), "itens": itens, "mais": (decod(mais.group(1)), decod(mais.group(2))) if mais else None})
    return saida


def artilharia_da(h):
    padrao = re.compile(r'<button class="ar( sel| sem)?" data-act="clube" data-id="(\d+)" data-tip="([^"]*)"><span class="ps">(\d+)</span><span class="esc">(.*?)</span><div class="tx"><b>([^<]*) <small>([^<]*)</small></b><div class="bb"><i class="g" style="width:([\d.]+)%"></i><i class="p" style="width:([\d.]+)%"></i><i class="f" style="width:([\d.]+)%"></i></div></div><span class="gl">(\d+)</span></button>', re.S)
    linhas = [{"cls": c.strip(), "k": int(k), "tip": decod(t), "pos": int(p), "logo": lg, "nome": decod(n), "sigla": decod(sg), "g": float(g), "p": float(pp), "f": float(f), "tot": int(tot)} for c, k, t, p, lg, n, sg, g, pp, f, tot in padrao.findall(h)]
    mais = re.search(r'<div class="mais" data-tip="([^"]*)">([^<]*)</div>', h)
    return linhas, (decod(mais.group(1)), decod(mais.group(2))) if mais else None


def pro_contra_da(h):
    padrao = re.compile(r'<button class="pc( sel| sem)?" data-act="clube" data-id="(\d+)" data-tip="([^"]*)"><span class="esc">(.*?)</span><span>([^<]*)</span><span class="nc">(\d+)</span><div class="bc"><i style="width:([\d.]+)%"></i></div><div class="bp"><i style="width:([\d.]+)%"></i></div><span class="np">(\d+)</span></button>', re.S)
    return [{"cls": c.strip(), "id": int(i), "tip": decod(t), "sigla": decod(sg), "con": int(nc), "wc": float(wc), "wp": float(wp), "pro": int(np_)} for c, i, t, lg, sg, nc, wc, wp, np_ in padrao.findall(h)]


def placares_da(h):
    padrao = re.compile(r'<div class="pl2" data-tip="([^"]*)"><span class="sc">(\d+) × (\d+)</span><div class="tx"><div class="bb"><i style="width:([\d.]+)%"></i></div><small>([^<]*)</small></div><span class="ct2">(\d+)</span></div>')
    return [{"tip": decod(t), "hi": int(a), "lo": int(b), "w": float(w), "sub": decod(s), "n": int(n)} for t, a, b, w, s, n in padrao.findall(h)]


def rotulo_do_recorte(f, c, curto):
    return FS[f] if c is None else f"{curto[c]} · {FS[f]}"


def estados_esperados(saida):
    return [(e["f"], e["c"]) for e in saida["estados"]]


@precisa_dados
@precisa_node
def test_o_codigo_roda_no_node_sem_texto_estragado_em_todos_os_estados(saida, ref):
    assert not any(e["ruim"] for e in saida["estados"])
    esperados = [("t", None)] + [("t", c) for c in sorted({x for j in ref["jogos"] for x in (j["m"], j["v"])})]
    for f in ("p", "m"):
        esperados += [(f, None)] + [(f, c) for c in sorted({x for j in jogos_do_recorte(ref, f, None) for x in (j["m"], j["v"])})]
    assert estados_esperados(saida) == esperados and len(esperados) == 43


@precisa_dados
@precisa_node
def test_seis_quadros_em_cada_recorte_e_a_dica_com_os_tres_recortes(saida, ref, curto):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        r = resumo(ref, f, c)
        com = c is not None
        k = kpis_da(e["kpis"])
        esperados = [("Gols", fmt(r["g"]), f"marcados · sofreu {fmt(r['sof'])}" if com else f"em {plural(r['n'], 'jogo', 'jogos')}"),
                     ("Gols por jogo", fmt(r["gpj"], 2), "marcados por jogo" if com else "média do recorte"),
                     ("De pênalti", fmt(r["pen"]), f"{pct(r['pen'], r['g'])} dos gols"), ("De falta", fmt(r["fal"]), f"{pct(r['fal'], r['g'])} dos gols"),
                     ("Gols contra", fmt(r["aut"]), "a favor do clube" if com else "autogols"), ("Jogos sem gols", fmt(r["sem"]), f"{pct(r['sem'], r['n'])} dos jogos")]
        assert [(x["r"], x["v"], x["s"]) for x in k] == esperados, (f, c)
        assert [round(x["x"], 1) for x in k] == [round(i * 307.6, 1) for i in range(6)] and all(x["x"] + 290 <= 1828 for x in k)
        por = {fase: resumo(ref, fase, c) for fase in "tpm"}
        tabelas = [lambda x: fmt(x["g"]), lambda x: fmt(x["gpj"], 2), lambda x: fmt(x["pen"]), lambda x: fmt(x["fal"]), lambda x: fmt(x["aut"]), lambda x: fmt(x["sem"])]
        nota = "~Este número muda com o filtro de fase" + (" e é o do clube escolhido" if com else "; com um clube escolhido ele passa a ser só dos gols desse clube") + "."
        for q, fn in zip(k, tabelas):
            secoes = q["tip"].split("||")
            assert tabela_tip(secoes[2]) == [("Todas as fases", fn(por["t"])), ("1ª fase", fn(por["p"])), ("Mata-mata", fn(por["m"]))], (f, c, q["r"])
            assert secoes[3] == nota


@precisa_dados
@precisa_node
def test_campo_mostra_os_gols_de_cada_faixa_com_cor_proporcional_e_o_total_de_cada_tempo(saida, ref, curto):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        r = resumo(ref, f, c)
        com = c is not None
        zonas, topo, rotulos = zonas_da(e["paineis"][0])
        assert len(zonas) == 6 and rotulos == ["01-15 min", "16-30 min", "31-45 min", "46-60 min", "61-75 min", "76-90+ min"]
        maximo = max(r["fx"] + [1])
        t1, t2 = sum(r["fx"][:3]), sum(r["fx"][3:])
        assert topo == [f"1º tempo · {plural(t1, 'gol', 'gols')} ({pct(t1, r['g'])})", f"2º tempo · {plural(t2, 'gol', 'gols')} ({pct(t2, r['g'])})"]
        for i, z in enumerate(zonas):
            assert abs(z["x"] - i * 1010 / 6) < 0.06 and abs(z["w"] - 1010 / 6) < 0.06
            assert z["n"] == r["fx"][i] and z["pct"] == pct(r["fx"][i], r["g"]) and abs(z["alfa"] - (0.1 + 0.62 * r["fx"][i] / maximo)) < 0.0011
            assert z["sof"] == (r["fs"][i] if com else None)
            secoes = z["tip"].split("||")
            t = r["ft"][i]
            lin = [("Gols", fmt(r["fx"][i])), ("Parte dos gols", pct(r["fx"][i], r["g"])), ("De jogo corrido", fmt(t["g"])), ("De pênalti", fmt(t["p"])), ("De falta", fmt(t["f"])), ("Gol contra", fmt(t["c"]))]
            if com:
                lin.append(("Sofridos nesta faixa", fmt(r["fs"][i])))
            assert secoes[0] == "Minutos " + NOME_FAIXA[i] and tabela_tip(secoes[1]) == lin and secoes[2].startswith("~O acréscimo conta na faixa do tempo")
        assert f"{rotulo_do_recorte(f, c, curto)} · {plural(r['g'], 'gol', 'gols')}</small>" in e["paineis"][0]


@precisa_dados
@precisa_node
def test_jogos_para_ver_listam_todos_os_jogos_do_recorte_ordenados_por_diferenca_e_por_total(saida, ref, curto):
    jogo = lambda j: f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}"
    quem = lambda j: f"1ª fase · rodada {j['r']}" if j["f"] == 1 else FASE[j["f"]]
    dif, tot = (lambda j: abs(j["gm"] - j["gv"])), (lambda j: j["gm"] + j["gv"])
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        js = jogos_do_recorte(ref, f, c)
        h = e["paineis"][1]
        colunas = jogos_para_ver_da(h)
        assert [x["titulo"] for x in colunas] == ["Maiores goleadas", "Mais gols no jogo"]
        assert h.count('<div class="rola" data-r="jg0" style="max-height:220px">') == 1 and h.count('<div class="rola" data-r="jg1" style="max-height:220px">') == 1 and 'class="mais"' not in h
        assert f"{rotulo_do_recorte(f, c, curto)} · {plural(len(js), 'jogo', 'jogos')}</small>" in h
        for coluna, (k1, k2, sufixo) in zip(colunas, ((dif, tot, lambda j: f"Diferença de {plural(dif(j), 'gol', 'gols')}."), (tot, dif, lambda j: f"{plural(tot(j), 'gol', 'gols')} no jogo."))):
            ordem = sorted(js, key=lambda j: (-k1(j), -k2(j), j["d"], j["n"]))
            assert coluna["mais"] is None and len(coluna["itens"]) == len(ordem) == len(js)
            for item, j in zip(coluna["itens"], ordem):
                assert (item["valor"], item["jogo"], item["sub"]) == (k1(j), jogo(j), f"{data_br(j['d'])} · {quem(j)}")
                secoes = item["tip"].split("||")
                gols = [g for g in ref["gols"] if g["j"] == j["n"]]
                lin_gols = [(f"{g['mn']}'", f"{g['a']} · {curto[g['k']]}" + {"g": "", "p": " (pênalti)", "f": " (falta)", "c": " (gol contra)"}[g["t"]]) for g in gols]
                assert secoes[0] == jogo(j) and tabela_tip(secoes[1]) == [("Jogo", f"{j['n']} · {data_longa(j['d'])}"), ("Fase", quem(j)), ("Placar", jogo(j))]
                assert (tabela_tip(secoes[2]) == lin_gols) if lin_gols else (secoes[2] == "Sem gols.")
                assert secoes[3] == "~" + sufixo(j)
    todos = jogos_para_ver_da(estado_de(saida, "t", None)["paineis"][1])
    assert len(todos[0]["itens"]) == 72 and todos[0]["itens"][0]["valor"] == 6 and todos[1]["itens"][0]["valor"] == 7


@precisa_dados
@precisa_node
def test_artilharia_lista_todos_os_atletas_do_recorte_com_a_divisao_por_tipo_e_rolagem(saida, ref, curto, sigla):
    totais = Counter(g["p"] for g in ref["gols"] if g["t"] != "c")
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        gs = [g for g in gols_do_recorte(ref, f, c) if g["t"] != "c" and (c is None or g["c"] == c)]
        por = defaultdict(lambda: {"g": 0, "p": 0, "f": 0, "k": None, "a": None})
        for g in gs:
            a = por[g["p"]]
            a[g["t"]] += 1
            a["k"], a["a"] = g["k"], g["a"]
        l = sorted(por.items(), key=lambda kv: (-(kv[1]["g"] + kv[1]["p"] + kv[1]["f"]), kv[0]))
        h = e["paineis"][2]
        linhas, mais_linha = artilharia_da(h)
        assert mais_linha is None and 'class="mais"' not in h and len(linhas) == len(l)
        assert '<div class="rw"><div class="rola" data-r="ar" style="max-height:326px">' in h
        assert f"{rotulo_do_recorte(f, c, curto)} · {plural(len(l), 'atleta', 'atletas')}</small>" in h
        maximo = l[0][1]["g"] + l[0][1]["p"] + l[0][1]["f"] if l else 1
        for i, (x, (pessoa, a)) in enumerate(zip(linhas, l)):
            tot = a["g"] + a["p"] + a["f"]
            assert (x["pos"], x["nome"], x["sigla"], x["tot"], x["k"]) == (i + 1, a["a"], sigla[a["k"]], tot, a["k"])
            assert abs(x["g"] - 100 * a["g"] / maximo) < 0.01 and abs(x["p"] - 100 * a["p"] / maximo) < 0.01 and abs(x["f"] - 100 * a["f"] / maximo) < 0.01
            assert x["cls"] == ("" if c is None else "sel" if a["k"] == c else "sem")
            assert "<img" in x["logo"] or 'class="sg"' in x["logo"]
            secoes = x["tip"].split("||")
            assert secoes[0] == f"{pessoa} · {curto[a['k']]}" and tabela_tip(secoes[1]) == [("Gols no recorte", str(tot)), ("De jogo corrido", str(a["g"])), ("De pênalti", str(a["p"])), ("De falta", str(a["f"])), ("Gols no campeonato todo", str(totais[pessoa]))]
            assert secoes[2].startswith("~Clique para escolher o clube do atleta")
    assert len(artilharia_da(estado_de(saida, "t", None)["paineis"][2])[0]) == 111


@precisa_dados
@precisa_node
def test_artilharia_desempata_pelo_nome_mesmo_quando_a_ordem_dos_atletas_nos_dados_muda(saida, ref):
    for e in saida["permutado"]:
        f = e["f"]
        por = Counter()
        nomes = {}
        for g in gols_do_recorte(ref, f, None):
            if g["t"] != "c":
                por[g["p"]] += 1
                nomes[g["p"]] = g["a"]
        esperado = sorted(por.items(), key=lambda kv: (-kv[1], kv[0]))
        linhas, _ = artilharia_da(e["paineis"][2])
        assert [(x["nome"], x["tot"]) for x in linhas] == [(nomes[p], n) for p, n in esperado], f


@precisa_dados
@precisa_node
def test_gols_pro_e_contra_listam_os_clubes_que_jogaram_na_fase_em_ordem_de_gols_feitos(saida, ref, curto, sigla):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        m = {}
        for j in jogos_do_recorte(ref, f, None):
            for lado, adv, gf, gc in ((j["m"], j["v"], j["gm"], j["gv"]), (j["v"], j["m"], j["gv"], j["gm"])):
                x = m.setdefault(lado, {"pro": 0, "con": 0, "n": 0})
                x["pro"] += gf
                x["con"] += gc
                x["n"] += 1
        ordem = sorted(m, key=lambda k: (-m[k]["pro"], m[k]["con"], curto[k]))
        linhas = pro_contra_da(e["paineis"][3])
        assert [x["id"] for x in linhas] == ordem
        maximo = max([max(v["pro"], v["con"]) for v in m.values()] + [1])
        for x in linhas:
            v = m[x["id"]]
            assert (x["pro"], x["con"], x["sigla"]) == (v["pro"], v["con"], sigla[x["id"]])
            assert abs(x["wp"] - 100 * v["pro"] / maximo) < 0.01 and abs(x["wc"] - 100 * v["con"] / maximo) < 0.01
            assert x["cls"] == ("" if c is None else "sel" if x["id"] == c else "sem")
            secoes = x["tip"].split("||")
            assert secoes[0] == f"{curto[x['id']]} · gols pró e contra" and tabela_tip(secoes[1]) == [("Gols marcados", str(v["pro"])), ("Gols sofridos", str(v["con"])), ("Saldo", sinal(v["pro"] - v["con"])), ("Jogos", str(v["n"])), ("Marcados por jogo", fmt(Decimal(v["pro"]) / v["n"], 2))]
        assert f"{FS[f]} · {plural(len(m), 'clube', 'clubes')}</small>" in e["paineis"][3]
        if f == "m":
            assert len(linhas) == 8
        else:
            assert len(linhas) == 16
        if c is not None:
            assert sum(1 for x in linhas if x["cls"] == "sel") == 1 and c in [x["id"] for x in linhas]


@precisa_dados
@precisa_node
def test_placares_mais_comuns_contam_os_dois_lados_e_desempatam_pelo_menor_total(saida, ref, curto):
    jogo = lambda j: f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}"
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        js = jogos_do_recorte(ref, f, c)
        m = {}
        for j in js:
            hi, lo = max(j["gm"], j["gv"]), min(j["gm"], j["gv"])
            x = m.setdefault((hi, lo), {"n": 0, "mand": 0, "vis": 0, "emp": 0, "js": []})
            x["n"] += 1
            x["js"].append(j)
            x["mand" if j["gm"] > j["gv"] else "vis" if j["gm"] < j["gv"] else "emp"] += 1
        ordem = sorted(m, key=lambda k: (-m[k]["n"], k[0] + k[1], -k[0]))
        h = e["paineis"][4]
        linhas = placares_da(h)
        assert [(x["hi"], x["lo"]) for x in linhas] == ordem and len(linhas) == len(m)
        assert '<div class="rw"><div class="rola" data-r="pl" style="max-height:308px">' in h and f"{rotulo_do_recorte(f, c, curto)}</small>" in h and f"{plural(len(m), 'placar diferente', 'placares diferentes')} no recorte. O placar vale para os dois lados" in h
        maximo = m[ordem[0]]["n"]
        for x in linhas:
            v = m[(x["hi"], x["lo"])]
            assert x["n"] == v["n"] and abs(x["w"] - 100 * v["n"] / maximo) < 0.01
            assert x["sub"] == ("empate" if x["hi"] == x["lo"] else f"de mandante {v['mand']} · de visitante {v['vis']}")
            secoes = x["tip"].split("||")
            assert secoes[0] == f"Placar {x['hi']} × {x['lo']}" and secoes[1] == f"{plural(v['n'], 'jogo', 'jogos')} ({pct(v['n'], len(js))} do recorte)"
            assert tabela_tip(secoes[2]) == ([("Empates com este placar", str(v["emp"]))] if x["hi"] == x["lo"] else [("Vitórias do mandante", str(v["mand"])), ("Vitórias do visitante", str(v["vis"]))])
            assert tabela_tip(secoes[3]) == [(data_br(j["d"]), jogo(j)) for j in v["js"][:8]]
            resto = len(v["js"]) - 8
            assert secoes[4] == (("~e mais 1 jogo não listado." if resto == 1 else f"~e mais {resto} jogos não listados.") if resto > 0 else "~Jogos com este placar.")
    todos = placares_da(estado_de(saida, "t", None)["paineis"][4])
    assert (todos[0]["hi"], todos[0]["lo"], todos[0]["n"]) == (1, 0, 20) and len(todos) > 6


@precisa_dados
@precisa_node
def test_cabecalho_botoes_de_fase_limpar_e_subtitulo(saida, ref, curto):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        r = resumo(ref, f, c)
        if c is None:
            esperado = ("Quando e como saem os gols, e quem os faz · " if f == "t" else FS[f] + " · ") + f"{plural(r['n'], 'jogo', 'jogos')} · {plural(r['g'], 'gol', 'gols')}"
        else:
            esperado = f"{curto[c]} · {FS[f]} · {plural(r['n'], 'jogo', 'jogos')} · {plural(r['g'], 'gol marcado', 'gols marcados')} e {fmt(r['sof'])} sofridos"
        assert e["sub"] == esperado, (f, c)
        chips = re.findall(r'<button class="chp( on)?" data-act="fase" data-v="(\w)"[^>]*><span>([^<]*)</span></button>', e["ctl"])
        assert [(x[1], x[2], bool(x[0])) for x in chips] == [(k, FS[k], k == f) for k in "tpm"]
        assert ("lim off" in e["ctl"]) == (f == "t" and c is None) and 'data-act="ajuda"' in e["ctl"]


@precisa_dados
@precisa_node
def test_rodape_e_ajuda_explicam_a_tela(saida):
    r = saida["rodape"]
    assert "gols conferidos com os placares e os indicadores" in r["rod"] and "Projeto independente, sem vínculo com a FPF" in r["rod"]
    assert r["aj"].count("<li>") == 4 and re.search(r'<button[^>]*data-act="ajuda-fechar"[^>]*data-tip="[^"]+"[^>]*>Entendi</button>', r["aj"])
    for palavra in ("Gol contra", "Faixa de minuto", "Pró e contra", "Placar comum", "Disputa de pênaltis"):
        assert palavra in r["aj"]


def modelo(est, acao, id_, v, jogam):
    fase, clube = est
    if acao == "fase":
        if v not in ("t", "p", "m"):
            return est
        if clube is not None and clube not in jogam[v]:
            clube = None
        return (v, clube)
    if acao == "clube":
        n = int(id_)
        if n not in jogam[fase]:
            return est
        return (fase, None if clube == n else n)
    return ("t", None) if acao == "limpar" else est


@precisa_dados
@precisa_node
def test_cliques_nos_botoes_gerados_levam_ao_estado_esperado(saida, ref):
    jogam = {f: {x for j in jogos_do_recorte(ref, f, None) for x in (j["m"], j["v"])} for f in "tpm"}
    assert set(saida["acoesVistas"]) == {"clube", "fase", "limpar", "ajuda", "ajuda-fechar"}
    assert len(saida["cliques"]) == 23
    for c in saida["cliques"]:
        a, d = c["antes"], c["depois"]
        if c["act"] in ("fase", "clube", "limpar"):
            assert (d["fase"], d["clube"]) == modelo((a["fase"], a["clube"]), c["act"], c["id"], c["v"], jogam) and d["ajuda"] == a["ajuda"], c["rot"]
        elif c["act"] == "ajuda":
            assert d == {**a, "ajuda": True}
        elif c["act"] == "ajuda-fechar":
            assert d == {**a, "ajuda": False}
        else:
            assert c["rot"] == "clique fora da ajuda" and a["ajuda"] is True and d == {**a, "ajuda": False}
    por = {c["rot"]: c for c in saida["cliques"]}
    solta = por["chip mata-mata solta o clube que nao jogou nela"]
    assert solta["antes"]["clube"] == saida["foraDoMata"] and solta["depois"] == {"fase": "m", "clube": None, "ajuda": False}
    mantem = por["chip mata-mata mantem o clube"]
    assert mantem["antes"]["clube"] == saida["noMata"] and mantem["depois"]["clube"] == saida["noMata"]
    assert saida["foraDoMata"] not in jogam["m"] and saida["noMata"] in jogam["m"]
    assert saida["clubeInexistente"] == saida["clubeSemId"] == saida["clubeTexto"] == saida["faseProto"] == saida["faseInvalida"] == {"fase": "t", "clube": None, "ajuda": False}
    assert saida["clubeForaDaFase"] == {"fase": "m", "clube": None, "ajuda": False}


@precisa_dados
@precisa_node
def test_teclas_esc_e_backspace_soltam_primeiro_o_clube_depois_a_fase_e_a_ajuda_fecha_antes(saida):
    t = {x["rot"]: x for x in saida["teclas"]}
    no = saida["noMata"]
    livre = {"fase": "t", "clube": None, "ajuda": False}
    assert t["esc sem nada"]["tratou"] is False and t["esc sem nada"]["estado"] == livre
    assert t["esc solta o clube primeiro"]["antes"] == {"fase": "m", "clube": no, "ajuda": False} and t["esc solta o clube primeiro"]["estado"] == {"fase": "m", "clube": None, "ajuda": False}
    assert t["esc depois solta a fase"]["tratou"] is True and t["esc depois solta a fase"]["estado"] == livre and t["esc de novo nao trata"]["tratou"] is False
    assert t["backspace solta o clube"]["antes"] == {"fase": "p", "clube": no, "ajuda": False} and t["backspace solta o clube"]["estado"] == {"fase": "p", "clube": None, "ajuda": False}
    assert t["backspace solta a fase"]["tratou"] is True and t["backspace solta a fase"]["estado"] == livre
    assert (t["abre com ?"]["tratou"], t["abre com ?"]["estado"]["ajuda"]) == (True, True) and (t["esc fecha a ajuda"]["tratou"], t["esc fecha a ajuda"]["estado"]["ajuda"]) == (True, False)
    assert t["h abre"]["estado"]["ajuda"] is True and t["enter fecha"]["estado"]["ajuda"] is False
    assert t["h com ctrl nao abre"]["tratou"] is False and t["outra tecla"]["tratou"] is False
    assert t["esc com ajuda e clube fecha so a ajuda"]["antes"] == {"fase": "m", "clube": no, "ajuda": True} and t["esc com ajuda e clube fecha so a ajuda"]["estado"] == {"fase": "m", "clube": no, "ajuda": False}
    assert t["backspace com ajuda aberta nao solta"]["tratou"] is False and t["backspace com ajuda aberta nao solta"]["estado"] == {"fase": "m", "clube": no, "ajuda": True}
    assert t["espaco fecha a ajuda"]["tratou"] is True and t["espaco fecha a ajuda"]["estado"] == {"fase": "m", "clube": no, "ajuda": False}
    assert saida["teclaNoDocumento"] == {"escPrevenido": True, "clubeDepoisDoEsc": None, "escondidoPrevenido": False, "clubeEscondido": no}


@precisa_dados
@precisa_node
def test_toda_dica_abre_com_titulo_sem_texto_estragado_nem_nome_interno(saida):
    tips = saida["tips"]
    assert len(tips) > 300 and saida["tipEscondeAoSair"] is True
    for t in tips:
        assert t["visivel"] is True and t["html"] == t["tipHtml"] and t["html"].startswith("<b>") and t["tip"].split("||")[0], t["rot"]
        assert not re.search(r"NaN|undefined|Infinity|\[object|null", t["tip"]), t["tip"][:80]
        for ruim in INTERNOS:
            assert ruim not in t["tip"], (ruim, t["tip"][:80])
    assert {t["rot"] for t in tips} >= {"kpis", "p1", "p2", "p3", "p4", "p5", "controles", "rodape", "cabecalho"}


@precisa_dados
@precisa_node
def test_dica_escapa_html_e_monta_titulo_tabela_paragrafo_e_nota(saida):
    assert saida["tipHtml"]["completo"] == '<b>Título</b><div class="tv"><div><span>A</span><em>1</em></div><div><span>B</span><em>2</em></div></div><span>Parágrafo</span><small>Nota</small>'
    assert saida["tipHtml"]["escapado"] == "<b>&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;</b>"


@precisa_dados
@precisa_node
def test_sem_escudos_a_tela_cai_para_a_sigla_colorida(montagem):
    s = rodar(montagem, "semlogos")
    t = estado_de(s, "t", None)
    assert not any(e["ruim"] for e in s["estados"])
    assert t["paineis"][2].count("<img") == 0 and t["paineis"][2].count('class="sg"') == 111 and t["paineis"][3].count("<img") == 0 and t["paineis"][3].count('class="sg"') == 16
    com = estado_de(rodar(montagem), "t", None)
    assert com["paineis"][2].count("<img") == 111 and com["paineis"][3].count("<img") == 16
