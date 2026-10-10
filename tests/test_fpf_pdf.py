import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from fpf_pdf import ler_boletim, ler_sumula, minuto, texto_pdf  # noqa: E402

PDFS = RAIZ / "data" / "raw" / "fpf_pdf" / "2026"
precisa_pdf = pytest.mark.skipif(not (PDFS / "sumula" / "57.pdf").exists(), reason="PDFs brutos ausentes (rode scripts/03_coletar_fpf_pdf.py)")


def aplicar_regra_fpf(advertencias, vermelhos_diretos, segundos_amarelos):
    return advertencias - segundos_amarelos, vermelhos_diretos + segundos_amarelos


def test_minuto_normal_e_acrescimo():
    assert minuto("23:00", "1T") == (23, 0)
    assert minuto("+ 6", "2T") == (90, 6)
    assert minuto("+ 1", "1T") == (45, 1)


def test_regra_de_cartoes_da_fpf():
    assert aplicar_regra_fpf(4, 0, 1) == (3, 1)
    assert aplicar_regra_fpf(26, 3, 0) == (26, 3)


@precisa_pdf
def test_boletim_jogo_57():
    b = ler_boletim(texto_pdf(PDFS / "boletim" / "57.pdf"))
    assert b["publico"] == 4962
    assert b["renda_bruta"] == Decimal("109640.00")
    assert b["despesas_total"] == Decimal("63275.02")
    assert b["renda_liquida"] == Decimal("46364.98")
    assert b["receita_confere"] and b["renda_confere"]
    assert b["publico_pagante"] == 4499


@precisa_pdf
def test_boletim_com_renda_liquida_negativa():
    b = ler_boletim(texto_pdf(PDFS / "boletim" / "1.pdf"))
    assert b["renda_liquida"] == Decimal("-13503.80")
    assert b["renda_confere"]


@precisa_pdf
def test_boletim_com_cabecalho_colado():
    # No jogo 46 o texto do PDF vem "...São Bernardo FCESTÁDIO..." (sem espaço antes de ESTÁDIO).
    b = ler_boletim(texto_pdf(PDFS / "boletim" / "46.pdf"))
    assert (b["data"], b["horario"]) == ("01/02/2026", "18:15")
    assert b["jogo"] == "Red Bull Bragantino x São Bernardo FC"


@precisa_pdf
def test_sumula_jogo_57():
    s = ler_sumula(texto_pdf(PDFS / "sumula" / "57.pdf"), ["Botafogo", "Capivariano"])
    assert s["arbitro"] == "Murilo Tarrega Victor"
    assert s["placar_final"] == (0, 1)
    assert [(g["equipe"], g["minuto"], g["acrescimo"]) for g in s["gols"]] == [("Capivariano", 90, 6)]
    assert len(s["advertencias"]) == 4
    assert len(s["expulsoes"]) == 1 and s["expulsoes"][0]["tipo"] == "Cartão Vermelho"


@precisa_pdf
def test_sumula_expulsao_apos_o_jogo_com_traco_no_lugar_do_minuto():
    s = ler_sumula(texto_pdf(PDFS / "sumula" / "65.pdf"), ["Red Bull Bragantino", "São Paulo"])
    pos_jogo = [e for e in s["expulsoes"] if e["periodo"] == "PJ"]
    assert len(pos_jogo) == 1 and pos_jogo[0]["minuto"] is None and pos_jogo[0]["tipo"] == "Cartão Vermelho"
    assert any(e["tipo"] == "2º Cartão Amarelo" for e in s["expulsoes"])


@precisa_pdf
def test_sumula_traz_o_placar_dos_penaltis_so_quando_houve_disputa():
    s = ler_sumula(texto_pdf(PDFS / "sumula" / "68.pdf"), ["Portuguesa SAF", "Corinthians"])
    assert s["placar_final"] == (1, 1) and s["penaltis"] == (7, 8)
    sem = ler_sumula(texto_pdf(PDFS / "sumula" / "57.pdf"), ["Botafogo", "Capivariano"])
    assert sem["penaltis"] is None


@precisa_pdf
def test_so_a_sumula_do_jogo_68_das_72_tem_disputa_de_penaltis():
    import csv

    with open(RAIZ / "data" / "referencia" / "fpf_a1_2026_jogos.csv", encoding="utf-8", newline="") as f:
        jogos = list(csv.DictReader(f, delimiter=";"))
    com_disputa = {}
    for j in jogos:
        s = ler_sumula(texto_pdf(PDFS / "sumula" / f"{j['numero']}.pdf"), [j["mandante"], j["visitante"]])
        if s["penaltis"] is not None:
            com_disputa[int(j["numero"])] = (s["placar_final"], s["penaltis"])
    assert com_disputa == {68: ((1, 1), (7, 8))}


@precisa_pdf
def test_sumula_cartao_de_comissao_tecnica():
    s = ler_sumula(texto_pdf(PDFS / "sumula" / "72.pdf"), ["Grêmio Novorizontino", "Palmeiras"])
    comissao = [a for a in s["advertencias"] if a["funcao"] != "Atleta"]
    assert len(comissao) == 3
    assert {a["funcao"] for a in comissao} == {"Técnico", "Auxiliar Técnico"}


@precisa_pdf
def test_total_de_gols_das_sumulas_bate_com_a_temporada():
    import csv

    with open(RAIZ / "data" / "referencia" / "fpf_a1_2026_jogos.csv", encoding="utf-8", newline="") as f:
        jogos = list(csv.DictReader(f, delimiter=";"))
    total_oficial = sum(int(j["gols_mandante"]) + int(j["gols_visitante"]) for j in jogos)
    total_sumula = 0
    for j in jogos:
        s = ler_sumula(texto_pdf(PDFS / "sumula" / f"{j['numero']}.pdf"), [j["mandante"], j["visitante"]])
        total_sumula += len(s["gols"])
    assert total_oficial == total_sumula == 168
