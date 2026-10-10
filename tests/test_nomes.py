import sys
from collections import Counter
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import nomes  # noqa: E402
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
precisa_dados = pytest.mark.skipif(not all((PROC / n).exists() for n in ("dim_atleta.csv", "fato_evento.csv", "fato_escalacao.csv")), reason="rode scripts/04_tratar.py antes")


# ---------- regras de nome, com nomes inventados ----------

def test_apelido_todo_em_maiusculas_vira_so_a_inicial_maiuscula_e_o_resto_fica_como_esta():
    assert nomes.caixa_do_apelido("EVERTON") == "Everton"
    assert nomes.caixa_do_apelido("RAFA SILVA") == "Rafa Silva"
    assert nomes.caixa_do_apelido("Gabigol") == "Gabigol"
    assert nomes.caixa_do_apelido("PH") == "PH"
    assert nomes.caixa_do_apelido("  Moisés ") == "Moisés"


def test_nome_curto_vale_o_apelido_ou_o_primeiro_nome_com_o_ultimo_sobrenome_sem_particulas():
    assert nomes.nome_curto("Luciano da Rocha Neves") == "Luciano Neves"
    assert nomes.nome_curto("Fulano de Tal") == "Fulano Tal"
    assert nomes.nome_curto("Neymar") == "Neymar"
    assert nomes.nome_curto("Gabriel Barbosa Almeida", "Gabigol") == "Gabigol"
    assert nomes.nome_curto("Everton Leandro de Oliveira Santo", "EVERTON") == "Everton"


def test_palavra_cortada_pela_sumula_so_sai_do_nome_curto_se_sobrar_nome_e_sobrenome():
    assert nomes.nome_curto("Vinicius dos Santos de Oliveira P", truncado=True) == "Vinicius Oliveira"
    assert nomes.nome_curto("Ana Mari", truncado=True) == "Ana Mari"


def test_filho_e_junior_contam_como_sobrenome_no_atleta_mas_a_comissao_pula_os_sufixos():
    assert nomes.nome_curto("Alberto Magno Santos de Melo Filho") == "Alberto Filho"
    assert nomes.nome_de_comissao("Luiz Felipe Scolari Filho") == "Luiz Scolari"
    assert nomes.nome_de_comissao("Carlos Alberto Junior") == "Carlos Alberto"
    assert nomes.nome_de_comissao("Ze Junior") == "Ze Junior"
    assert nomes.nome_de_comissao("Dorival") == "Dorival"


def test_nome_cortado_em_33_letras_so_se_completa_com_um_nome_mais_comprido_que_comeca_igual():
    cortado = "Alberto Magno Santos de Melo Filh"
    assert len(cortado) == nomes.TAMANHO_NOME_SUMULA
    inteiro = "Alberto Magno Santos de Melo Filho"
    assert nomes.completar_nome(cortado, Counter({inteiro: 3, "Outro Nome Qualquer": 5})) == inteiro
    assert nomes.completar_nome(cortado, Counter({cortado: 2})) is None
    assert nomes.completar_nome(cortado, Counter({"Alberto Magno Santos de Mello Filho": 2})) is None
    assert nomes.completar_nome("Nome Curto", Counter({"Nome Curto Completo": 1})) is None
    assert nomes.completar_nome(cortado, Counter()) is None


def test_completar_nome_ignora_acentos_e_caixa_prefere_o_mais_frequente_e_desempata_em_ordem_alfabetica():
    cortado = "Joao Victor Araujo de Albuquerque"
    assert len(cortado) == nomes.TAMANHO_NOME_SUMULA
    com_acento, em_caixa_alta = "João Victor Araújo de Albuquerque Neto", "JOAO VICTOR ARAUJO DE ALBUQUERQUE FILHO"
    assert nomes.completar_nome(cortado, Counter({com_acento: 3, em_caixa_alta: 2})) == com_acento
    assert nomes.completar_nome(cortado, Counter({com_acento: 1, em_caixa_alta: 2})) == em_caixa_alta
    assert nomes.completar_nome(cortado, Counter({com_acento: 2, em_caixa_alta: 2})) == min(com_acento, em_caixa_alta)


def _atleta(i, clube, nome, curto, truncado=0, **extra):
    return {"id_atleta": i, "id_clube": clube, "nome": nome, "nome_truncado": truncado, "nome_curto": curto, **extra}


def test_nomes_curtos_repetidos_no_mesmo_clube_passam_a_nome_e_sobrenome_e_so_eles():
    atletas = [_atleta("a", 1, "Pedro Santana Silva", "Pedro"), _atleta("b", 1, "Pedro Henrique Lima", "Pedro"), _atleta("c", 1, "Marcos Souza", "Marcos"), _atleta("d", 2, "Pedro Dois", "Pedro")]
    nomes.desambiguar(atletas)
    assert [a["nome_curto"] for a in atletas] == ["Pedro Silva", "Pedro Lima", "Marcos", "Pedro"]


def test_se_nome_e_sobrenome_ainda_empatam_entra_a_inicial_do_nome_do_meio_e_depois_o_nome_do_meio_so_para_quem_ainda_repete():
    atletas = [_atleta("a", 1, "Gabriel Barbosa Santos", "Gabriel"), _atleta("b", 1, "Gabriel Almeida Santos", "Gabriel"), _atleta("c", 1, "Gabriel Batista Santos", "Gabriel")]
    nomes.desambiguar(atletas)
    assert [a["nome_curto"] for a in atletas] == ["Gabriel Barbosa Santos", "Gabriel A. Santos", "Gabriel Batista Santos"]


