import importlib.util
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

PROC = RAIZ / "data" / "processed"
MODELO = RAIZ / "powerbi" / "PaulistaAnalytics.SemanticModel" / "definition"
precisa_dados = pytest.mark.skipif(not (PROC / "fato_partida.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")


def gerador():
    spec = importlib.util.spec_from_file_location("rel09", RAIZ / "scripts" / "09_gerar_relacionamentos.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


g = gerador()


def test_quantidade_e_papeis():
    ativas = [r for r in g.R if r[4]]
    assert (len(g.R), len(ativas)) == (39, 28)
    inativas = {(r[0], r[1]) for r in g.R if not r[4]}
    assert {("fato_partida", "id_clube_mandante"), ("fato_partida", "id_clube_visitante"), ("fato_evento", "id_clube_creditado"), ("fato_substituicao", "id_atleta_saiu"), ("dim_atleta", "id_clube")} <= inativas
    assert len([r for r in g.R if r[2] == "dim_arbitro"]) == 7 and len([r for r in g.R if r[2] == "dim_arbitro" and r[4]]) == 1
    assert len({g.nome(r) for r in g.R}) == 39


@precisa_dados
def test_dados_sem_orfaos_e_chaves_unicas():
    assert g.conferir_dados() == []


def test_desenho_sem_caminhos_ativos_ambiguos():
    assert g.conferir_ambiguidade() == []


def test_o_verificador_acusa_ambiguidade(monkeypatch):
    # se o clube se ligasse ativamente à partida, chegaria ao evento por dois caminhos
    alterada = [(*r[:4], True, r[5]) if r[1] == "id_clube_mandante" else r for r in g.R]
    monkeypatch.setattr(g, "R", alterada)
    erros = g.conferir_ambiguidade()
    assert any("dim_clube para fato_evento" in e for e in erros)


@precisa_dados
def test_o_verificador_acusa_orfao_e_chave_repetida(monkeypatch):
    monkeypatch.setattr(g, "R", [("fato_evento", "id_clube_creditado", "dim_fase", "id_fase", True, "x")])  # valores de clube não existem em dim_fase
    assert any("sem par" in e for e in g.conferir_dados())
    monkeypatch.setattr(g, "R", [("fato_partida", "id_fase", "fato_evento", "id_clube", True, "x")])  # lado "um" repetido
    assert any("única" in e for e in g.conferir_dados())


@precisa_dados
def test_arquivos_gerados_batem_com_a_definicao_e_as_colunas_existem():
    arq = MODELO / "relationships.tmdl"
    if not arq.exists():
        pytest.skip("rode scripts/09_gerar_relacionamentos.py")
    texto = arq.read_text(encoding="utf-8")
    pares = re.findall(r"fromColumn: (\w+)\.(\w+)\n\ttoColumn: (\w+)\.(\w+)", texto)
    assert len(pares) == 39 and set(pares) == {(r[0], r[1], r[2], r[3]) for r in g.R}
    for t, c in {(p[0], p[1]) for p in pares} | {(p[2], p[3]) for p in pares}:
        colunas = re.findall(r"^\tcolumn (\w+)$", (MODELO / "tables" / f"{t}.tmdl").read_text(encoding="utf-8"), re.M)
        assert c in colunas, f"{t}.{c} não é coluna do modelo"
    assert texto.count("isActive: false") == 11


def gerador_pq():
    spec = importlib.util.spec_from_file_location("pq08", RAIZ / "scripts" / "08_gerar_powerquery.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_descricao_cobre_todas_as_tabelas_de_dados_e_a_de_medidas():
    assert set(g.DESCRICAO_TABELAS) == set(gerador_pq().TABELAS) | {"_Medidas"}
    assert all(d and "\n" not in d and len(d) < 300 for d in g.DESCRICAO_TABELAS.values())
    assert [x["Name"] for x in g.definicoes_tabelas_mcp()] == list(g.DESCRICAO_TABELAS)


def test_sem_resto_da_prova_de_conceito_no_modelo_nem_nos_geradores():
    tabelas = {a.stem for a in (MODELO / "tables").glob("*.tmdl")}
    assert tabelas == set(gerador_pq().TABELAS) | {"_Medidas", "aux_dashboard"}  # sem a aux_versus, que era só da tela de versus
    assert not (RAIZ / "scripts" / "07_gerar_medida_poc.py").exists()
    antigo = "aux" + "_html"
    assert antigo not in (MODELO / "model.tmdl").read_text(encoding="utf-8")
    for arq in (RAIZ / "scripts").glob("*.py"):
        assert antigo not in arq.read_text(encoding="utf-8"), arq.name


def test_modelo_salvo_pelo_desktop_guarda_a_descricao_de_cada_tabela():
    for arq in sorted((MODELO / "tables").glob("*.tmdl")):
        assert arq.read_text(encoding="utf-8").split("\n")[0].startswith("/// "), f"{arq.name} sem descrição da tabela"


def test_atletas_substituicoes_e_financeiro_ligam_ao_jogo_e_ao_clube_sem_caminho_duplo():
    ativas = {(r[0], r[1], r[2], r[3]) for r in g.R if r[4]}
    for t in ("fato_escalacao", "fato_substituicao", "fato_ingresso", "fato_despesa", "fato_rateio", "fato_comissao"):
        assert (t, "id_partida", "fato_partida", "id_partida") in ativas, t
    for t in ("fato_escalacao", "fato_substituicao", "fato_comissao", "fato_rateio"):
        assert (t, "id_clube", "dim_clube", "id_clube") in ativas, t
    assert not any(r[0] in ("fato_ingresso", "fato_despesa") and r[2] == "dim_clube" for r in g.R)  # o clube chega a ingressos e despesas pela partida (USERELATIONSHIP)
    assert ("fato_escalacao", "id_atleta", "dim_atleta", "id_atleta") in ativas and ("fato_substituicao", "id_atleta_entrou", "dim_atleta", "id_atleta") in ativas
    assert len([r for r in g.R if r[0] == "fato_substituicao" and r[2] == "dim_atleta"]) == 2 and len([r for r in g.R if r[0] == "fato_substituicao" and r[2] == "dim_atleta" and r[4]]) == 1


def test_o_verificador_acusa_o_atleta_ligado_ao_clube_de_forma_ativa(monkeypatch):
    # com dim_atleta -> dim_clube ativa, o clube chegaria a fato_escalacao por dois caminhos (direto e pelo atleta)
    alterada = [(*r[:4], True, r[5]) if (r[0], r[1]) == ("dim_atleta", "id_clube") else r for r in g.R]
    monkeypatch.setattr(g, "R", alterada)
    assert any("dim_clube para fato_escalacao" in e for e in g.conferir_ambiguidade())
