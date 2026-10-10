import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

PROC = RAIZ / "data" / "processed"
FRAGMENTO = RAIZ / "prototype" / "versus" / "fragmento.html"
precisa_dados = pytest.mark.skipif(not (PROC / "ref_indicadores.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")


def gerador():
    spec = importlib.util.spec_from_file_location("versus11", RAIZ / "scripts" / "11_montar_versus.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ref_clube(ind):
    from comum import ler_csv

    return {l["id_clube"]: float(l["valor"]) for l in ler_csv(PROC / "ref_indicadores.csv") if l["id_indicador"] == ind and l["escopo"] == "clube" and l["valor"] != ""}


@pytest.fixture(scope="module")
def dados():
    return gerador().montar_dados()


@precisa_dados
def test_numeros_dos_clubes_batem_com_o_gabarito(dados):
    jogos, gp, gc = ref_clube("I01"), ref_clube("I27"), ref_clube("I28")
    pts, pos, am, ve, pub = ref_clube("I29"), ref_clube("I31"), ref_clube("I20"), ref_clube("I21"), ref_clube("I32")
    assert len(dados["clubes"]) == 16
    for c in dados["clubes"]:
        i = c["id"]
        assert (c["j"], c["gp"], c["gc"]) == (jogos[i], gp[i], gc[i]), c["nome"]
        assert c["v"] + c["e"] + c["d"] == c["j"], c["nome"]
        assert c["sg"] == c["gp"] - c["gc"], c["nome"]
        assert (c["pts1"], c["pos1"]) == (pts[i], pos[i]), c["nome"]
        assert (c["am"], c["ve"]) == (am[i], ve[i]), c["nome"]
        assert c["pubm"] == round(pub[i]), c["nome"]


@precisa_dados
def test_somas_gerais(dados):
    cl = dados["clubes"]
    assert sum(c["j"] for c in cl) == 2 * len(dados["jogos"]) == 144
    assert sum(c["gp"] for c in cl) == sum(c["gc"] for c in cl) == 168
    assert sum(c["v"] for c in cl) == sum(c["d"] for c in cl)
    assert sorted(c["pos1"] for c in cl) == list(range(1, 17))


@precisa_dados
def test_eventos_de_gol_batem_com_o_placar_de_cada_jogo(dados):
    for j in dados["jogos"]:
        gols = Counter(e[1] for e in j["ev"] if e[0] in ("g", "p", "f", "c"))
        assert (gols[0], gols[1]) == (j["gm"], j["gv"]), j["n"]


@precisa_dados
def test_fase_alcancada_uma_so_campeao_e_contagens(dados):
    fases = Counter(c["fase"] for c in dados["clubes"])
    assert fases == {"Campeão": 1, "Vice-campeão": 1, "Semifinal": 2, "Quartas de final": 4, "1ª fase": 8}


@precisa_dados
def test_forma_tem_um_resultado_por_jogo(dados):
    for c in dados["clubes"]:
        assert len(c["forma"]) == c["j"], c["nome"]
        penaltis = sum(1 for f in c["forma"] if f[1])
        normais = Counter(f[0] for f in c["forma"] if not f[1])
        assert (normais["V"], normais["E"], normais["D"]) == (c["v"], c["e"] - penaltis, c["d"]), c["nome"]


@precisa_dados
def test_cores_validas_e_escudo_embutido(dados):
    for c in dados["clubes"]:
        assert re.fullmatch(r"#[0-9a-f]{6}", c["cor"]) and re.fullmatch(r"#[0-9a-f]{6}", c["cor2"]), c["nome"]
        assert c["logo"].startswith("data:image/png;base64,"), c["nome"]
        assert c["art"], c["nome"]


@precisa_dados
def test_cartoes_do_duelo_levam_so_o_grupo_do_motivo_e_nunca_o_texto_da_sumula(dados):
    from comum import ler_csv
    from disciplina import categorias_em_ordem, classificar_motivo, ler_regras_motivo

    regras = ler_regras_motivo()
    grupos = [r["categoria"] for r in categorias_em_ordem(regras)]
    assert dados["mot"] == grupos and len(grupos) == 8
    eventos = [e for e in ler_csv(PROC / "fato_evento.csv") if e["tipo_evento"] in ("amarelo", "vermelho", "segundo_amarelo")]
    esperado = Counter(classificar_motivo(e["motivo"], regras)["categoria"] if e["motivo"] else None for e in eventos)
    achado = Counter(dados["mot"][x[7]] if x[7] >= 0 else None for j in dados["jogos"] for x in j["ev"] if x[0] in "avs")
    assert achado == esperado and sum(achado.values()) == 417
    assert all(x[7] == -1 for j in dados["jogos"] for x in j["ev"] if x[0] in "gpfc")
    texto_do_pacote = json.dumps(dados, ensure_ascii=False)
    livres = {e["motivo"] for e in ler_csv(PROC / "fato_evento.csv") if e["motivo"] and not any(e["motivo"] in g for g in grupos)}
    assert len(livres) > 100 and not [t for t in livres if t in texto_do_pacote], "o texto livre do motivo não pode ir para a página"


def test_fragmento_sem_recursos_externos_nem_armazenamento():
    t = FRAGMENTO.read_text(encoding="utf-8")
    assert t.count("__DADOS__") == 1
    assert "localStorage" not in t and "sessionStorage" not in t and "indexedDB" not in t
    assert not re.search(r"https?://", t.replace("http://www.w3.org/2000/svg", ""))
    assert "<!--" not in t and "/*" not in t and not re.search(r"(?m)^\s*//", t)
    assert not re.search(r"<link|@import", t)


@precisa_dados
def test_pagina_gerada_tem_json_valido():
    g = gerador()
    dados = g.montar_dados()
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    assert "</" not in texto
    assert json.loads(texto)["jogos"][0]["n"] == 1
