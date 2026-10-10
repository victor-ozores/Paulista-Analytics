import hashlib
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from classificacao import contagem_cartoes, tabela_primeira_fase  # noqa: E402
from comum import FASE_ESPN, carregar_espn, ler_csv, mapa_clubes, norm, pareamento  # noqa: E402

PROC = RAIZ / "data" / "processed"
REF = RAIZ / "data" / "referencia"
precisa_proc = pytest.mark.skipif(not (PROC / "fato_partida.csv").exists(), reason="rode scripts/04_tratar.py antes")
precisa_espn = pytest.mark.skipif(not (RAIZ / "data" / "raw" / "espn").exists(), reason="coleta da ESPN ausente")


def tab(nome):
    return ler_csv(PROC / f"{nome}.csv")


def jogo(m, v, gm, gv):
    return {"id_clube_mandante": m, "id_clube_visitante": v, "gols_mandante": gm, "gols_visitante": gv}


def ordem(partidas, cartoes=None):
    return [l["id_clube"] for l in tabela_primeira_fase(partidas, cartoes)]


def test_desempate_por_vitorias():
    partidas = [jogo("B", "X", 0, 0), jogo("B", "Y", 0, 0), jogo("B", "Z", 0, 0), jogo("A", "X", 1, 0)]
    t = tabela_primeira_fase(partidas)
    assert [l["id_clube"] for l in t[:2]] == ["A", "B"]
    assert t[0]["pontos"] == t[1]["pontos"] == 3 and t[0]["vitorias"] == 1 and t[1]["vitorias"] == 0


def test_empate_triplo_em_16_pontos_decidido_por_vitorias_e_saldo():
    t = {"N": dict(pontos=16, vitorias=5, saldo=6, gols_pro=16), "P": dict(pontos=16, vitorias=5, saldo=1, gols_pro=8), "B": dict(pontos=16, vitorias=4, saldo=12, gols_pro=14)}
    certo = sorted(t, key=lambda k: (-t[k]["pontos"], -t[k]["vitorias"], -t[k]["saldo"], -t[k]["gols_pro"]))
    assert certo == ["N", "P", "B"]


def test_desempate_por_saldo_gols_e_cartoes():
    por_saldo = [jogo("A", "C", 3, 0), jogo("B", "C", 1, 0)]
    assert ordem(por_saldo)[:2] == ["A", "B"]
    por_gols = [jogo("A", "C", 2, 1), jogo("B", "C", 1, 0)]
    assert ordem(por_gols)[:2] == ["A", "B"]
    iguais = [jogo("A", "C", 1, 0), jogo("B", "C", 1, 0)]
    assert ordem(iguais, {"A": (3, 1), "B": (5, 0)})[:2] == ["B", "A"]
    assert ordem(iguais, {"A": (2, 0), "B": (5, 0)})[:2] == ["A", "B"]
    t = tabela_primeira_fase(iguais, {"A": (2, 0), "B": (2, 0)})
    assert t[0]["empate_total"] and t[1]["empate_total"]


def test_contagem_de_cartoes_regra_da_fpf():
    regs = [{"equipe_id": 1, "cartao": "amarelo"}] * 4 + [{"equipe_id": 1, "cartao": "2o_amarelo"}, {"equipe_id": 1, "cartao": "vermelho"}]
    assert contagem_cartoes(regs)[1] == (3, 2)


@precisa_proc
def test_chaves_unicas_e_chaves_estrangeiras():
    pk = {"dim_clube": "id_clube", "dim_estadio": "id_estadio", "dim_arbitro": "id_arbitro", "dim_fase": "id_fase", "fato_partida": "id_partida", "fato_evento": "id_evento", "dim_calendario": "data"}
    for nome, col in pk.items():
        ids = [l[col] for l in tab(nome)]
        assert len(ids) == len(set(ids)), nome
    clubes = {c["id_clube"] for c in tab("dim_clube")}
    estadios = {e["id_estadio"] for e in tab("dim_estadio")}
    arbitros = {a["id_arbitro"] for a in tab("dim_arbitro")}
    partidas = tab("fato_partida")
    for p in partidas:
        assert p["id_clube_mandante"] in clubes and p["id_clube_visitante"] in clubes
        assert p["id_estadio"] in estadios and p["id_arbitro"] in arbitros
    ids_p = {p["id_partida"] for p in partidas}
    assert all(e["id_partida"] in ids_p for e in tab("fato_evento"))
    datas = {c["data"] for c in tab("dim_calendario")}
    assert all(p["data_jogo"] in datas for p in partidas)


@precisa_proc
def test_totais_da_temporada():
    p = tab("fato_partida")
    assert len(p) == 72
    assert sum(int(x["gols_mandante"]) + int(x["gols_visitante"]) for x in p) == 168
    assert sum(int(x["publico_boletim"]) for x in p) == sum(int(x["publico_espn"]) for x in p) == 784369
    assert sum(Decimal(x["renda_bruta"]) for x in p) == Decimal("44730003.80")
    assert sum(int(x["publico_pagante"]) for x in p) == 761489
    assert all(Decimal(x["despesas_total"]) + Decimal(x["renda_liquida"]) == Decimal(x["renda_bruta"]) for x in p)


