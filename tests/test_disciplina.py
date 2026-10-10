import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unicodedata
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
REF = RAIZ / "data" / "referencia"
precisa_dados = pytest.mark.skipif(not all((PROC / n).exists() for n in ("fato_partida.csv", "fato_evento.csv", "ref_indicadores.csv", "dim_fase.csv", "dim_arbitro.csv")), reason="rode scripts/04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(not shutil.which("node"), reason="Node não instalado")
INTERNOS = ("fato_", "dim_", "aux_", "ref_", ".csv", "scripts/", "data/", ".py")
FS = {"t": "Todas as fases", "p": "1ª fase", "m": "Mata-mata"}
COD_FASE = {"PRIMEIRA FASE": 1, "QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}
NOME_FAIXA = ["1 a 15", "16 a 30", "31 a 45", "46 a 60", "61 a 75", "76 a 90 e acréscimos"]
CARTOES = {"amarelo": "a", "vermelho": "v", "segundo_amarelo": "s"}
POR_CATEGORIA = {"Ação temerária": 181, "Impedir ataque promissor ou gol": 73, "Atitude antidesportiva": 68, "Reclamar ou desrespeitar a arbitragem": 45, "Retardar o jogo": 28, "Conduta violenta ou força excessiva": 13, "Infração repetida": 5, "Outros": 0}


def carregar(nome, arq):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


disc = carregar("disciplina_teste", "disciplina.py")


def decod(t):
    return t.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def fmt(n, c=0):
    v = Decimal(n).quantize(Decimal(1).scaleb(-c), rounding=ROUND_HALF_UP)
    return f"{v:,.{c}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def plural(n, u, p):
    return f"{fmt(n)} " + (u if n == 1 else p)


def pct(a, b):
    return fmt(Decimal(100 * a) / b, 1) + "%" if b > 0 else "—"


def data_br(d):
    a, m, dia = d.split("-")
    return f"{dia}/{m}"


def faixa(mn):
    return 0 if mn <= 15 else 1 if mn <= 30 else 2 if mn <= 45 else 3 if mn <= 60 else 4 if mn <= 75 else 5


def tabela_tip(secao):
    assert secao.startswith("@"), secao[:60]
    return [tuple(x.split("::")) for x in secao[1:].split("\n")]


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if not unicodedata.combining(c)).lower()


# ---------- regras de motivo (scripts/disciplina.py) ----------

def escrever(tmp_path, linhas, cabecalho="ordem_regra;categoria;ordem_exibicao;condicao;expressao;explicacao"):
    arq = tmp_path / "motivos.csv"
    arq.write_text("\n".join([cabecalho] + linhas) + "\n", encoding="utf-8")
    return arq


BOAS = ["1;Grave;2;texto;violen|brusco;Explica A", "2;Comum;1;texto;temerari;Explica B", "3;Outros;3;resto;;Explica C"]


def test_regras_validas_leem_em_ordem_e_a_categoria_de_exibicao_vem_a_parte(tmp_path):
    regras = disc.ler_regras_motivo(escrever(tmp_path, BOAS))
    assert [r["categoria"] for r in regras] == ["Grave", "Comum", "Outros"]
    assert [r["categoria"] for r in disc.categorias_em_ordem(regras)] == ["Comum", "Grave", "Outros"]


def test_regras_fora_de_ordem_no_arquivo_sao_ordenadas_pelo_numero_da_regra(tmp_path):
    regras = disc.ler_regras_motivo(escrever(tmp_path, ["3;Outros;3;resto;;C", "2;Comum;1;texto;temerari;B", "1;Grave;2;texto;violen;A"]))
    assert [r["ordem_regra"] for r in regras] == [1, 2, 3] and regras[-1]["condicao"] == "resto"


@pytest.mark.parametrize("linhas,trecho", [
    (["1;A;1;texto;x;e", "2;B;2;talvez;;e", "3;Outros;3;resto;;e"], "condição 'talvez'"),
    (["1;A;1;texto;;e", "2;Outros;2;resto;;e"], "sem expressão"),
    (["1;A;1;texto;x;e", "2;Outros;2;resto;sobra;e"], "não usa expressão"),
    (["1;A;1;texto;x;e", "2;B;2;texto;y;e"], "última regra"),
    (["1;Outros;1;resto;;e", "2;A;2;texto;x;e"], "última regra"),
    (["1;A;1;texto;x;e", "2;Outros;2;resto;;e", "3;Mais;3;resto;;e"], "última regra"),
    (["1;A;1;texto;x;e", "1;B;2;texto;y;e", "3;Outros;3;resto;;e"], "ordem_regra repetido"),
    (["1;A;1;texto;x;e", "2;A;2;texto;y;e", "3;Outros;3;resto;;e"], "categoria repetido"),
    (["1;A;1;texto;x;e", "2;B;1;texto;y;e", "3;Outros;3;resto;;e"], "ordem_exibicao repetido"),
    (["1;A;1;texto;(aberto;e", "2;Outros;2;resto;;e"], "expressão inválida"),
    (["um;A;1;texto;x;e", "2;Outros;2;resto;;e"], "números inteiros"),
    (["1;A;;texto;x;e", "2;Outros;2;resto;;e"], "números inteiros"),
    (["1;;1;texto;x;e", "2;Outros;2;resto;;e"], "categoria não pode ficar vazia"),
    ([], "pelo menos uma regra"),
])
def test_arquivo_de_regras_com_erro_para_com_a_linha_certa(tmp_path, linhas, trecho):
    with pytest.raises(ValueError, match=re.escape(trecho)):
        disc.ler_regras_motivo(escrever(tmp_path, linhas))


def test_arquivo_sem_uma_coluna_nao_e_aceito(tmp_path):
    with pytest.raises(ValueError, match="colunas"):
        disc.ler_regras_motivo(escrever(tmp_path, ["1;A;1;texto;x"], cabecalho="ordem_regra;categoria;ordem_exibicao;condicao;expressao"))


def test_erro_de_linha_conta_a_partir_da_segunda_linha_do_arquivo(tmp_path):
    with pytest.raises(ValueError, match="linha 3"):
        disc.ler_regras_motivo(escrever(tmp_path, ["1;A;1;texto;x;e", "2;B;2;talvez;;e", "3;Outros;3;resto;;e"]))


def test_classificar_usa_a_primeira_regra_que_casa_ignora_acento_e_caixa_e_cai_no_resto(tmp_path):
    regras = disc.ler_regras_motivo(escrever(tmp_path, BOAS))
    c = lambda t: disc.classificar_motivo(t, regras)["categoria"]
    assert c("Por jogo BRUSCO grave") == "Grave" and c("de maneira TEMERÁRIA") == "Comum" and c("de maneira temeraria") == "Comum"
    assert c("jogo brusco e de maneira temerária") == "Grave", "vale a primeira regra, não a categoria que aparece primeiro na tela"
    assert c("nada a ver") == "Outros" and c("") == "Outros" and c(None) == "Outros" and c("   ") == "Outros"
    assert c("  Ação   TEMERÁRIA  ") == "Comum"


@precisa_dados
def test_regras_reais_cobrem_os_oito_grupos_e_terminam_no_resto():
    regras = disc.ler_regras_motivo()
    assert len(regras) == 8 and regras[-1]["categoria"] == "Outros" and regras[-1]["condicao"] == "resto"
    assert sorted(r["ordem_exibicao"] for r in regras) == list(range(1, 9)) and [r["ordem_regra"] for r in regras] == list(range(1, 9))
    assert [r["categoria"] for r in disc.categorias_em_ordem(regras)][:3] == ["Ação temerária", "Impedir ataque promissor ou gol", "Atitude antidesportiva"]
    for r in regras:
        assert r["explicacao"].strip() and "http" not in r["explicacao"]
        for ruim in INTERNOS:
            assert ruim not in r["explicacao"] and ruim not in r["categoria"], (ruim, r["categoria"])


@precisa_dados
@pytest.mark.parametrize("texto,categoria", [
    ("Ação temerária", "Ação temerária"), ("AÇÃO TEMERÁRIA", "Ação temerária"), ("Por atingir com o braço o rosto de seu adversário de maneira temerária na disputa da bola", "Ação temerária"),
    ("Impedir ataque promissor", "Impedir ataque promissor ou gol"), ("Por cometer uma infração impedindo uma clara oportunidade de gol", "Impedir ataque promissor ou gol"),
    ("Agarrar seu adversário de maneira acintosa impedindo um ataque promissor.", "Impedir ataque promissor ou gol"),
    ("Retardar o reinício do jogo", "Retardar o jogo"), ("Por retardar a saída do campo de jogo no momento da substituição", "Retardar o jogo"),
    ("Infringir persistentemente as regras do jogo", "Infração repetida"),
    ("Discordar das decisões da arbitragem com palavras ou ações", "Reclamar ou desrespeitar a arbitragem"), ("POR RECLAMAR PERSISTENTEMENTE CONTRA AS DECISÕES DA ARBITRAGEM.", "Reclamar ou desrespeitar a arbitragem"),
    ("Por segurar seu adversário de forma acintosa.", "Atitude antidesportiva"), ("Por simulação", "Atitude antidesportiva"), ("Infração na comemoração de gol", "Atitude antidesportiva"),
    ("Por chutar a bandeira de escanteio na comemoração de um gol.", "Atitude antidesportiva"), ("Por trocar empurrões com seu adversário com o jogo paralisado.", "Atitude antidesportiva"),
    ("Por jogo brusco grave, acertando com as travas da chuteira a panturrilha do seu adversário", "Conduta violenta ou força excessiva"), ("Por desferir uma cotovelada no rosto de seu adversário", "Conduta violenta ou força excessiva"),
    ("Por dar um carrinho por trás em seu adversário com uso de força excessiva", "Conduta violenta ou força excessiva"),
    ("Texto que a súmula nunca trouxe", "Outros"), ("", "Outros"),
])
def test_exemplos_de_motivo_caem_no_grupo_esperado_com_as_regras_do_projeto(texto, categoria):
    regras = disc.ler_regras_motivo()
    assert disc.classificar_motivo(texto, regras)["categoria"] == categoria


# ---------- referência recalculada aqui, direto das tabelas tratadas ----------

@pytest.fixture(scope="module")
def ref():
    fases = {f["id_fase"]: COD_FASE[f["nome_fase"]] for f in ler_csv(PROC / "dim_fase.csv")}
    partidas = ler_csv(PROC / "fato_partida.csv")
    eventos = ler_csv(PROC / "fato_evento.csv")
    arbitros = {a["id_arbitro"]: a["nome"] for a in ler_csv(PROC / "dim_arbitro.csv")}
    penaltis = Counter(e["id_partida"] for e in eventos if e["tipo_evento"] == "gol_penalti")
    jogos = []
    for p in sorted(partidas, key=lambda x: (x["data_hora_programada"], int(x["numero_jogo"]))):
        jogos.append({"n": int(p["numero_jogo"]), "f": fases[p["id_fase"]], "r": int(p["rodada"]), "d": p["data_jogo"], "m": int(p["id_clube_mandante"]), "v": int(p["id_clube_visitante"]), "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]),
                      "arb": arbitros[p["id_arbitro"]], "a1": int(p["acrescimo_1t_min"]), "a2": int(p["acrescimo_2t_min"]), "pn": penaltis[p["id_partida"]]})
    numero = {p["id_partida"]: int(p["numero_jogo"]) for p in partidas}
    ordem = {j["n"]: i for i, j in enumerate(jogos)}
    curto = curto_das_pessoas(eventos).__getitem__

    por_pessoa = defaultdict(list)
    for e in eventos:
        if e["tipo_evento"] in CARTOES:
            por_pessoa[(e["id_partida"], e["pessoa"])].append(e)
    regras = sorted(ler_csv(REF / "motivos_cartao.csv"), key=lambda r: int(r["ordem_regra"]))

    def categoria(motivo):
        t = re.sub(r"\s+", " ", sem_acento(motivo or "")).strip()
        for r in regras:
            if r["condicao"] == "texto" and re.search(r["expressao"], t):
                return r["categoria"]
        return regras[-1]["categoria"]

    cartoes = []
    for lista in por_pessoa.values():
        lista = sorted(lista, key=lambda e: e["id_evento"])
        if any(e["tipo_evento"] == "segundo_amarelo" for e in lista):
            primeiro = next(e for e in lista if e["tipo_evento"] == "amarelo")
            lista = [e for e in lista if e is not primeiro]
        for e in lista:
            atleta = e["funcao"] == "Atleta"
            cartoes.append({"j": numero[e["id_partida"]], "mn": int(e["minuto"]) if e["minuto"] != "" else None, "t": CARTOES[e["tipo_evento"]], "c": int(e["id_clube"]), "f": 0 if atleta else 1, "p": e["pessoa"] if atleta else None,
                            "a": curto(e["pessoa"]) if atleta else None, "cat": categoria(e["motivo"]), "motivo": e["motivo"]})
    cartoes.sort(key=lambda x: (ordem[x["j"]], x["mn"] is None, x["mn"] or 0, x["c"], x["t"], x["p"] or ""))
    cats = sorted(regras, key=lambda r: int(r["ordem_exibicao"]))
    return {"jogos": jogos, "cartoes": cartoes, "por_n": {j["n"]: j for j in jogos}, "cats": [(r["categoria"], r["explicacao"]) for r in cats], "motivos": {e["motivo"] for e in eventos if e["tipo_evento"] in CARTOES}}


def jogos_do_recorte(ref, f, c):
    return [j for j in ref["jogos"] if (f == "t" or (f == "p" and j["f"] == 1) or (f == "m" and j["f"] > 1)) and (c is None or c in (j["m"], j["v"]))]


def cartoes_do_recorte(ref, f, c):
    ns = {j["n"] for j in jogos_do_recorte(ref, f, None)}
    return [x for x in ref["cartoes"] if x["j"] in ns and (c is None or x["c"] == c)]


def resumo(ref, f, c):
    js = jogos_do_recorte(ref, f, c)
    cs = cartoes_do_recorte(ref, f, c)
    fx, fa, fv = [0] * 6, [0] * 6, [0] * 6
    for x in cs:
        if x["mn"] is not None:
            fx[faixa(x["mn"])] += 1
            if x["t"] == "a":
                fa[faixa(x["mn"])] += 1
            else:
                fv[faixa(x["mn"])] += 1
    a = sum(1 for x in cs if x["t"] == "a")
    v = sum(1 for x in cs if x["t"] == "v")
    s = sum(1 for x in cs if x["t"] == "s")
    n = len(js)
    return {"n": n, "a": a, "v": v, "s": s, "red": v + s, "tot": a + v + s, "cpj": Decimal(a + v + s) / n if n else Decimal(0), "jcv": len({x["j"] for x in cs if x["t"] != "a"}), "com": sum(1 for x in cs if x["f"] == 1),
            "sem": sum(1 for x in cs if x["mn"] is None), "fx": fx, "fa": fa, "fv": fv, "cs": cs}


@pytest.fixture(scope="module")
def montagem(tmp_path_factory):
    m = carregar("montar_app13_ds", "13_montar_app.py")
    versus = m.modulo_versus().montar_dados()
    ds = m.montar_dados_ds(versus)
    frag = (PROTO / "disciplina" / "fragmento.html").read_text(encoding="utf-8").replace("__DADOS__", m.dados_json(ds))
    pasta = tmp_path_factory.mktemp("ds")
    (pasta / "ds.html").write_text(m.pagina("t", m.logos_js(versus) + frag), encoding="utf-8")
    return {"m": m, "versus": versus, "ds": ds, "frag": frag, "pasta": pasta}


@pytest.fixture(scope="module")
def curto(montagem):
    return {int(c["id"]): c["curto"] for c in montagem["ds"]["clubes"]}


@pytest.fixture(scope="module")
def sigla(montagem):
    return {int(c["id"]): c["sigla"] for c in montagem["ds"]["clubes"]}


def rodar(montagem, *extra):
    proc = subprocess.run(["node", str(RAIZ / "tests" / "js_harness_ds.js"), str(montagem["pasta"] / "ds.html"), *extra], capture_output=True, text=True, encoding="utf-8", timeout=600)
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
    ds = montagem["ds"]
    esperado = [{"n": j["n"], "f": j["f"], "r": j["r"], "d": j["d"], "m": j["m"], "v": j["v"], "gm": j["gm"], "gv": j["gv"], "ar": ds["arb"].index(j["arb"]), "a1": j["a1"], "a2": j["a2"], "pn": j["pn"]} for j in ref["jogos"]]
    assert ds["jogos"] == esperado and len(esperado) == 72
    assert ds["arb"] == sorted(set(j["arb"] for j in ref["jogos"])) and len(ds["arb"]) == 16


@precisa_dados
def test_cartoes_do_pacote_sao_os_413_da_regra_da_fpf_um_a_um(montagem, ref):
    ds = montagem["ds"]
    assert len(ds["cart"]) == len(ref["cartoes"]) == 413
    for c, e in zip(ds["cart"], ref["cartoes"]):
        assert (c["j"], c["mn"], c["t"], c["c"], c["f"]) == (e["j"], e["mn"], e["t"], e["c"], e["f"])
        assert (ds["atl"][c["p"]]["p"] if c["p"] is not None else None) == e["p"] and (ds["atl"][c["p"]]["a"] if c["p"] is not None else None) == e["a"]
        assert ds["cat"][c["m"]]["n"] == e["cat"]
    assert Counter(c["t"] for c in ds["cart"]) == {"a": 385, "v": 24, "s": 4} and Counter(c["f"] for c in ds["cart"]) == {0: 384, 1: 29}
    assert sum(1 for c in ds["cart"] if c["mn"] is None) == 3
    assert [a["p"] for a in ds["atl"]] == sorted({e["p"] for e in ref["cartoes"] if e["p"]}) and len(ds["atl"]) == 234
    assert all((c["p"] is None) == (c["f"] == 1) for c in ds["cart"])


@precisa_dados
def test_o_primeiro_amarelo_de_quem_foi_expulso_por_segundo_amarelo_fica_de_fora(montagem):
    eventos = ler_csv(PROC / "fato_evento.csv")
    seg = [e for e in eventos if e["tipo_evento"] == "segundo_amarelo"]
    assert len(seg) == 4
    brutos = Counter(e["tipo_evento"] for e in eventos if e["tipo_evento"] in CARTOES)
    assert brutos == {"amarelo": 389, "vermelho": 24, "segundo_amarelo": 4}
    ds = montagem["ds"]
    feitos = Counter(c["t"] for c in ds["cart"])
    assert feitos["a"] == brutos["amarelo"] - brutos["segundo_amarelo"] and feitos["v"] + feitos["s"] == brutos["vermelho"] + brutos["segundo_amarelo"]
    numero = {p["id_partida"]: int(p["numero_jogo"]) for p in ler_csv(PROC / "fato_partida.csv")}
    for s in seg:
        amarelos_dele = [e for e in eventos if e["id_partida"] == s["id_partida"] and e["pessoa"] == s["pessoa"] and e["tipo_evento"] == "amarelo"]
        assert len(amarelos_dele) == 1, "o dado traz o primeiro amarelo como evento à parte"
        dele = [c for c in ds["cart"] if c["j"] == numero[s["id_partida"]] and c["p"] is not None and ds["atl"][c["p"]]["p"] == s["pessoa"]]
        assert [c["t"] for c in dele] == ["s"], "na tela fica só a expulsão, que conta como vermelho"


@precisa_dados
def test_totais_do_pacote_batem_com_o_gabarito_geral_por_fase_e_por_clube(montagem, ref):
    gab = ler_csv(PROC / "ref_indicadores.csv")
    geral = {l["id_indicador"]: Decimal(l["valor"]) for l in gab if l["escopo"] == "geral"}
    r = resumo(ref, "t", None)
    assert (r["a"], r["red"]) == (geral["I20"], geral["I21"]) == (385, 28)
    assert round(r["cpj"], 4) == geral["I22"] and round(Decimal(sum(j["a1"] + j["a2"] for j in ref["jogos"])) / 72, 4) == geral["I23"] and sum(j["pn"] for j in ref["jogos"]) == geral["I25"] == 13
    fase = {(l["id_indicador"], l["chave"]): Decimal(l["valor"]) for l in gab if l["escopo"] == "fase"}
    for f, nome in {1: "PRIMEIRA FASE", 2: "QUARTAS DE FINAL", 3: "SEMIFINAL", 4: "FINAL"}.items():
        js = [j for j in ref["jogos"] if j["f"] == f]
        cs = [c for c in montagem["ds"]["cart"] if ref["por_n"][c["j"]]["f"] == f]
        assert (sum(1 for c in cs if c["t"] == "a"), sum(1 for c in cs if c["t"] != "a")) == (fase[("I20", nome)], fase[("I21", nome)])
        assert round(Decimal(len(cs)) / len(js), 4) == fase[("I22", nome)] and round(Decimal(sum(j["a1"] + j["a2"] for j in js)) / len(js), 4) == fase[("I23", nome)]
        assert sum(j["pn"] for j in js) == fase[("I25", nome)]
    clube = {(l["id_indicador"], l["id_clube"]): int(Decimal(l["valor"])) for l in gab if l["escopo"] == "clube"}
    for c in montagem["ds"]["clubes"]:
        cs = [x for x in montagem["ds"]["cart"] if str(x["c"]) == c["id"]]
        assert (sum(1 for x in cs if x["t"] == "a"), sum(1 for x in cs if x["t"] != "a")) == (clube[("I20", c["id"])], clube[("I21", c["id"])]), c["nome"]


@precisa_dados
def test_cartoes_da_comissao_e_os_sem_minuto_batem_com_o_que_a_documentacao_registra(montagem):
    cs = montagem["ds"]["cart"]
    assert (sum(1 for c in cs if c["f"] == 1 and c["t"] == "a"), sum(1 for c in cs if c["f"] == 1 and c["t"] != "a")) == (22, 7)
    assert sorted((c["j"], c["t"], c["f"]) for c in cs if c["mn"] is None) == [(41, "v", 1), (65, "v", 0), (71, "a", 1)]
    assert all(c["mn"] is None or 0 < c["mn"] <= 90 for c in cs)


@precisa_dados
def test_arbitros_do_pacote_tem_os_jogos_do_cadastro_e_acrescimos_do_boletim(montagem, ref):
    ds = montagem["ds"]
    por = Counter(ds["arb"][j["ar"]] for j in ds["jogos"])
    cadastro = {a["nome"]: int(a["jogos_arbitro"]) for a in ler_csv(PROC / "dim_arbitro.csv") if int(a["jogos_arbitro"]) > 0}
    assert dict(por) == cadastro and len(cadastro) == 16 and sorted(por.values(), reverse=True) == [9, 9, 9, 6, 5, 5, 5, 5, 4, 3, 3, 3, 3, 1, 1, 1] and sum(por.values()) == 72
    assert (min(j["a1"] for j in ds["jogos"]), max(j["a1"] for j in ds["jogos"]), min(j["a2"] for j in ds["jogos"]), max(j["a2"] for j in ds["jogos"])) == (3, 10, 3, 13)


@precisa_dados
def test_categorias_do_pacote_seguem_a_ordem_de_exibicao_e_a_contagem_por_grupo_e_a_esperada(montagem, ref):
    ds = montagem["ds"]
    assert [(c["n"], c["x"]) for c in ds["cat"]] == ref["cats"]
    assert dict(Counter(ds["cat"][c["m"]]["n"] for c in ds["cart"])) == {k: v for k, v in POR_CATEGORIA.items() if v}
    assert ds["meta"]["textos"] == len({x["motivo"] for x in ref["cartoes"]}) and ds["meta"]["textos"] <= len(ref["motivos"])


@precisa_dados
def test_cada_cartao_cai_num_grupo_e_so_os_poucos_textos_de_apoio_aparecem_na_tela(montagem, ref):
    regras = disc.ler_regras_motivo()
    brutos = [e for e in ler_csv(PROC / "fato_evento.csv") if e["tipo_evento"] in CARTOES]
    assert len(brutos) == 417 and all(disc.classificar_motivo(e["motivo"], regras)["categoria"] != "Outros" for e in brutos)
    nomes = {c["n"] for c in montagem["ds"]["cat"]} | {c["x"] for c in montagem["ds"]["cat"]}
    assert len(ref["motivos"]) > 100
    for motivo in ref["motivos"]:
        if motivo and not any(motivo in texto for texto in nomes):
            assert json.dumps(motivo, ensure_ascii=False) not in montagem["frag"], motivo[:40]
            assert len(motivo) < 40 or motivo not in montagem["frag"], "o texto livre da súmula (com nomes de pessoas) não pode ir para a tela"


@precisa_dados
def test_clubes_nomes_e_categorias_do_pacote_nao_citam_nada_interno(montagem):
    ds = montagem["ds"]
    assert len(ds["clubes"]) == 16
    for texto in [c[k] for c in ds["clubes"] for k in ("nome", "curto", "sigla")] + [a[k] for a in ds["atl"] for k in ("p", "a")] + ds["arb"] + [c[k] for c in ds["cat"] for k in ("n", "x")]:
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
    return montagem["m"].montar_dados_ds(montagem["versus"])


@precisa_dados
def test_o_montador_para_se_um_amarelo_sumir_dos_eventos(montagem, monkeypatch):
    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", lambda ls: ls.pop(next(k for k, x in enumerate(ls) if x["tipo_evento"] == "amarelo")))
    with pytest.raises(SystemExit, match="384 amarelos e 28 vermelhos"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_vermelho_virar_amarelo(montagem, monkeypatch):
    def mexer(linhas):
        next(x for x in linhas if x["tipo_evento"] == "vermelho")["tipo_evento"] = "amarelo"

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="386 amarelos e 27 vermelhos"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_segundo_amarelo_ficar_sem_o_primeiro(montagem, monkeypatch):
    def mexer(linhas):
        seg = next(x for x in linhas if x["tipo_evento"] == "segundo_amarelo")
        linhas.remove(next(x for x in linhas if x["tipo_evento"] == "amarelo" and x["id_partida"] == seg["id_partida"] and x["pessoa"] == seg["pessoa"]))

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="segundo amarelo sem amarelo anterior"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_cartao_da_comissao_for_de_clube_que_nao_jogou(montagem, monkeypatch):
    def mexer(linhas):
        partidas = {p["id_partida"]: p for p in ler_csv(PROC / "fato_partida.csv")}
        e = next(x for x in linhas if x["tipo_evento"] == "amarelo" and x["funcao"] != "Atleta")
        p = partidas[e["id_partida"]]
        e["id_clube"] = next(c["id_clube"] for c in ler_csv(PROC / "dim_clube.csv") if c["id_clube"] not in (p["id_clube_mandante"], p["id_clube_visitante"]))

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="clube que não jogou"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_cartao_de_atleta_for_de_clube_sem_a_camisa_na_relacao_de_jogadores(montagem, monkeypatch):
    def mexer(linhas):
        partidas = {p["id_partida"]: p for p in ler_csv(PROC / "fato_partida.csv")}
        e = next(x for x in linhas if x["tipo_evento"] == "amarelo" and x["funcao"] == "Atleta")
        p = partidas[e["id_partida"]]
        e["id_clube"] = next(c["id_clube"] for c in ler_csv(PROC / "dim_clube.csv") if c["id_clube"] not in (p["id_clube_mandante"], p["id_clube_visitante"]))

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="camisa que não está na relação de jogadores"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_o_acrescimo_de_um_jogo_mudar(montagem, monkeypatch):
    def mexer(linhas):
        l = next(x for x in linhas if x["numero_jogo"] == "7")
        l["acrescimo_2t_min"] = str(int(l["acrescimo_2t_min"]) + 1)

    adulterar(monkeypatch, montagem["m"], "fato_partida.csv", mexer)
    with pytest.raises(SystemExit, match="acréscimo"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_jogo_mudar_de_arbitro(montagem, monkeypatch):
    def mexer(linhas):
        a, b = (next(x for x in linhas if x["numero_jogo"] == n) for n in ("1", "2"))
        assert a["id_arbitro"] != b["id_arbitro"]
        a["id_arbitro"] = b["id_arbitro"]

    adulterar(monkeypatch, montagem["m"], "fato_partida.csv", mexer)
    with pytest.raises(SystemExit, match="árbitro"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_um_penalti_virar_gol_comum(montagem, monkeypatch):
    def mexer(linhas):
        next(x for x in linhas if x["tipo_evento"] == "gol_penalti")["tipo_evento"] = "gol"

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="pênalti"):
        refazer(montagem)


@precisa_dados
def test_o_montador_para_se_o_motivo_de_muitos_cartoes_deixar_de_ser_reconhecido(montagem, monkeypatch):
    def mexer(linhas):
        n = 0
        for x in linhas:
            if x["tipo_evento"] in CARTOES and n < 30:
                x["motivo"] = "texto novo que nenhuma regra conhece"
                n += 1

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    with pytest.raises(SystemExit, match="Outros"):
        refazer(montagem)


@precisa_dados
def test_poucos_motivos_novos_viram_outros_sem_parar_o_montador(montagem, monkeypatch):
    def mexer(linhas):
        next(x for x in linhas if x["tipo_evento"] == "amarelo")["motivo"] = "texto novo que nenhuma regra conhece"

    adulterar(monkeypatch, montagem["m"], "fato_evento.csv", mexer)
    ds = refazer(montagem)
    assert sum(1 for c in ds["cart"] if ds["cat"][c["m"]]["n"] == "Outros") == 1


# ---------- montagem da tela ----------

@precisa_dados
def test_fragmento_nao_deixa_marca_sobrando_e_so_age_quando_visivel(montagem):
    assert not re.search(r"__[A-Z_]+__", montagem["frag"])
    src = (PROTO / "disciplina" / "fragmento.html").read_text(encoding="utf-8")
    assert src.count("__DADOS__") == 1 and "height:100%;min-height:320px" in src and "if(!raiz.offsetParent)return;" in src
    assert "window.PA.mods.ds={entrar:entrar}" in src and 'id="dsx"' in src
    for ruim in INTERNOS:
        assert ruim not in src, ruim
    assert "http://" not in src and "https://" not in src and "@import" not in src and "<link" not in src


@precisa_dados
def test_textos_da_tela_sao_todos_de_pelo_menos_16_pixels():
    src = (PROTO / "disciplina" / "fragmento.html").read_text(encoding="utf-8")
    tamanhos = [int(x) for x in re.findall(r"font-size:(\d+)px", src)] + [int(x) for x in re.findall(r"font:[^;{}]*?(\d+)px", src)]
    assert tamanhos and min(tamanhos) >= 16, sorted(set(tamanhos))


@precisa_dados
def test_desenhos_nao_roubam_o_clique_nem_a_dica_e_as_listas_tem_barra_com_folga():
    src = (PROTO / "disciplina" / "fragmento.html").read_text(encoding="utf-8")
    assert re.search(r"#dsx \.tip\{[^}]*pointer-events:none", src)
    rola = re.search(r"#dsx \.rola\{([^}]*)\}", src).group(1)
    assert "overflow-y:auto" in rola and "scrollbar-width:thin" in rola
    assert re.search(r"padding-right:(1[2-9]|[2-9]\d)px", rola), "o conteúdo das listas precisa de folga em relação à barra de rolagem"
    assert re.search(r"#dsx \.rw::after\{[^}]*pointer-events:none", src), "o esmaecido do fim da lista não pode tampar o clique"
    for seletor in (r"#dsx \.campo text", r"#dsx \.campo \.lin", r"#dsx \.campo \.col"):
        assert re.search(seletor + r"\{[^}]*pointer-events:none", src), seletor
    js = src[src.index("<script>"):]
    for fixo in ("72 jogos", "413 cartões", "385", "16 clubes", "234 atletas", "113 textos", "no máximo 9"):
        assert fixo not in js, fixo
    assert "D.meta.textos" in js and "maxJogos()" in js


@precisa_dados
def test_pagina_do_app_leva_a_tela_depois_de_gols_e_antes_do_publico():
    m = carregar("montar_app13_dspg", "13_montar_app.py")
    dados = m.montar_todos_os_dados()
    frag = m.montar_fragmentos(dados)
    app = frag["app"]
    assert not re.search(r"__[A-Z_]+__", app)
    assert app.count('id="dsx"') == 1 and app.count('<section class="mod" id="mod-ds">') == 1 and m.dados_json(dados["ds"]) in app and frag["ds"] in app
    nav = re.search(r"<nav[^>]*>(.*?)</nav>", app, re.S).group(1)
    assert re.findall(r'data-mod="(\w+)"', nav) == [t[0] for t in m.TELAS] and [t[0] for t in m.TELAS].index("ds") == [t[0] for t in m.TELAS].index("gl") + 1
    assert '<button data-mod="ds"><span>Disciplina</span></button>' in nav and "Duelo de clubes" not in nav and "<span>Duelo</span>" in nav
    assert app.index('id="mod-vs"') < app.index('id="mod-ds"')


# ---------- comportamento (módulo simulado em Node) ----------

def kpis_da(h):
    achados = re.findall(r'<div class="kpi" style="left:([\d.]+)px;--kc:(#[0-9a-f]{6})" data-tip="([^"]*)"><h4>([^<]*)</h4><div class="v">([^<]*)</div><small>([^<]*)</small></div>', h)
    return [{"x": float(x), "tip": decod(t), "r": decod(r), "v": decod(v), "s": decod(s)} for x, cor, t, r, v, s in achados]


def zonas_da(h):
    padrao = re.compile(r'<g class="zona" data-tip="([^"]*)"><rect x="([\d.]+)" y="44" width="([\d.]+)" height="150" fill="rgba\(255,209,102,([\d.]+)\)"/><text class="cn" x="[\d.]+" y="126" text-anchor="middle">(\d+)</text>'
                        r'<text class="cp" x="[\d.]+" y="152" text-anchor="middle">([^<]*)</text></g>')
    topo = re.findall(r'<text class="ct" x="[\d.]+" y="20" text-anchor="middle">([^<]*)</text>', h)
    rotulos = re.findall(r'<text x="[\d.]+" y="218" text-anchor="middle">([^<]*)</text>', h)
    return [{"tip": decod(t), "x": float(x), "w": float(w), "alfa": float(a), "n": int(n), "pct": decod(p)} for t, x, w, a, n, p in padrao.findall(h)], [decod(t) for t in topo], rotulos


def motivos_da(h):
    padrao = re.compile(r'<div class="mv" data-tip="([^"]*)"><span class="nm">([^<]*)</span><div class="bb"><i class="a" style="width:([\d.]+)%"></i><i class="v" style="width:([\d.]+)%"></i></div><span class="ct">(\d+)</span></div>')
    return [{"tip": decod(t), "nome": decod(n), "wa": float(a), "wv": float(v), "n": int(c)} for t, n, a, v, c in padrao.findall(h)]


def clubes_da(h):
    padrao = re.compile(r'<button class="pc( sel| sem)?" data-act="clube" data-id="(\d+)" data-tip="([^"]*)"><span class="esc">(.*?)</span><span>([^<]*)</span><div class="bb"><i class="a" style="width:([\d.]+)%"></i><i class="v" style="width:([\d.]+)%"></i></div><span class="na">(\d+)</span><span class="nv">(\d+)</span></button>', re.S)
    return [{"cls": c.strip(), "id": int(i), "tip": decod(t), "logo": lg, "sigla": decod(sg), "wa": float(a), "wv": float(v), "a": int(na), "v": int(nv)} for c, i, t, lg, sg, a, v, na, nv in padrao.findall(h)]


def arbitros_da(h):
    padrao = re.compile(r'<div class="ar" data-tip="([^"]*)"><span class="nm">([^<]*)</span><i>(\d+)</i><i class="am">(\d+)</i><i class="vm">(\d+)</i><i>([^<]*)</i><i class="mut">(\d+)</i><i class="mut">([^<]*)</i></div>')
    return [{"tip": decod(t), "nome": decod(n), "j": int(j), "am": int(a), "vm": int(v), "cj": decod(cj), "pn": int(pn), "acr": decod(ac)} for t, n, j, a, v, cj, pn, ac in padrao.findall(h)]


def atletas_da(h):
    padrao = re.compile(r'<button class="at( sel| sem)?" data-act="clube" data-id="(\d+)" data-tip="([^"]*)"><span class="ps">(\d+)</span><span class="esc">(.*?)</span><div class="tx">([^<]*) <small>([^<]*)</small></div><span class="na">(\d+)</span><span class="nv">(\d+)</span></button>', re.S)
    return [{"cls": c.strip(), "id": int(i), "tip": decod(t), "pos": int(p), "logo": lg, "nome": decod(n), "sigla": decod(sg), "a": int(a), "v": int(v)} for c, i, t, p, lg, n, sg, a, v in padrao.findall(h)]


def rotulo_do_recorte(f, c, curto):
    return FS[f] if c is None else f"{curto[c]} · {FS[f]}"


@precisa_dados
@precisa_node
def test_o_codigo_roda_no_node_sem_texto_estragado_em_todos_os_estados(saida, ref):
    assert not any(e["ruim"] for e in saida["estados"])
    esperados = [("t", None)] + [("t", c) for c in sorted({x for j in ref["jogos"] for x in (j["m"], j["v"])})]
    for f in ("p", "m"):
        esperados += [(f, None)] + [(f, c) for c in sorted({x for j in jogos_do_recorte(ref, f, None) for x in (j["m"], j["v"])})]
    assert [(e["f"], e["c"]) for e in saida["estados"]] == esperados and len(esperados) == 43


@precisa_dados
@precisa_node
def test_seis_quadros_em_cada_recorte_e_a_dica_com_os_tres_recortes(saida, ref, curto):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        r = resumo(ref, f, c)
        com = c is not None
        k = kpis_da(e["kpis"])
        esperados = [("Amarelos", fmt(r["a"]), f"{pct(r['a'], r['tot'])} dos cartões"), ("Vermelhos", fmt(r["red"]), f"{fmt(r['v'])} diretos e {fmt(r['s'])} por 2º amarelo"),
                     ("Cartões por jogo", fmt(r["cpj"], 2), "do clube por jogo dele" if com else "média do recorte"), ("Segundos amarelos", fmt(r["s"]), "contam como vermelho"),
                     ("Jogos com vermelho", fmt(r["jcv"]), f"{pct(r['jcv'], r['n'])} dos jogos"), ("À comissão técnica", fmt(r["com"]), "técnicos e auxiliares")]
        assert [(x["r"], x["v"], x["s"]) for x in k] == esperados, (f, c)
        assert [round(x["x"], 1) for x in k] == [round(i * 307.6, 1) for i in range(6)] and all(x["x"] + 290 <= 1828 for x in k)
        por = {fase: resumo(ref, fase, c) for fase in "tpm"}
        tabelas = [lambda x: fmt(x["a"]), lambda x: fmt(x["red"]), lambda x: fmt(x["cpj"], 2), lambda x: fmt(x["s"]), lambda x: fmt(x["jcv"]), lambda x: fmt(x["com"])]
        nota = "~Este número muda com o filtro de fase" + (" e é o do clube escolhido" if com else "; com um clube escolhido ele passa a ser só dos cartões desse clube") + "."
        for q, fn in zip(k, tabelas):
            secoes = q["tip"].split("||")
            assert tabela_tip(secoes[2]) == [("Todas as fases", fn(por["t"])), ("1ª fase", fn(por["p"])), ("Mata-mata", fn(por["m"]))], (f, c, q["r"])
            assert secoes[3] == nota


@precisa_dados
@precisa_node
def test_campo_mostra_os_cartoes_de_cada_faixa_com_cor_proporcional_e_o_total_de_cada_tempo(saida, ref, curto):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        r = resumo(ref, f, c)
        h = e["paineis"][0]
        zonas, topo, rotulos = zonas_da(h)
        assert len(zonas) == 6 and rotulos == ["01-15 min", "16-30 min", "31-45 min", "46-60 min", "61-75 min", "76-90+ min"]
        maximo = max(r["fx"] + [1])
        t1, t2 = sum(r["fx"][:3]), sum(r["fx"][3:])
        dentro = t1 + t2
        assert dentro == r["tot"] - r["sem"]
        assert topo == [f"1º tempo · {plural(t1, 'cartão', 'cartões')} ({pct(t1, dentro)})", f"2º tempo · {plural(t2, 'cartão', 'cartões')} ({pct(t2, dentro)})"]
        for i, z in enumerate(zonas):
            assert abs(z["x"] - i * 1010 / 6) < 0.06 and abs(z["w"] - 1010 / 6) < 0.06
            assert z["n"] == r["fx"][i] and z["pct"] == pct(r["fx"][i], dentro) and abs(z["alfa"] - (0.1 + 0.62 * r["fx"][i] / maximo)) < 0.0011
            secoes = z["tip"].split("||")
            assert secoes[0] == "Minutos " + NOME_FAIXA[i] and tabela_tip(secoes[1]) == [("Cartões", fmt(r["fx"][i])), ("Parte dos cartões", pct(r["fx"][i], dentro)), ("Amarelos", fmt(r["fa"][i])), ("Vermelhos", fmt(r["fv"][i]))]
            assert secoes[2].startswith("~O acréscimo conta na faixa do tempo")
        assert f"{rotulo_do_recorte(f, c, curto)} · {plural(r['tot'], 'cartão', 'cartões')}" in h
        assert ("sem minuto</em>" in h) == (r["sem"] > 0)
        if r["sem"]:
            assert f"{fmt(r['sem'])} sem minuto</em>" in h and "como pós-jogo" in h and 'class="nota"' not in h
    todos = estado_de(saida, "t", None)
    assert zonas_da(todos["paineis"][0])[0][5]["n"] == 136 and sum(z["n"] for z in zonas_da(todos["paineis"][0])[0]) == 410


@precisa_dados
@precisa_node
def test_motivos_listam_os_oito_grupos_do_maior_para_o_menor_com_amarelos_e_vermelhos(saida, ref, curto):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        r = resumo(ref, f, c)
        nomes = [n for n, _ in ref["cats"]]
        por = {n: [0, 0] for n in nomes}
        for x in r["cs"]:
            por[x["cat"]][0 if x["t"] == "a" else 1] += 1
        ordem = sorted(range(len(nomes)), key=lambda i: (-(sum(por[nomes[i]])), i))
        h = e["paineis"][1]
        linhas = motivos_da(h)
        assert [x["nome"] for x in linhas] == [nomes[i] for i in ordem] and len(linhas) == 8
        maximo = max([sum(v) for v in por.values()] + [1])
        assert f"{rotulo_do_recorte(f, c, curto)}</small>" in h and h.count('<div class="lg2">') == 1
        for x, i in zip(linhas, ordem):
            a, v = por[nomes[i]]
            assert x["n"] == a + v and abs(x["wa"] - 100 * a / maximo) < 0.01 and abs(x["wv"] - 100 * v / maximo) < 0.01
            secoes = x["tip"].split("||")
            assert secoes[0] == nomes[i] and secoes[1] == f"{plural(a + v, 'cartão', 'cartões')} ({pct(a + v, r['tot'])} do recorte)"
            assert tabela_tip(secoes[2]) == [("Amarelos", str(a)), ("Vermelhos", str(v))] and secoes[3] == "~" + ref["cats"][i][1]
        assert sum(x["n"] for x in linhas) == r["tot"]
    todos = motivos_da(estado_de(saida, "t", None)["paineis"][1])
    assert [(x["nome"], x["n"]) for x in todos][:3] == [("Ação temerária", 181), ("Impedir ataque promissor ou gol", 73), ("Atitude antidesportiva", 68)] and todos[-1]["n"] == 0


@precisa_dados
@precisa_node
def test_cartoes_por_clube_listam_os_clubes_da_fase_em_ordem_de_cartoes_e_marcam_o_escolhido(saida, ref, curto, sigla):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        m = {}
        for j in jogos_do_recorte(ref, f, None):
            for lado in (j["m"], j["v"]):
                m.setdefault(lado, {"a": 0, "r": 0, "s": 0, "n": 0})["n"] += 1
        for x in cartoes_do_recorte(ref, f, None):
            q = m[x["c"]]
            if x["t"] == "a":
                q["a"] += 1
            else:
                q["r"] += 1
                q["s"] += 1 if x["t"] == "s" else 0
        ordem = sorted(m, key=lambda k: (-(m[k]["a"] + m[k]["r"]), -m[k]["r"], curto[k]))
        h = e["paineis"][2]
        linhas = clubes_da(h)
        assert [x["id"] for x in linhas] == ordem and len(linhas) == (8 if f == "m" else 16)
        maximo = max([v["a"] + v["r"] for v in m.values()] + [1])
        assert f"{FS[f]} · {plural(len(m), 'clube', 'clubes')}</small>" in h and '<div class="pch">' in h
        for x in linhas:
            v = m[x["id"]]
            assert (x["a"], x["v"], x["sigla"]) == (v["a"], v["r"], sigla[x["id"]]) and abs(x["wa"] - 100 * v["a"] / maximo) < 0.01 and abs(x["wv"] - 100 * v["r"] / maximo) < 0.01
            assert x["cls"] == ("" if c is None else "sel" if x["id"] == c else "sem") and ("<img" in x["logo"] or 'class="sg"' in x["logo"])
            secoes = x["tip"].split("||")
            assert secoes[0] == f"{curto[x['id']]} · cartões"
            assert tabela_tip(secoes[1]) == [("Amarelos", str(v["a"])), ("Vermelhos", str(v["r"])), ("Cartões", str(v["a"] + v["r"])), ("Jogos", str(v["n"])), ("Cartões por jogo", fmt(Decimal(v["a"] + v["r"]) / v["n"], 2)), ("Segundos amarelos", str(v["s"]))]
            assert secoes[2] == "~Clique para escolher este clube."
        if c is not None:
            assert sum(1 for x in linhas if x["cls"] == "sel") == 1
    todos = clubes_da(estado_de(saida, "t", None)["paineis"][2])
    assert sum(x["a"] for x in todos) == 385 and sum(x["v"] for x in todos) == 28


@precisa_dados
@precisa_node
def test_arbitros_mostram_cartoes_penaltis_e_acrescimo_dos_jogos_deles_sem_mudar_com_o_clube(saida, ref, curto):
    jogo = lambda j: f"{curto[j['m']]} {j['gm']} × {j['gv']} {curto[j['v']]}"
    por_jogo = {}
    for x in ref["cartoes"]:
        por_jogo.setdefault(x["j"], [0, 0])[0 if x["t"] == "a" else 1] += 1
    maximo_jogos = max(Counter(j["arb"] for j in ref["jogos"]).values())
    assert maximo_jogos == 9
    for e in saida["estados"]:
        f = e["f"]
        m = {}
        for j in jogos_do_recorte(ref, f, None):
            m.setdefault(j["arb"], []).append(j)
        ordem = sorted(m, key=lambda n: (-len(m[n]), n))
        h = e["paineis"][3]
        linhas = arbitros_da(h)
        assert [x["nome"] for x in linhas] == ordem and f"{FS[f]} · {plural(len(m), 'árbitro', 'árbitros')}</small>" in h
        assert '<div class="rw"><div class="rola" data-r="ar" style="max-height:300px">' in h and f"Amostra pequena: no máximo {maximo_jogos} jogos por árbitro. Não é avaliação de desempenho." in h
        for x in linhas:
            js = m[x["nome"]]
            n = len(js)
            am = sum(por_jogo.get(j["n"], [0, 0])[0] for j in js)
            vm = sum(por_jogo.get(j["n"], [0, 0])[1] for j in js)
            a1, a2, pn = sum(j["a1"] for j in js), sum(j["a2"] for j in js), sum(j["pn"] for j in js)
            assert (x["j"], x["am"], x["vm"], x["cj"], x["pn"], x["acr"]) == (n, am, vm, fmt(Decimal(am + vm) / n, 2), pn, fmt(Decimal(a1 + a2) / n, 1))
            secoes = x["tip"].split("||")
            assert secoes[0] == x["nome"]
            assert tabela_tip(secoes[1]) == [("Jogos", str(n)), ("Amarelos", str(am)), ("Vermelhos", str(vm)), ("Cartões por jogo", fmt(Decimal(am + vm) / n, 2)), ("Gols de pênalti", str(pn)),
                                              ("Acréscimo médio (1º + 2º tempo)", fmt(Decimal(a1 + a2) / n, 1) + " min"), ("Acréscimo médio do 1º tempo", fmt(Decimal(a1) / n, 1) + " min"), ("Acréscimo médio do 2º tempo", fmt(Decimal(a2) / n, 1) + " min")]
            assert tabela_tip(secoes[2]) == [(data_br(j["d"]) + " · " + jogo(j), plural(sum(por_jogo.get(j["n"], [0, 0])), "cartão", "cartões")) for j in js]
            assert secoes[3] == "~Amostra pequena: não é avaliação de desempenho."
    iguais = {tuple(x["nome"] for x in arbitros_da(es["paineis"][3])) for es in saida["estados"] if es["f"] == "t"}
    assert len(iguais) == 1
    todos = arbitros_da(estado_de(saida, "t", None)["paineis"][3])
    assert len(todos) == 16 and sum(x["j"] for x in todos) == 72 and sum(x["am"] for x in todos) == 385 and sum(x["vm"] for x in todos) == 28 and sum(x["pn"] for x in todos) == 13


@precisa_dados
@precisa_node
def test_atletas_mais_advertidos_listam_so_atletas_do_recorte_com_desempate_por_vermelhos_e_nome(saida, ref, curto, sigla):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        por = {}
        for x in cartoes_do_recorte(ref, f, c):
            if x["f"] == 0:
                q = por.setdefault((x["p"], x["c"]), {"a": 0, "r": 0, "nome": x["a"]})
                q["a" if x["t"] == "a" else "r"] += 1
        ordem = sorted(por, key=lambda k: (-(por[k]["a"] + por[k]["r"]), -por[k]["r"], k[0], k[1]))
        h = e["paineis"][4]
        linhas = atletas_da(h)
        assert [(x["nome"], x["id"]) for x in linhas] == [(por[k]["nome"], k[1]) for k in ordem] and len(linhas) == len(por)
        assert f"{plural(len(por), 'atleta', 'atletas')}</small>" in h and '<div class="rw"><div class="rola" data-r="at" style="max-height:330px">' in h
        for i, (x, k) in enumerate(zip(linhas, ordem)):
            v = por[k]
            assert (x["pos"], x["a"], x["v"], x["sigla"]) == (i + 1, v["a"], v["r"], sigla[k[1]]) and x["cls"] == ("" if c is None else "sel" if k[1] == c else "sem")
            secoes = x["tip"].split("||")
            assert secoes[0] == f"{k[0]} · {curto[k[1]]}" and tabela_tip(secoes[1]) == [("Cartões", str(v["a"] + v["r"])), ("Amarelos", str(v["a"])), ("Vermelhos", str(v["r"]))]
            assert secoes[2] == "~Clique para escolher o clube do atleta."
        if not por:
            assert "Nenhum atleta advertido neste recorte." in h
    todos = atletas_da(estado_de(saida, "t", None)["paineis"][4])
    assert len(todos) == 234 and sum(x["a"] for x in todos) + sum(x["v"] for x in todos) == 384
    assert todos[0]["a"] + todos[0]["v"] == max(x["a"] + x["v"] for x in todos)


@precisa_dados
@precisa_node
def test_atletas_e_arbitros_desempatam_pelo_nome_mesmo_quando_a_ordem_nos_dados_muda(saida, ref):
    for e in saida["permutado"]:
        f = e["f"]
        por = {}
        for x in cartoes_do_recorte(ref, f, None):
            if x["f"] == 0:
                q = por.setdefault((x["p"], x["c"]), {"n": 0, "r": 0, "nome": x["a"]})
                q["n"] += 1
                q["r"] += 0 if x["t"] == "a" else 1
        esperado = sorted(por, key=lambda k: (-por[k]["n"], -por[k]["r"], k[0], k[1]))
        assert [x["nome"] for x in atletas_da(e["paineis"][4])] == [por[k]["nome"] for k in esperado], f
        m = Counter(j["arb"] for j in jogos_do_recorte(ref, f, None))
        assert [x["nome"] for x in arbitros_da(e["paineis"][3])] == sorted(m, key=lambda n: (-m[n], n)), f


@precisa_dados
@precisa_node
def test_cabecalho_botoes_de_fase_limpar_e_subtitulo(saida, ref, curto):
    for e in saida["estados"]:
        f, c = e["f"], e["c"]
        r = resumo(ref, f, c)
        if c is None:
            esperado = ("Quanto se pune em campo e onde · " if f == "t" else FS[f] + " · ") + f"{plural(r['n'], 'jogo', 'jogos')} · {plural(r['tot'], 'cartão', 'cartões')}"
        else:
            esperado = f"{curto[c]} · {FS[f]} · {plural(r['n'], 'jogo', 'jogos')} · {plural(r['tot'], 'cartão', 'cartões')}"
        assert e["sub"] == esperado, (f, c)
        chips = re.findall(r'<button class="chp( on)?" data-act="fase" data-v="(\w)"[^>]*><span>([^<]*)</span></button>', e["ctl"])
        assert [(x[1], x[2], bool(x[0])) for x in chips] == [(k, FS[k], k == f) for k in "tpm"]
        assert ("lim off" in e["ctl"]) == (f == "t" and c is None) and 'data-act="ajuda"' in e["ctl"]


@precisa_dados
@precisa_node
def test_rodape_e_ajuda_explicam_a_tela(saida):
    r = saida["rodape"]
    assert "Dados: súmulas oficiais da FPF" in r["rod"] and "cartões conferidos com os indicadores" in r["rod"] and "Projeto independente, sem vínculo com a FPF" in r["rod"]
    assert r["aj"].count("<li>") == 4 and re.search(r'<button[^>]*data-act="ajuda-fechar"[^>]*data-tip="[^"]+"[^>]*>Entendi</button>', r["aj"]) and "(no máximo 9)" in r["aj"]
    for palavra in ("Segundo amarelo", "Faixa de minuto", "Motivos", "Árbitros", "não é avaliação de desempenho"):
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
    atleta = por["linha dos atletas"]
    assert atleta["tag"] == "at" and atleta["depois"]["clube"] is not None and por["linha dos atletas de novo"]["depois"]["clube"] is None
    do_quadro_de_clubes = [c for c in saida["cliques"] if c["rot"].startswith("clube")]
    assert len(do_quadro_de_clubes) == 5 and all(c["tag"] == "pc" for c in do_quadro_de_clubes)
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
    assert t["paineis"][2].count("<img") == 0 and t["paineis"][2].count('class="sg"') == 16 and t["paineis"][4].count("<img") == 0 and t["paineis"][4].count('class="sg"') == 234
    com = estado_de(rodar(montagem), "t", None)
    assert com["paineis"][2].count("<img") == 16 and com["paineis"][4].count("<img") == 234