def test_desambiguar_usa_o_nome_ja_completado_pelos_gols_e_cartoes_quando_ele_existe():
    atletas = [_atleta("a", 1, "Pedro Henrique da Silva Santa", "Pedro", 1, _nome="Pedro Henrique da Silva Santana", _truncado=False), _atleta("b", 1, "Pedro Lima", "Pedro")]
    nomes.desambiguar(atletas)
    assert [a["nome_curto"] for a in atletas] == ["Pedro Santana", "Pedro Lima"]


def test_nome_curto_por_pessoa_liga_o_gol_ou_cartao_ao_atleta_da_camisa_e_pula_comissao_e_espn():
    escalacao = [{"id_partida": "1", "id_clube": "10", "numero_camisa": "9", "id_atleta": "x"}, {"id_partida": "1", "id_clube": "10", "numero_camisa": "7", "id_atleta": "y"}]
    atletas = [{"id_atleta": "x", "nome_curto": "Fulano"}, {"id_atleta": "y", "nome_curto": "Beltrano"}]
    base = {"id_evento": "1-01", "id_partida": "1", "id_clube": "10", "funcao": "Atleta", "fonte": "SUMULA"}
    eventos = [{**base, "numero_camisa": "9", "pessoa": "Fulano de Tal da Silva"}, {**base, "numero_camisa": "9", "pessoa": "Fulano de Tal da Silva"},
               {**base, "numero_camisa": "7", "pessoa": "Beltrano Souza"}, {**base, "funcao": "Técnico", "numero_camisa": "", "pessoa": "Técnico Qualquer"},
               {**base, "fonte": "ESPN", "numero_camisa": "", "pessoa": "Cobrador da ESPN"}]
    assert nomes.curto_por_pessoa(eventos, escalacao, atletas) == {"Fulano de Tal da Silva": "Fulano", "Beltrano Souza": "Beltrano"}


def test_nome_curto_por_pessoa_para_se_a_camisa_nao_esta_na_relacao_ou_se_o_nome_serve_a_dois_atletas():
    escalacao = [{"id_partida": "1", "id_clube": "10", "numero_camisa": "9", "id_atleta": "x"}, {"id_partida": "2", "id_clube": "10", "numero_camisa": "9", "id_atleta": "y"}]
    atletas = [{"id_atleta": "x", "nome_curto": "Fulano"}, {"id_atleta": "y", "nome_curto": "Beltrano"}]
    base = {"id_partida": "1", "id_clube": "10", "funcao": "Atleta", "fonte": "SUMULA", "pessoa": "Fulano de Tal"}
    with pytest.raises(SystemExit, match="camisa que não está na relação de jogadores"):
        nomes.curto_por_pessoa([{**base, "id_evento": "1-01", "numero_camisa": "10"}], escalacao, atletas)
    with pytest.raises(SystemExit, match="dois atletas diferentes"):
        nomes.curto_por_pessoa([{**base, "id_evento": "1-01", "numero_camisa": "9"}, {**base, "id_evento": "2-01", "id_partida": "2", "numero_camisa": "9"}], escalacao, atletas)


# ---------- as mesmas regras, nos dados reais ----------

@precisa_dados
def test_nenhum_clube_tem_dois_atletas_com_o_mesmo_nome_curto():
    atletas = ler_csv(PROC / "dim_atleta.csv")
    assert len(atletas) == 505
    assert max(Counter((a["id_clube"], a["nome_curto"]) for a in atletas).values()) == 1


@precisa_dados
def test_apelido_em_maiusculas_da_sumula_fica_guardado_como_veio_e_o_nome_curto_o_corrige():
    atletas = ler_csv(PROC / "dim_atleta.csv")
    caixa_alta = [a for a in atletas if a["apelido"] and len(a["apelido"]) > 3 and a["apelido"] == a["apelido"].upper()]
    assert [(a["apelido"], a["nome_curto"]) for a in caixa_alta] == [("EVERTON", "Everton")]
    assert not any(len(a["nome_curto"]) > 3 and a["nome_curto"] == a["nome_curto"].upper() for a in atletas)


@precisa_dados
def test_dim_atleta_guarda_o_nome_da_relacao_como_veio_e_o_nome_curto_usa_o_nome_inteiro_dos_eventos():
    atletas = ler_csv(PROC / "dim_atleta.csv")
    cortados = [a for a in atletas if a["nome_truncado"] == "1"]
    assert len(cortados) == 55 and all(len(a["nome"]) == nomes.TAMANHO_NOME_SUMULA for a in cortados)
    assert all(a["nome_truncado"] == "0" for a in atletas if len(a["nome"]) < nomes.TAMANHO_NOME_SUMULA)
    camisa = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e["id_atleta"] for e in ler_csv(PROC / "fato_escalacao.csv")}
    inteiros = {}
    for e in ler_csv(PROC / "fato_evento.csv"):
        if e["funcao"] == "Atleta" and e["fonte"] == "SUMULA":
            inteiros.setdefault(camisa[(e["id_partida"], e["id_clube"], e["numero_camisa"])], set()).add(e["pessoa"])
    completos = [a for a in cortados if any(len(p) > len(a["nome"]) for p in inteiros.get(a["id_atleta"], ()))]
    assert len(completos) == 14 and len(cortados) - len(completos) == 41
    curto = {a["nome"]: a["nome_curto"] for a in atletas}
    assert curto["Alberto Magno Santos de Melo Filh"] == "Alberto Filho"
    assert curto["Carlos Adalberto de Oliveira Juni"] == "Carlos Junior"
    assert curto["Hugo Sanches Nogueira Ribeiro Mag"] == "Hugo Magalhães"
    assert curto["Antonio Josenildo Rodrigues de Ol"] == "Antonio Rodrigues"
    assert curto["Cesar Augusto Soares dos Reis Rib"] == "Cesar Reis"
