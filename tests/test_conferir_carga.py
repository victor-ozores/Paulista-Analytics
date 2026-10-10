import csv
import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

PROC = RAIZ / "data" / "processed"
precisa_dados = pytest.mark.skipif(not (PROC / "fato_partida.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")


def gerador():
    spec = importlib.util.spec_from_file_location("car15", RAIZ / "scripts" / "15_conferir_carga_powerbi.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


g = gerador()


def resultado_do_modelo(tmp_path, ajustar=None, nome="r.csv"):
    """Escreve um resultado como o Power BI devolveria (vírgula decimal), a partir do esperado; `ajustar` muda ou tira linhas."""
    esp = {k: (n, s) for k, (n, s, tipo) in g.esperado().items()}
    if ajustar:
        ajustar(esp)
    arq = tmp_path / nome
    with open(arq, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["[t]", "[c]", "[n]", "[s]"])
        for (t, c), (n, s) in esp.items():
            w.writerow([t, c, n, str(round(s, 6) if isinstance(s, float) else s).replace(".", ",")])
    return arq


@precisa_dados
def test_cada_coluna_das_23_tabelas_tem_uma_linha_na_consulta_e_os_lotes_cobrem_tudo():
    cols = g.colunas()
    assert len(cols) == 272 and len({(t, c) for t, c, _ in cols}) == 272
    assert {t for t, _, _ in cols} == set(g.modulo_powerquery().TABELAS) and ("dim_clube", "escudo_base64", "string") in cols
    assert g.consulta().count('ROW("t",') == 272
    lotes = [g.consulta(0, 90), g.consulta(90, 181), g.consulta(181, 272)]
    assert sum(l.count('ROW("t",') for l in lotes) == 272
    todas = [linha for l in lotes for linha in l.split("\n") if linha.startswith("ROW(")]
    assert len(set(todas)) == 272
    assert 'SUMX(dim_fase, LEN(dim_fase[nome_fase]))' in g.consulta() and 'SUM(fato_partida[renda_bruta])' in g.consulta()
    assert 'CONVERT(fato_partida[data_jogo], DOUBLE)' in g.consulta() and 'CONVERT(fato_partida[publicada_em], DOUBLE)' in g.consulta()


@precisa_dados
def test_esperado_traz_os_valores_conhecidos_do_etl():
    esp = g.esperado()
    assert len(esp) == 271 and ("dim_clube", "escudo_base64") not in esp
    assert esp[("fato_partida", "publico_boletim")][:2] == (72, 784369)
    assert esp[("fato_ingresso", "ingressos")][:2] == (2388, 784369)
    assert esp[("dim_estadio", "capacidade")][:2] == (0, 0)  # sem fonte verificada (A32): coluna toda vazia
    assert esp[("fato_rateio", "liquido")][1] == pytest.approx(24171721.26, abs=0.005)
    assert esp[("fato_despesa", "valor")][1] == pytest.approx(20404747.14, abs=0.005)
    assert esp[("fato_escalacao", "jogou")][:2] == (3292, 2290)
    assert esp[("dim_calendario", "data")][0] == 365 and esp[("fato_partida", "publicada_em")][2] == "datetime_ptbr"


@precisa_dados
def test_comparar_aceita_o_modelo_igual_ao_etl(tmp_path):
    r = g.comparar([resultado_do_modelo(tmp_path)])
    assert (r["colunas"], r["iguais"], r["diferentes"], r["sem_resultado"]) == (271, 271, [], [])


@precisa_dados
def test_comparar_acusa_tabela_velha_soma_errada_e_coluna_sem_resultado(tmp_path):
    def velha(esp):
        n, s = esp[("aux_config", "chave")]
        esp[("aux_config", "chave")] = (n - 2, s - 51)
        n, s = esp[("fato_despesa", "valor")]
        esp[("fato_despesa", "valor")] = (n, s + 0.02)
        del esp[("fato_partida", "gols_mandante")]

    r = g.comparar([resultado_do_modelo(tmp_path, velha)])
    assert r["iguais"] == 268 and r["sem_resultado"] == [("fato_partida", "gols_mandante")]
    assert {d[0] for d in r["diferentes"]} == {("aux_config", "chave"), ("fato_despesa", "valor")}


@precisa_dados
def test_diferenca_de_centavo_abaixo_da_tolerancia_passa_e_de_texto_ou_inteiro_nao(tmp_path):
    def pouco(esp):
        n, s = esp[("fato_ingresso", "arrecadacao")]
        esp[("fato_ingresso", "arrecadacao")] = (n, s + 0.004)

    assert g.comparar([resultado_do_modelo(tmp_path, pouco, "a.csv")])["diferentes"] == []

    def um_a_mais(esp):
        n, s = esp[("fato_partida", "publico_boletim")]
        esp[("fato_partida", "publico_boletim")] = (n, s + 1)
        n, s = esp[("dim_clube", "nome_popular")]
        esp[("dim_clube", "nome_popular")] = (n, s + 1)

    r = g.comparar([resultado_do_modelo(tmp_path, um_a_mais, "b.csv")])
    assert {d[0] for d in r["diferentes"]} == {("fato_partida", "publico_boletim"), ("dim_clube", "nome_popular")}


@precisa_dados
def test_resultado_de_varios_lotes_se_junta_e_o_ultimo_arquivo_vale(tmp_path):
    cheio = resultado_do_modelo(tmp_path, nome="cheio.csv")
    linhas = cheio.read_text(encoding="utf-8").split("\n")
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("\n".join(linhas[:100]) + "\n", encoding="utf-8")
    b.write_text(linhas[0] + "\n" + "\n".join(linhas[100:]), encoding="utf-8")
    assert g.comparar([a, b])["iguais"] == 271
    velho = resultado_do_modelo(tmp_path, lambda e: e.update({("fato_partida", "id_partida"): (1, 1)}), "velho.csv")
    assert g.comparar([velho, cheio])["diferentes"] == []
    assert len(g.comparar([cheio, velho])["diferentes"]) == 1