@precisa_proc
def test_classificacao_calculada_reproduz_a_oficial():
    oficial = {int(c["id_clube"]): c for c in ler_csv(REF / "fpf_a1_2026_classificacao.csv") if c["fase"] == "PRIMEIRA FASE"}
    for l in tab("ref_classificacao_primeira_fase"):
        o = oficial[int(l["id_clube"])]
        assert int(l["posicao"]) == int(o["pos"])
        for col_ref, col_of in (("pontos", "pontos"), ("jogos", "jogos"), ("vitorias", "vitorias"), ("saldo", "saldo"), ("amarelos", "amarelos"), ("vermelhos", "vermelhos")):
            assert int(l[col_ref]) == int(o[col_of]), (l["id_clube"], col_ref)


@precisa_proc
def test_gol_contra_credita_o_adversario_e_total_por_clube_confere_com_placar():
    ev = tab("fato_evento")
    contra = [e for e in ev if e["tipo_evento"] == "gol_contra"]
    assert len(contra) == 2 and all(e["id_clube"] != e["id_clube_creditado"] for e in contra)
    gols = Counter()
    for e in ev:
        if e["tipo_evento"].startswith("gol"):
            gols[(e["id_partida"], e["id_clube_creditado"])] += 1
    for p in tab("fato_partida"):
        assert gols[(p["id_partida"], p["id_clube_mandante"])] == int(p["gols_mandante"])
        assert gols[(p["id_partida"], p["id_clube_visitante"])] == int(p["gols_visitante"])


@precisa_proc
def test_disputa_de_penaltis_registrada_uma_vez():
    com = [p for p in tab("fato_partida") if p["penaltis_mandante"] != ""]
    assert len(com) == 1 and (int(com[0]["penaltis_mandante"]), int(com[0]["penaltis_visitante"])) == (7, 8)
    disputa = [e for e in tab("fato_evento") if e["tipo_evento"] == "penalti_disputa"]
    assert len(disputa) == 15 and all(e["periodo"] == "PEN" and not e["tipo_evento"].startswith("gol") for e in disputa)


@precisa_proc
def test_placar_dos_penaltis_vem_da_sumula_oficial_e_as_15_cobrancas_da_espn_fecham_com_ele():
    sp = ler_csv(PROC / "fpf" / "sumula_partida.csv")
    assert [(r["numero_jogo"], r["penaltis_mandante"], r["penaltis_visitante"]) for r in sp if r["penaltis_mandante"] != ""] == [("68", "7", "8")]
    partida = next(p for p in tab("fato_partida") if p["numero_jogo"] == "68")
    assert (partida["penaltis_mandante"], partida["penaltis_visitante"]) == ("7", "8")
    cobrancas = [e for e in tab("fato_evento") if e["tipo_evento"] == "penalti_disputa"]
    assert {e["fonte"] for e in cobrancas} == {"ESPN"} and {e["id_partida"] for e in cobrancas} == {partida["id_partida"]}
    assert (sum(1 for e in cobrancas if e["id_clube"] == partida["id_clube_mandante"]), sum(1 for e in cobrancas if e["id_clube"] == partida["id_clube_visitante"])) == (7, 8)


@precisa_proc
def test_cartoes_oficiais_por_regra_da_fpf():
    ev = tab("fato_evento")
    c = Counter(e["tipo_evento"] for e in ev)
    assert c["amarelo"] - c["segundo_amarelo"] == 385
    assert c["vermelho"] + c["segundo_amarelo"] == 28


@precisa_proc
def test_escudos_oficiais_reduzidos_para_o_dashboard():
    clubes = tab("dim_clube")
    assert len(clubes) == 16
    from PIL import Image

    for c in clubes:
        arq = PROC / c["arquivo_escudo"]
        assert arq.exists() and arq.stat().st_size <= 8000
        assert max(Image.open(arq).size) <= 128


@precisa_proc
def test_estatistica_de_time_completa():
    est = tab("fato_estatistica_time")
    assert len(est) == 144
    assert all(v != "" for l in est for v in l.values())


@precisa_proc
def test_nomes_de_arbitros_sem_duplicados():
    arb = tab("dim_arbitro")
    for i, a in enumerate(arb):
        for b in arb[i + 1:]:
            na, nb = norm(a["nome"]), norm(b["nome"])
            assert not (na <= nb or nb <= na), (a["nome"], b["nome"])


@precisa_espn
def test_chave_do_jogo_inclui_a_fase_e_pareia_72_jogos():
    jogos = ler_csv(REF / "fpf_a1_2026_jogos.csv")
    eventos, _ = carregar_espn()
    _, _, mapa, sem_par = mapa_clubes(jogos, eventos)
    assert not sem_par
    assert len(pareamento(jogos, eventos, mapa)) == 72
    assert set(FASE_ESPN.values()) == {j["fase"] for j in jogos}


@precisa_proc
def test_etl_idempotente_mesmas_tabelas_ao_rodar_de_novo():
    def hashes():
        return {a.name: hashlib.sha256(a.read_bytes()).hexdigest() for a in sorted(PROC.glob("*.csv")) if a.name != "aux_config.csv"}

    antes = hashes()
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "04_tratar.py")], capture_output=True, text=True, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert hashes() == antes
