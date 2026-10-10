"""Indicadores do financeiro e do elenco (I38 a I59), com cálculo independente do que `scripts/indicadores.py` faz."""
import re
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import indicadores  # noqa: E402
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
precisa_dados = pytest.mark.skipif(not (PROC / "ref_indicadores.csv").exists() or not (PROC / "fato_ingresso.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")
NOVOS = {f"I{i}" for i in range(38, 60)}


def D(x):
    return Decimal(x)


def reais(x):
    return D(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pct(a, b):
    return round(float(D(a) * 100 / D(b)), 4)


@pytest.fixture(scope="module")
def tab():
    L = lambda n: ler_csv(PROC / f"{n}.csv")
    return {n: L(n) for n in ("fato_partida", "fato_ingresso", "fato_despesa", "fato_rateio", "fato_escalacao", "fato_substituicao", "dim_clube", "dim_fase", "ref_indicadores")}


@pytest.fixture(scope="module")
def ref(tab):
    return {(l["id_indicador"], l["escopo"], l["chave"], l["id_clube"]): l for l in tab["ref_indicadores"]}


def valor(ref, ind, escopo, chave="", clube=""):
    return ref[(ind, escopo, chave, clube)]["valor"]


def confere_dinheiro(ref, ind, escopo, chave, clube, esperado):
    assert D(valor(ref, ind, escopo, chave, clube)) == reais(esperado), (ind, escopo, chave, clube)


def confere_pct(ref, ind, escopo, chave, clube, esperado):
    assert abs(float(valor(ref, ind, escopo, chave, clube)) - esperado) <= 0.00006, (ind, escopo, chave, clube)


# ---------- fórmulas com dados inventados ----------

def test_formulas_com_dados_inventados():
    partidas = [
        {"id_partida": "1", "publico_boletim": "1000", "renda_bruta": "9000.00", "despesas_total": "3000.00"},
        {"id_partida": "2", "publico_boletim": "500", "renda_bruta": "1000.00", "despesas_total": "1500.50"},
    ]
    ingressos = [{"id_partida": "1", "setor_visitante": "1", "ingressos": "100"}, {"id_partida": "1", "setor_visitante": "0", "ingressos": "900"}, {"id_partida": "2", "setor_visitante": "1", "ingressos": "50"}, {"id_partida": "9", "setor_visitante": "1", "ingressos": "7"}]
    rateio = [{"id_partida": "1", "deducao_inss": "10.00", "deducao_outras": "5.50", "liquido": "5984.50"}, {"id_partida": "2", "deducao_inss": "0.00", "deducao_outras": "0.00", "liquido": "-500.50"}, {"id_partida": "9", "deducao_inss": "1", "deducao_outras": "1", "liquido": "1"}]
    escalacao = [{"id_partida": "1", "situacao": "titular", "jogou": "1", "gols": "2"}, {"id_partida": "1", "situacao": "reserva", "jogou": "1", "gols": "1"}, {"id_partida": "1", "situacao": "reserva", "jogou": "0", "gols": "0"},
                 {"id_partida": "2", "situacao": "titular", "jogou": "1", "gols": "0"}, {"id_partida": "2", "situacao": "reserva", "jogou": "1", "gols": "3"}, {"id_partida": "9", "situacao": "reserva", "jogou": "1", "gols": "9"}]
    substituicoes = [{"id_partida": "1"}, {"id_partida": "2"}, {"id_partida": "2"}, {"id_partida": "9"}]
    m = {k[1]: v for k, v in indicadores.metricas_financeiro_elenco(partidas, ingressos, [], rateio, escalacao, substituicoes).items()}
    assert m["despesas"] == (Decimal("4500.50"), "R$")
    assert m["pct_despesas_renda_bruta"] == (45.005, "%")
    assert m["despesa_por_ingresso"] == (Decimal("3.00"), "R$/ingresso")  # 4500,50 / 1500 = 3,0003
    assert m["ingressos_setor_visitante"] == (150, "ingressos") and m["pct_torcida_visitante"] == (10.0, "%")
    assert m["deducoes"] == (Decimal("15.50"), "R$") and m["liquido_a_receber"] == (Decimal("5484.00"), "R$")
    assert m["atletas_em_campo"][0] == 4 and m["titulares"][0] == 2 and m["reservas_que_entraram"][0] == 2
    assert m["substituicoes"][0] == 3 and m["gols_de_reservas"][0] == 4


def test_so_os_jogos_do_conjunto_entram():
    partidas = [{"id_partida": "1", "publico_boletim": "10", "renda_bruta": "100.00", "despesas_total": "40.00"}]
    m = {k[1]: v[0] for k, v in indicadores.metricas_financeiro_elenco(partidas, [{"id_partida": "2", "setor_visitante": "1", "ingressos": "5"}], [], [{"id_partida": "2", "deducao_inss": "1", "deducao_outras": "1", "liquido": "3"}], [], [{"id_partida": "2"}]).items()}
    assert m["ingressos_setor_visitante"] == 0 and m["deducoes"] == Decimal("0.00") and m["substituicoes"] == 0


# ---------- com os dados reais: cada linha nova recalculada de outro jeito ----------

@precisa_dados
def test_geral_e_por_fase_batem_com_calculo_independente(tab, ref):
    fases = {f["id_fase"]: f["nome_fase"] for f in tab["dim_fase"]}
    conjuntos = [("geral", "", {p["id_partida"] for p in tab["fato_partida"]})] + [("fase", nome, {p["id_partida"] for p in tab["fato_partida"] if p["id_fase"] == idf}) for idf, nome in fases.items()]
    assert len(conjuntos) == 5
    for escopo, chave, ids in conjuntos:
        ps = [p for p in tab["fato_partida"] if p["id_partida"] in ids]
        publico = sum(int(p["publico_boletim"]) for p in ps)
        bruta = sum(D(p["renda_bruta"]) for p in ps)
        despesas = sum(D(p["despesas_total"]) for p in ps)
        visit = sum(int(x["ingressos"]) for x in tab["fato_ingresso"] if x["id_partida"] in ids and x["setor_visitante"] == "1")
        rat = [r for r in tab["fato_rateio"] if r["id_partida"] in ids]
        esc = [e for e in tab["fato_escalacao"] if e["id_partida"] in ids]
        confere_dinheiro(ref, "I38", escopo, chave, "", despesas)
        confere_pct(ref, "I39", escopo, chave, "", float(despesas / bruta * 100))
        confere_dinheiro(ref, "I40", escopo, chave, "", despesas / publico)
        assert int(valor(ref, "I41", escopo, chave)) == visit
        confere_pct(ref, "I42", escopo, chave, "", visit / publico * 100)
        confere_dinheiro(ref, "I43", escopo, chave, "", sum(D(r["deducao_inss"]) + D(r["deducao_outras"]) for r in rat))
        confere_dinheiro(ref, "I44", escopo, chave, "", sum(D(r["liquido"]) for r in rat))
        assert int(valor(ref, "I55", escopo, chave)) == sum(1 for e in esc if e["jogou"] == "1")
        assert int(valor(ref, "I56", escopo, chave)) == sum(1 for e in esc if e["situacao"] == "titular")
        assert int(valor(ref, "I57", escopo, chave)) == sum(1 for e in esc if e["situacao"] == "reserva" and e["jogou"] == "1")
        assert int(valor(ref, "I58", escopo, chave)) == sum(1 for s in tab["fato_substituicao"] if s["id_partida"] in ids)
        assert int(valor(ref, "I59", escopo, chave)) == sum(int(e["gols"]) for e in esc if e["situacao"] == "reserva")


@precisa_dados
def test_categorias_de_ingresso_batem_com_calculo_independente(tab, ref):
    por = defaultdict(lambda: [0, Decimal(0)])
    for x in tab["fato_ingresso"]:
        por[x["categoria"]][0] += int(x["ingressos"])
        por[x["categoria"]][1] += D(x["arrecadacao"])
    assert set(por) == {"Inteira", "Meia-entrada", "Sócio-torcedor", "Cadeira e camarote", "Gratuidade por lei", "Outros"}
    tot_q, tot_r = sum(v[0] for v in por.values()), sum(v[1] for v in por.values())
    for cat, (q, r) in por.items():
        assert int(valor(ref, "I45", "categoria", cat)) == q
        confere_dinheiro(ref, "I46", "categoria", cat, "", r)
        confere_dinheiro(ref, "I47", "categoria", cat, "", r / q)
        confere_pct(ref, "I48", "categoria", cat, "", q / tot_q * 100)
        confere_pct(ref, "I49", "categoria", cat, "", float(r / tot_r * 100))
    assert D(valor(ref, "I47", "categoria", "Gratuidade por lei")) == 0  # gratuidade não tem preço
    assert (tot_q, reais(tot_r)) == (784369, D("44730003.80"))


@precisa_dados
def test_grupos_e_blocos_de_despesa_batem_com_calculo_independente(tab, ref):
    grupo, bloco = defaultdict(Decimal), defaultdict(Decimal)
    for d in tab["fato_despesa"]:
        grupo[d["grupo"]] += D(d["valor"])
        bloco[d["bloco_codigo"]] += D(d["valor"])
    total = sum(grupo.values())
    assert len(grupo) == 10 and sorted(bloco) == ["B1", "B2", "B3"] and reais(total) == D("20404747.14")
    for escopo, mapa in (("grupo_despesa", grupo), ("bloco", bloco)):
        for chave, v in mapa.items():
            confere_dinheiro(ref, "I38", escopo, chave, "", v)
            confere_pct(ref, "I50", escopo, chave, "", float(v / total * 100))


@precisa_dados
def test_indicadores_por_clube_batem_com_calculo_independente(tab, ref):
    clubes = {c["id_clube"]: c["nome_popular"] for c in tab["dim_clube"]}
    assert len(clubes) == 16
    ing_visit = defaultdict(int)
    for x in tab["fato_ingresso"]:
        if x["setor_visitante"] == "1":
            ing_visit[x["id_partida"]] += int(x["ingressos"])
    for idc, nome in clubes.items():
        casa = [p for p in tab["fato_partida"] if p["id_clube_mandante"] == idc]
        fora = [p for p in tab["fato_partida"] if p["id_clube_visitante"] == idc]
        confere_dinheiro(ref, "I51", "clube", nome, idc, sum(D(p["renda_bruta"]) for p in casa))
        confere_dinheiro(ref, "I52", "clube", nome, idc, sum(D(p["renda_liquida"]) for p in casa))
        assert int(valor(ref, "I53", "clube", nome, idc)) == sum(ing_visit[p["id_partida"]] for p in casa)
        assert int(valor(ref, "I54", "clube", nome, idc)) == sum(ing_visit[p["id_partida"]] for p in fora)
        confere_dinheiro(ref, "I44", "clube", nome, idc, sum(D(r["liquido"]) for r in tab["fato_rateio"] if r["id_clube"] == idc))


@precisa_dados
def test_escopos_fecham_entre_si(tab, ref):
    linhas = tab["ref_indicadores"]
    soma = lambda ind, escopo: sum(D(l["valor"]) for l in linhas if l["id_indicador"] == ind and l["escopo"] == escopo)
    geral = lambda ind: D(valor(ref, ind, "geral"))
    assert soma("I45", "categoria") == D(valor(ref, "I10", "geral")) == 784369
    assert soma("I46", "categoria") == geral("I16")  # arrecadação por categoria = renda bruta
    assert soma("I38", "grupo_despesa") == soma("I38", "bloco") == geral("I38")
    assert soma("I38", "fase") == geral("I38") and soma("I43", "fase") == geral("I43") and soma("I44", "fase") == geral("I44")
    assert soma("I41", "fase") == geral("I41") == soma("I53", "clube") == soma("I54", "clube")  # cada ingresso de visitante é recebido por um e levado por outro
    assert soma("I51", "clube") == geral("I16") and soma("I52", "clube") == geral("I17")
    assert soma("I44", "clube") == geral("I44")
    assert abs(float(soma("I48", "categoria")) - 100) < 0.0003 and abs(float(soma("I49", "categoria")) - 100) < 0.0003
    assert abs(float(soma("I50", "grupo_despesa")) - 100) < 0.0003 and abs(float(soma("I50", "bloco")) - 100) < 0.0003
    assert geral("I55") == geral("I56") + geral("I57") and geral("I57") == geral("I58")  # quem entrou do banco é quem foi substituído (sem concussão adicional)
    assert geral("I40") == reais(geral("I38") / geral("I10"))


@precisa_dados
def test_fatos_conhecidos_do_financeiro_e_do_elenco(ref):
    esperado = {"I38": "20404747.14", "I39": "45.6176", "I40": "26.01", "I41": "69685", "I42": "8.8842", "I43": "153535.40", "I44": "24171721.26",
                "I55": "2290", "I56": "1584", "I57": "706", "I58": "706", "I59": "34"}
    for ind, v in esperado.items():
        assert D(valor(ref, ind, "geral")) == D(v), ind
    assert int(valor(ref, "I53", "clube", "Corinthians", next(k[3] for k in ref if k[0] == "I53" and k[2] == "Corinthians"))) >= 0
    levada = {k[2]: int(v["valor"]) for k, v in ref.items() if k[0] == "I54"}
    assert [n for n, _ in sorted(levada.items(), key=lambda kv: -kv[1])[:3]] == ["Corinthians", "Palmeiras", "Santos"]
    assert (levada["Corinthians"], levada["Palmeiras"], levada["Santos"]) == (25270, 19159, 11290)


@precisa_dados
def test_ref_indicadores_tem_586_linhas_e_todos_os_ids_do_dicionario(tab):
    assert len(tab["ref_indicadores"]) == 586
    ids = {l["id_indicador"] for l in tab["ref_indicadores"]}
    assert ids == {f"I{i:02d}" for i in range(1, 60)}
    dic = (RAIZ / "docs" / "dicionario_indicadores.md").read_text(encoding="utf-8")
    linhas = [l for l in dic.splitlines() if re.match(r"^\| I\d\d \|", l)]
    assert [l.split("|")[1].strip() for l in linhas] == [f"I{i:02d}" for i in range(1, 60)]
    assert all(len(l.strip().strip("|").split("|")) == 7 for l in linhas)
    escopos = {l["escopo"] for l in tab["ref_indicadores"]}
    assert escopos == {"geral", "fase", "faixa_minuto", "clube", "artilheiro", "qualidade", "categoria", "grupo_despesa", "bloco"}
    for esc in ("categoria", "grupo_despesa", "bloco"):
        assert f"`{esc}`" in dic
    assert not NOVOS - ids
