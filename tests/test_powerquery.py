import importlib.util
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
MODELO = RAIZ / "powerbi" / "PaulistaAnalytics.SemanticModel" / "definition"
precisa_dados = pytest.mark.skipif(not (PROC / "fato_partida.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")


def gerador():
    spec = importlib.util.spec_from_file_location("pq08", RAIZ / "scripts" / "08_gerar_powerquery.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


g = gerador()


@precisa_dados
def test_cada_csv_vira_uma_consulta_com_todas_as_colunas_na_mesma_ordem():
    assert len(g.TABELAS) == 23 and len(set(g.TABELAS)) == 23
    for t in g.TABELAS:
        p = g.tabela_pronta(t)
        csv_cols = list(ler_csv(PROC / f"{t}.csv")[0])
        assert [c[0] for c in p["colunas"]] == csv_cols
        declaradas = re.findall(r"^\tcolumn (\w+)$", p["tmdl"], re.M)
        esperadas = csv_cols + (["escudo_base64"] if t == "dim_clube" else [])
        assert declaradas == esperadas, t
        assert re.findall(r"^\t\tsourceColumn: (\w+)$", p["tmdl"], re.M) == esperadas
        assert len(set(declaradas)) == len(declaradas)


@precisa_dados
def test_consultas_usam_cultura_en_us_e_nao_detectam_tipos():
    for t in g.TABELAS:
        m = g.tabela_pronta(t)["m"]
        assert 'Delimiter = ";"' in m and "Encoding = 65001" in m and 'CaminhoDados & "\\' + t + '.csv"' in m
        assert '"en-US")' in m
        assert "Detect" not in m and "ChangedType" not in m
        assert 'Vazios = Table.ReplaceValue(Cabecalho, "", null' in m and "Table.TransformColumnTypes(Vazios" in m


@precisa_dados
def test_tipos_dos_campos_que_exigem_cuidado():
    p = {c[0]: c[1] for c in g.tabela_pronta("fato_partida")["colunas"]}
    assert p["renda_bruta"] == p["despesas_total"] == p["renda_liquida"] == "decimal"
    assert p["publicada_em"] == "datetime_ptbr" and p["data_hora_programada"] == "datetime" and p["data_jogo"] == "date"
    assert p["hora_programada"] == "string" and p["id_clube_mandante"] == "int64" and p["id_estadio"] == "string"
    assert {c[0]: c[1] for c in g.tabela_pronta("dim_estadio")["colunas"]}["capacidade"] == "int64"
    assert {c[0]: c[1] for c in g.tabela_pronta("dim_clube")["colunas"]}["cor_espn"] == "string"  # "000000" não pode virar número
    m = g.tabela_pronta("fato_partida")["m"]
    assert 'Format = "dd/MM/yyyy HH:mm", Culture = "pt-BR"' in m and "Currency.Type" in m


@precisa_dados
def test_dim_clube_carrega_o_escudo_em_base64():
    m = g.tabela_pronta("dim_clube")["m"]
    assert "Binary.ToText" in m and "BinaryEncoding.Base64" in m and "escudo_base64" in m


@precisa_dados
def test_geracao_e_idempotente_e_o_modelo_registra_tudo():
    assert g.tabela_pronta("fato_evento")["tmdl"] == g.tabela_pronta("fato_evento")["tmdl"]
    modelo = (MODELO / "model.tmdl").read_text(encoding="utf-8")
    if not (MODELO / "expressions.tmdl").exists():
        pytest.skip("rode scripts/08_gerar_powerquery.py")
    for t in g.TABELAS + ["_Medidas", "aux_dashboard"]:
        assert f"ref table {t}\n" in modelo, t
    assert "CaminhoDados" in modelo  # o gerador escreve `ref expression`; o Power BI, ao salvar, registra na ordem das consultas
    assert 'expression CaminhoDados = "' in (MODELO / "expressions.tmdl").read_text(encoding="utf-8")


@precisa_dados
def test_dinheiro_do_financeiro_e_decimal_fixo_e_as_chaves_ficam_texto_ou_inteiro():
    tipos = lambda t: {c[0]: c[1] for c in g.tabela_pronta(t)["colunas"]}
    assert tipos("fato_ingresso")["preco"] == tipos("fato_ingresso")["arrecadacao"] == "decimal"
    assert tipos("fato_despesa")["valor"] == "decimal"
    assert {tipos("fato_rateio")[c] for c in ("valor", "deducao_inss", "deducao_outras", "liquido")} == {"decimal"}
    assert tipos("fato_ingresso")["id_ingresso"] == "string" and tipos("fato_ingresso")["setor_visitante"] == "int64" and tipos("fato_ingresso")["ingressos"] == "int64"
    assert tipos("fato_escalacao")["registro"] == "string" and tipos("fato_escalacao")["jogou"] == "int64" and tipos("dim_atleta")["id_atleta"] == "string"
    assert tipos("fato_despesa")["bloco_codigo"] == "string" and tipos("fato_substituicao")["id_atleta_entrou"] == "string"
    assert "Currency.Type" in g.tabela_pronta("fato_rateio")["m"]


@precisa_dados
def test_a_descricao_da_tabela_entra_no_arquivo_como_comentario():
    descricoes = g.descricoes()
    for t in g.TABELAS:
        primeira = g.tabela_pronta(t)["tmdl"].split("\n")[0]
        assert primeira == f"/// {descricoes[t]}", t


@precisa_dados
def test_por_padrao_so_escreve_as_tabelas_que_ainda_nao_existem(tmp_path, monkeypatch):
    modelo = tmp_path / "definition"
    (modelo / "tables").mkdir(parents=True)
    (modelo / "model.tmdl").write_text('model Model\n\nannotation PBI_QueryOrder = ["velho"]\n\nref table velho\n\nref cultureInfo pt-BR\n', encoding="utf-8")
    (modelo / "tables" / "dim_fase.tmdl").write_text("TEXTO DO DESKTOP\n", encoding="utf-8")
    monkeypatch.setattr(g, "MODELO", modelo)
    monkeypatch.setattr(g, "DOC", tmp_path / "powerquery.md")
    monkeypatch.setattr(sys, "argv", ["08"])
    g.principal()
    assert (modelo / "tables" / "dim_fase.tmdl").read_text(encoding="utf-8") == "TEXTO DO DESKTOP\n"
    assert {a.stem for a in (modelo / "tables").glob("*.tmdl")} == set(g.TABELAS)
    registro = (modelo / "model.tmdl").read_text(encoding="utf-8")
    assert all(f"ref table {t}\n" in registro for t in g.TABELAS + g.TECNICAS) and "ref table velho" not in registro
    assert '"fato_rateio"' in registro and registro.count("annotation PBI_QueryOrder") == 1
    monkeypatch.setattr(sys, "argv", ["08", "--tudo"])
    g.principal()
    assert (modelo / "tables" / "dim_fase.tmdl").read_text(encoding="utf-8").startswith("/// ")
