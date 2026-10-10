import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
PROTO = RAIZ / "prototype"
precisa_dados = pytest.mark.skipif(not (PROC / "resultado_regra.csv").exists() or not (PROC / "fato_inconsistencia.csv").exists() or not (PROC / "ref_indicadores.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
ORDEM_STATUS = ["aberta", "explicada", "aceita", "corrigida"]
ROTULO_RES = {"t": "Todas", "ok": "Sem ocorr.", "explicada": "Explicadas", "aberta": "Abertas", "info": "Info"}
ROTULO_ST = {"t": "Todas", "aberta": "Abertas", "explicada": "Explicadas", "aceita": "Aceitas", "corrigida": "Corrigidas"}
RESPL = {"ok": "sem ocorrência", "explicada": "explicadas", "aberta": "abertas", "info": "informativas"}
NOME_RES = {"ok": "Sem ocorrência", "explicada": "Explicada", "aberta": "Aberta", "info": "Informativa"}
INTERNOS = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")


def carregar(nome, arq):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sem_tags(t):
    return re.sub(r"<[^>]*>", "", t)


def decod(t):
    return t.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def plural(n, u, p):
    return f"{n:,}".replace(",", ".") + " " + (u if n == 1 else p)


@pytest.fixture(scope="module")
def tab():
    return {"regras": ler_csv(PROC / "resultado_regra.csv"), "ocorr": ler_csv(PROC / "fato_inconsistencia.csv")}


@pytest.fixture(scope="module")
def montagem(tmp_path_factory):
    m = carregar("montar_app13_conf", "13_montar_app.py")
    conf = m.montar_dados_conf()
    frag = (PROTO / "conferencia" / "fragmento.html").read_text(encoding="utf-8").replace("__DADOS__", m.dados_json(conf))
    pasta = tmp_path_factory.mktemp("conf")
    (pasta / "conferencia.html").write_text(m.pagina("t", frag), encoding="utf-8")
    return {"m": m, "conf": conf, "frag": frag, "pasta": pasta}


@pytest.fixture(scope="module")
def saida(montagem):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_conf.js"), str(montagem["pasta"] / "conferencia.html")], capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr[-1500:]
    s = json.loads(proc.stdout)
    assert not s.get("semGancho")
    return s


# ---------- pacote de dados ----------

@precisa_dados
def test_pacote_traz_as_45_regras_e_as_46_ocorrencias_do_log(montagem, tab):
    d = montagem["conf"]
    assert [r["c"] for r in d["reg"]] == [r["codigo"] for r in tab["regras"]] and len(d["reg"]) == 45
    assert [o["i"] for o in d["oc"]] == [o["id_inconsistencia"] for o in tab["ocorr"]] and len(d["oc"]) == 46
    for r, c in zip(d["reg"], tab["regras"]):
        assert (r["v"], r["o"], r["r"], r["s"]) == (int(c["verificados"]), int(c["ocorrencias"]), c["resultado"], c["severidade"])
    for o, c in zip(d["oc"], tab["ocorr"]):
        assert (o["r"], o["st"], o["sv"]) == (c["codigo_regra"], c["status"], c["severidade"])
        assert d["tx"][o["x"]] == montagem["m"].amigavel(c["explicacao"])
    assert len(d["tx"]) == len(set(d["tx"])) < len(d["oc"])  # a mesma explicação (cartões da ESPN) não se repete


@precisa_dados
def test_resumo_do_pacote_bate_com_as_tabelas(montagem, tab):
    meta = montagem["conf"]["meta"]
    res = Counter(r["resultado"] for r in tab["regras"])
    st = Counter(o["status"] for o in tab["ocorr"])
    assert (meta["regras"], meta["ok"], meta["expl"], meta["aber"], meta["info"]) == (45, res["ok"], res["explicada"], res["aberta"], res["info"]) == (45, 35, 7, 2, 1)
    assert meta["ocorr"] == 46 and meta["st"] == dict(st) == {"explicada": 41, "aceita": 2, "corrigida": 1, "aberta": 2}
    assert meta["itens"] == sum(int(r["verificados"]) for r in tab["regras"]) == 9056
    por = {r["codigo"]: r for r in tab["regras"]}
    assert meta["placar"] == [72, 72] and meta["classif"] == [16, 16]
    assert "Placar final: súmula x tabela da FPF" in por["A22"]["titulo"] and "Art. 16" in por["A19"]["titulo"]
    assert [r["c"] for r in montagem["conf"]["reg"] if r["r"] == "aberta"] == ["A32", "A33"]
    assert sorted(o["i"] for o in montagem["conf"]["oc"] if o["st"] == "aberta") == ["A32-001", "A33-001"]


@precisa_dados
def test_datas_do_pacote_nao_incluem_a_hora_de_geracao_das_tabelas(montagem):
    meta = montagem["conf"]["meta"]
    assert (meta["pdf"], meta["espn"], meta["fpf"]) == ("2026-10-06", "2026-10-06", "2026-03-09")
    assert "gerado" not in json.dumps(montagem["conf"]).lower()  # a hora de cada geração mudaria o texto a cada rodada do ETL


@precisa_dados
def test_a_correcao_documentada_mostra_valor_original_e_corrigido(montagem):
    c, = montagem["conf"]["cor"]
    assert (c["i"], c["c"], c["de"], c["para"]) == ("C01", "minuto", "60", "76")
    assert c["t"].startswith("Jogo 15: ") and "Corinthians" in c["t"] and c["f"] == ["Gazeta Esportiva", "Trivela", "ESPN"]
    assert "Mosquera" in c["d"] and "súmula" in c["x"] and not any(i in c["x"] for i in INTERNOS)


@precisa_dados
def test_texto_nenhum_do_pacote_cita_arquivo_tabela_ou_pasta_internos(montagem):
    for texto in montagem["m"].texto_do_pacote(montagem["conf"]):
        for ruim in INTERNOS:
            assert ruim not in texto, (ruim, texto[:80])
    for r in montagem["conf"]["reg"]:
        assert "{" not in r["x"] and "'" not in r["x"]


@precisa_dados
def test_o_montador_para_se_um_texto_voltar_a_citar_nome_interno(montagem, monkeypatch):
    m = montagem["m"]
    monkeypatch.setattr(m, "AMIGAVEL", [])
    with pytest.raises(SystemExit, match="cita"):
        m.montar_dados_conf()


@precisa_dados
def test_o_montador_para_se_as_camadas_ficarem_velhas_em_relacao_aos_dados(montagem, monkeypatch):
    m = montagem["m"]
    real = m.contagens_para_camadas()
    assert real == {"tabelas": 23, "colunas": 271, "relacionamentos": 39, "medidas": 72, "gabarito": 586, "clubes": 16, "jogos": 72}
    for campo in ("colunas", "gabarito", "relacionamentos", "medidas"):
        monkeypatch.setattr(m, "contagens_para_camadas", lambda c=campo: {**real, c: real[c] + 1})
        with pytest.raises(SystemExit, match="CAMADAS desatualizadas"):
            m.montar_dados_conf()


@precisa_dados
def test_camadas_trazem_as_oito_conferencias_com_o_resultado_e_a_data(montagem):
    cam = montagem["conf"]["cam"]
    assert [c["n"] for c in cam] == ["Fontes entre si", "Tabelas tratadas", "Planilha no Excel", "Carga no Power BI", "Relacionamentos", "Medidas × gabarito", "Medidas × tabela FPF", "Boletins × outro leitor"]
    assert cam[0]["r"] == "45 regras"
    c = montagem["m"].contagens_para_camadas()
    assert cam[2]["r"] == "610 de 610" and "610 conferências" in cam[2]["d"]
    assert cam[3]["r"] == f"{c['colunas']} de {c['colunas']} colunas" and f"{c['colunas']} colunas das {c['tabelas']} tabelas" in cam[3]["d"]
    assert cam[4]["r"] == f"{c['relacionamentos']}, sem caminho duplo" and f"Os {c['relacionamentos']} relacionamentos" in cam[4]["d"]
    assert cam[5]["r"] == f"{c['gabarito']} de {c['gabarito']} linhas" and f"As {c['medidas']} medidas" in cam[5]["d"] and f"{c['gabarito']} de {c['gabarito']} iguais" in cam[5]["d"]
    assert cam[6]["r"] == f"{c['clubes']} de {c['clubes']} clubes"
    assert cam[7]["r"] == f"{c['jogos']} de {c['jogos']} jogos" and f"{c['jogos']} de {c['jogos']}" in cam[7]["d"]
    assert [c["q"] for c in cam if c["q"]] == ["09/10/2026"] + ["08/10/2026"] * 5
    assert all(c["d"] and c["r"] for c in cam)


@precisa_dados
def test_fontes_separam_oficial_nao_oficial_e_projeto(montagem):
    fon = montagem["conf"]["fon"]
    assert [f["k"] for f in fon] == ["o", "o", "o", "o", "n", "p"]
    assert "ESPN" in fon[4]["f"] and "não oficial" in fon[4]["f"] and "pênaltis do jogo 68" in fon[4]["d"] and "o da súmula" in fon[4]["d"]
    assert "ESPN" not in " ".join(f["t"] + f["f"] for f in fon[:4])


# ---------- montagem da tela ----------

@precisa_dados
def test_fragmento_nao_deixa_marca_sobrando_e_so_age_quando_visivel(montagem):
    frag = montagem["frag"]
    assert not re.search(r"__[A-Z_]+__", frag)
    src = (PROTO / "conferencia" / "fragmento.html").read_text(encoding="utf-8")
    assert src.count("__DADOS__") == 1 and "height:100%;min-height:320px" in src and "if(!raiz.offsetParent)return;" in src
    assert "window.PA.mods.conf={entrar:entrar}" in src and 'id="cnx"' in src
    for ruim in INTERNOS:
        assert ruim not in src, ruim


@precisa_dados
def test_textos_da_tela_sao_todos_de_pelo_menos_16_pixels():
    src = (PROTO / "conferencia" / "fragmento.html").read_text(encoding="utf-8")
    tamanhos = [int(x) for x in re.findall(r"font-size:(\d+)px", src)] + [int(x) for x in re.findall(r"font:[^;{}]*?(\d+)px", src)]
    assert tamanhos and min(tamanhos) >= 16, sorted(set(tamanhos))


@precisa_dados
def test_pagina_do_app_leva_o_modulo_com_os_dados_e_o_selo_vira_botao_da_conferencia():
    m = carregar("montar_app13_pg", "13_montar_app.py")
    dados = m.montar_todos_os_dados()
    conf = dados["conf"]
    frag = m.montar_fragmentos(dados)
    frag_conf, app = frag["conf"], frag["app"]
    assert not re.search(r"__[A-Z_]+__", app)
    assert app.count('id="cnx"') == 1 and app.count('<section class="mod" id="mod-conf">') == 1
    assert m.dados_json(conf) in app and frag_conf in app
    assert '<button class="selo" data-mod="conf"' in app and "Clique para ver a tela de conferência." in app and "a construir" not in app
    assert '<button data-mod="conf"><span>Conferência</span></button>' in app
    codigo = m.montar_codigo_app(conf["meta"])
    assert all(codigo.count(marca) == 1 for marca in ("__DADOS_CONF__", "__DADOS_VS__", "__DADOS_FIN__", "__DADOS_CLAS__", "__DADOS_VG__", "__DADOS_GL__", "__DADOS_DS__", "__DADOS_JG__"))


# ---------- comportamento (módulo simulado em Node) ----------

def esperado_combo(tab, res, st, sel):
    regras = [r["codigo"] for r in tab["regras"] if res == "t" or r["resultado"] == res]
    resultado = {r["codigo"]: r["resultado"] for r in tab["regras"]}
    base = [o for o in tab["ocorr"] if (o["codigo_regra"] == sel if sel else res == "t" or resultado[o["codigo_regra"]] == res)]
    oc = [o for o in base if st == "t" or o["status"] == st]
    oc.sort(key=lambda o: (ORDEM_STATUS.index(o["status"]), o["id_inconsistencia"]))
    conta_st = Counter(o["status"] for o in base)
    conta_st["t"] = len(base)
    conta_res = Counter(r["resultado"] for r in tab["regras"])
    conta_res["t"] = len(tab["regras"])
    return regras, [o["id_inconsistencia"] for o in oc], conta_res, conta_st, oc


@precisa_dados
@precisa_node
def test_cada_combinacao_de_filtro_e_regra_mostra_as_linhas_certas(saida, tab):
    assert len(saida["combos"]) == 5 * 5 * 46
    por_codigo = {r["codigo"]: r for r in tab["regras"]}
    resultado_da = {r["codigo"]: r["resultado"] for r in tab["regras"]}
    for c in saida["combos"]:
        f = c["f"]
        regras, ids, conta_res, conta_st, oc = esperado_combo(tab, f["res"], f["st"], f["sel"])
        assert c["regras"] == regras and c["ocorr"] == ids, f
        assert c["linhasRegras"] == len(regras) and c["linhasOcorr"] == len(ids) and c["linhasSel"] == (1 if f["sel"] in regras else 0), f
        for k in ("t", "ok", "explicada", "aberta", "info"):
            assert c["contaRes"].get(k, 0) == conta_res.get(k, 0), (f, k)
        for k in ("t", "aberta", "explicada", "aceita", "corrigida"):
            assert c["contaSt"].get(k, 0) == conta_st.get(k, 0), (f, k)
        assert c["abertasComTexto"] == sum(1 for o in oc if o["status"] == "aberta"), f
        assert [x for x, ligado in c["chipsRes"] if ligado] == [f["res"]] and len(c["chipsRes"]) == 5, f
        assert [x for x, ligado in c["chipsSt"] if ligado] == [f["st"]] and len(c["chipsSt"]) == 5, f
        assert c["tituloP1"] == plural(len(regras), "regra", "regras") and c["ruim"] is False, f
        assert c["tituloP2"] == plural(len(ids), "ocorrência", "ocorrências") + (f" · regra {f['sel']}" if f["sel"] else f" · regras {RESPL[f['res']]}" if f["res"] != "t" else ""), f
        assert c["temFiltro"] == c["limparVisivel"] == bool(f["sel"] or f["res"] != "t" or f["st"] != "t"), f
        if ids:
            assert c["vazio"] is None, f
        elif f["sel"] and not any(o["codigo_regra"] == f["sel"] for o in tab["ocorr"]):
            r = por_codigo[f["sel"]]
            assert f"Regra {f['sel']} sem ocorrência." in c["vazio"] and ("O item verificado bateu." if r["verificados"] == "1" else f"Os {int(r['verificados']):,}".replace(",", ".") + " itens verificados bateram.") in c["vazio"], f
        elif not f["sel"] and not any(resultado_da[o["codigo_regra"]] == f["res"] for o in tab["ocorr"]):
            assert f"As regras {RESPL[f['res']]} não têm ocorrência." in c["vazio"], f
        else:
            assert "Nenhuma ocorrência com este status" in c["vazio"], f


@precisa_dados
@precisa_node
def test_ocorrencias_abertas_vem_antes_das_demais_e_so_elas_mostram_o_texto_inteiro(saida, tab):
    c = next(x for x in saida["combos"] if x["f"] == {"res": "t", "st": "t", "sel": None})
    assert c["ocorr"][:2] == ["A32-001", "A33-001"] and c["abertasComTexto"] == 2 and len(c["ocorr"]) == 46
    estados = [next(o["status"] for o in tab["ocorr"] if o["id_inconsistencia"] == i) for i in c["ocorr"]]
    assert estados == sorted(estados, key=ORDEM_STATUS.index)


@precisa_dados
@precisa_node
def test_sete_quadros_com_os_numeros_das_tabelas(saida, tab):
    res = Counter(r["resultado"] for r in tab["regras"])
    st = Counter(o["status"] for o in tab["ocorr"])
    itens = sum(int(r["verificados"]) for r in tab["regras"])
    por = {r["codigo"]: r for r in tab["regras"]}
    abertas = " e ".join(r["codigo"] for r in tab["regras"] if r["resultado"] == "aberta")
    informativas = ", ".join(r["codigo"] for r in tab["regras"] if r["resultado"] == "info")
    decididas = len(tab["ocorr"]) - st["aberta"]
    a22, a19 = por["A22"], por["A19"]
    assert saida["kpis"] == [
        ["Regras", "45", "", f"{itens:,}".replace(",", ".") + " itens verificados"],
        ["Sem ocorrência", str(res["ok"]), "", f"{round(100 * res['ok'] / 45)}% das regras"],
        ["Explicadas", str(res["explicada"]), "", f"{decididas} ocorrências decididas"],
        ["Em aberto", str(res["aberta"]), "", abertas],
        ["Informativa", str(res["info"]), "", f"{informativas} · não é erro"],
        ["Placares × FPF", str(int(a22["verificados"]) - int(a22["ocorrencias"])), f"de {a22['verificados']}", "jogos iguais à FPF"],
        ["Posições × FPF", str(int(a19["verificados"]) - int(a19["ocorrencias"])), f"de {a19['verificados']}", "clubes na mesma posição"],
    ]
    assert saida["kpiTips"] == 7
    notas = re.findall(r'class="kpi"[^>]*data-tip="([^"]*)"', saida["render"]["kpis"])
    assert len(notas) == 7 and all("os filtros da tela não mudam este número" in decod(n) for n in notas)


@precisa_dados
@precisa_node
def test_paineis_da_direita_e_cabecalho_trazem_o_conteudo_do_pacote(saida, montagem):
    r, d = saida["render"], montagem["conf"]
    assert (r["fontes"], r["camadas"], r["correcoes"]) == (6, 8, 1)
    assert r["sub"] == "PDFs oficiais coletados em 06/10/2026 · tabela da FPF de 09/03/2026 · ESPN de 06/10/2026"
    assert "conferidos por 45 regras" in r["rod"] and "(2 pendências abertas)" in r["rod"]
    for cam in d["cam"]:
        assert cam["n"] in r["p4"] and cam["r"] in r["p4"]
    for f in d["fon"]:
        assert f["t"] in r["p3"]
    assert "60'" in r["p5"] and "76'" in r["p5"] and "Gazeta Esportiva, Trivela, ESPN" in r["p5"]
    assert "Como ler esta tela" in r["aj"] and "Passo a passo" in r["aj"]
    assert 'data-act="limpar"' in r["ctl"] and "lim off" in r["ctl"] and 'data-act="ajuda"' in r["ctl"]
    assert not re.search(r"NaN|undefined|\[object", " ".join(str(v) for v in r.values()))


@precisa_dados
@precisa_node
def test_cada_regra_mostra_codigo_titulo_resultado_e_a_conta_de_ocorrencias(saida, tab):
    p1 = saida["render"]["p1"]
    linhas = re.findall(r'<button class="rr[^"]*"[^>]*data-id="(\w+)"[^>]*>(.*?)</button>', p1)
    assert [c for c, _ in linhas] == [r["codigo"] for r in tab["regras"]]
    m = carregar("montar_app13_tx", "13_montar_app.py")
    for (cod, corpo), r in zip(linhas, tab["regras"]):
        assert sem_tags(corpo).startswith(cod) and decod(re.search(r"<u>(.*?)</u>", corpo).group(1)) == m.amigavel(r["titulo"])
        rotulo = re.search(r'<span class="rc (\w+)">([^<]*)</span>', corpo)
        assert rotulo.group(2) == NOME_RES[r["resultado"]] + (f" · {r['ocorrencias']}" if int(r["ocorrencias"]) else "")
    tips = re.findall(r'class="rr[^"]*"[^>]*data-tip="([^"]*)"', p1)
    assert len(tips) == 45 and all("Itens verificados" in decod(t) and "Clique para ver só as ocorrências desta regra." in decod(t) for t in tips)


@precisa_dados
@precisa_node
def test_cada_ocorrencia_mostra_id_status_fontes_e_a_explicacao_na_dica(saida, tab, montagem):
    p2 = saida["render"]["p2"]
    m, conf = montagem["m"], montagem["conf"]
    titulo = {r["codigo"]: m.amigavel(r["titulo"]) for r in tab["regras"]}
    pares = re.findall(r'<div class="oc[^"]*" tabindex="0"[^>]*data-tip="([^"]*)"><div class="l1"><b>([^<]*)</b><span class="rc (\w+)">([^<]*)</span>', p2)
    assert len(pares) == 46 and {i for _, i, _, _ in pares} == {o["id_inconsistencia"] for o in tab["ocorr"]}
    por_id = {o["id_inconsistencia"]: o for o in tab["ocorr"]}
    rotulo_st = {"aberta": "Aberta", "explicada": "Explicada", "aceita": "Aceita", "corrigida": "Corrigida"}
    for tip, i, _, rotulo in pares:
        o, t = por_id[i], decod(tip)
        assert t.startswith(f"{i} · {titulo[o['codigo_regra']]}||") and rotulo == rotulo_st[o["status"]]
        assert m.amigavel(o["explicacao"]) in t and f"Status::{rotulo_st[o['status']]}" in t and "Gravidade::" in t
        assert ("Fonte A::" in t and "Fonte B::" in t) != ("Dado::" in t)
        assert ("Fonte B::" in t) == (o["fonte_b"] != "total"), i
    assert len(conf["oc"]) == 46


def modelo(estado, acao, id_, v, resultado):
    """Regra de filtro escrita à parte, só com o que a tela promete: o resultado vale para as duas listas e solta a regra que ficou de fora; escolher regra alterna, zera o status e ignora regra que não aparece."""
    e = dict(estado)
    if acao == "res":
        e["res"] = v
        if e["sel"] and v != "t" and resultado[e["sel"]] != v:
            e["sel"] = None
    elif acao == "st":
        e["st"] = v
    elif acao == "regra":
        if id_ not in resultado or (e["res"] != "t" and resultado[id_] != e["res"]):
            return e
        e["sel"] = None if e["sel"] == id_ else id_
        e["st"] = "t"
    elif acao == "limpar":
        e = {"res": "t", "st": "t", "sel": None}
    return e


@precisa_dados
@precisa_node
def test_acoes_e_estado_depois_de_cada_passo(saida, tab):
    resultado = {r["codigo"]: r["resultado"] for r in tab["regras"]}
    estado = {"res": "t", "st": "t", "sel": None}
    assert len(saida["acoes"]) == 29
    for a in saida["acoes"]:
        acao, id_, v = a["passo"]
        estado = modelo(estado, acao, id_, v, resultado)
        assert a["estado"] == estado, a["passo"]
        assert a["temFiltro"] == bool(estado["sel"] or estado["res"] != "t" or estado["st"] != "t"), a["passo"]
    passos = [a["passo"] for a in saida["acoes"]]
    assert ["regra", "A12", None] in passos and ["regra", "A01", None] in passos and ["regra", "XXX", None] in passos
    # regra que não aparece no resultado escolhido é ignorada; o resultado que a inclui mantém a regra; o que a exclui solta
    assert [a["estado"]["sel"] for a in saida["acoes"][4:7]] == [None, None, None]
    assert [(a["estado"]["res"], a["estado"]["sel"]) for a in saida["acoes"][15:18]] == [("t", "A12"), ("explicada", "A12"), ("aberta", None)]
    assert [(a["estado"]["res"], a["estado"]["sel"]) for a in saida["acoes"][19:21]] == [("t", "A33"), ("t", "A33")]


@precisa_dados
@precisa_node
def test_cliques_nos_botoes_gerados_fazem_o_que_o_rotulo_diz(saida, tab):
    m = carregar("montar_app13_cl", "13_montar_app.py")
    titulo = {r["codigo"]: m.amigavel(r["titulo"]) for r in tab["regras"]}
    resultado = {r["codigo"]: r["resultado"] for r in tab["regras"]}
    assert set(saida["acoesVistas"]) == {"res", "regra", "st", "limpar", "ajuda", "ajuda-fechar"}
    assert len(saida["cliques"]) == 5 + 4 + 4 + 5 + 1 + 1 + 1 + 1 + 1 + 1
    for c in saida["cliques"]:
        a, d = c["antes"], c["depois"]
        antes_filtros = {k: a[k] for k in ("res", "st", "sel")}
        depois_filtros = {k: d[k] for k in ("res", "st", "sel")}
        if c["act"] in ("res", "st", "regra", "limpar"):
            assert depois_filtros == modelo(antes_filtros, c["act"], c["id"], c["v"], resultado), c["rot"]
            assert d["ajuda"] == a["ajuda"]
        if c["act"] == "res":
            assert ROTULO_RES[c["v"]] == c["rotulo"], c["rot"]
        elif c["act"] == "st":
            assert ROTULO_ST[c["v"]] == c["rotulo"], c["rot"]
        elif c["act"] == "regra":
            assert c["rotulo"].startswith(c["id"]) and titulo[c["id"]] in c["rotulo"], c["rot"]
        elif c["act"] == "limpar":
            assert c["rotulo"] == "Limpar"
        elif c["act"] == "ajuda":
            assert d["ajuda"] is True and depois_filtros == antes_filtros
        elif c["act"] == "ajuda-fechar":
            assert d["ajuda"] is False and c["rotulo"] == "Entendi"
        else:
            assert c["rot"] == "clique fora da ajuda" and a["ajuda"] is True and d["ajuda"] is False
    soltou = next(c for c in saida["cliques"] if c["rot"] == "chip regras aberta (solta A12)")
    assert soltou["antes"]["sel"] == "A12" and soltou["depois"]["sel"] is None
    manteve = next(c for c in saida["cliques"] if c["rot"] == "chip regras explicada (mantem A12)")
    assert manteve["antes"]["sel"] == "A12" and manteve["depois"]["sel"] == "A12"


@precisa_dados
@precisa_node
def test_teclas_esc_solta_a_regra_depois_os_filtros_e_a_ajuda_fecha_primeiro(saida):
    t = saida["tecla"]
    assert t[0] == {"semFiltro": False, "estado": {"res": "t", "st": "t", "sel": None}}
    assert t[1]["antes"] == {"res": "aberta", "st": "t", "sel": "A32"} and t[1]["tratou"] is True and t[1]["depois"] == {"res": "aberta", "st": "t", "sel": None}
    assert t[2]["tratou"] is True and t[2]["depois"] == {"res": "t", "st": "t", "sel": None}
    assert t[3]["tratou"] is False and t[3]["depois"] == t[3]["antes"]
    assert t[4] == {"abrir": True, "aberta": True, "fechou": True, "fechada": True, "hComCtrl": False, "outra": False}
    assert t[5] == {"ajudaAbertaComFiltro": True, "escFechaSoAAjuda": True, "selDepois": "A12", "fechada": True}


@precisa_dados
@precisa_node
def test_dica_escapa_html_e_monta_titulo_tabela_paragrafo_e_nota(saida):
    assert saida["tipHtml"]["completo"] == '<b>Título</b><div class="tv"><div><span>A</span><em>1</em></div><div><span>B</span><em>2</em></div></div><span>Parágrafo</span><small>Nota</small>'
    assert saida["tipHtml"]["escapado"] == "<b>&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;</b>"
