import importlib.util
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
MODELO = RAIZ / "powerbi" / "PaulistaAnalytics.SemanticModel" / "definition"


def gerador():
    spec = importlib.util.spec_from_file_location("med10", RAIZ / "scripts" / "10_gerar_medidas.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


g = gerador()


def test_definicoes_validas_e_todos_os_indicadores_cobertos():
    assert g.conferir_definicoes() == []
    assert len(g.M) == 72
    ids = {m[4] for m in g.M if m[4]}
    assert ids >= {f"I{i:02d}" for i in range(1, 60)}
    pastas = {m[0] for m in g.M}
    assert all(re.match(r"^\d\d ", p) for p in pastas) and len(pastas) == 12  # 10 pastas e as subpastas das faixas de minuto e do financeiro por clube


def test_mapas_do_gabarito_usam_so_medidas_que_existem():
    nomes = {m[1] for m in g.M}
    for mapa in (g.GERAL, g.FAIXAS, g.CLUBE, g.QUALIDADE, g.CATEGORIA, g.GRUPO, g.BLOCO):
        assert set(mapa.values()) <= nomes
    assert "Gols do atleta" in nomes
    consulta = g.consulta()
    sem_coluna = re.findall(r"(?<![\w\]])\[([^\]]+)\]", consulta)  # [Nome] sozinho = medida ou apelido de coluna
    assert set(sem_coluna) - nomes == {"ind", "escopo", "chave", "clube"}
    assert nomes >= set(sem_coluna) - {"ind", "escopo", "chave", "clube"}


def test_medidas_de_contagem_nunca_devolvem_vazio():
    for pasta, nome, dax, *_ in g.M:
        if nome in g.SEMPRE_ZERO:
            assert dax.endswith(" + 0"), nome
    assert {"Amarelos", "Vermelhos", "Empates", "Gols do atleta", "Ingressos em setor de visitante", "Atletas em campo", "Titulares", "Reservas que entraram", "Substituições", "Gols de reservas"} <= g.SEMPRE_ZERO


def test_medidas_do_clube_usam_userelationship_nas_duas_relacoes():
    for nome in ("Jogos do clube", "Gols pró", "Gols contra", "Pontos", "Público médio como mandante"):
        dax = next(m[2] for m in g.M if m[1] == nome)
        assert "id_clube_mandante" in dax
        if nome != "Público médio como mandante":
            assert "id_clube_visitante" in dax
    por_nome = {m[1]: m[2] for m in g.M}
    for nome in ("Renda bruta como mandante", "Renda líquida como mandante", "Torcida visitante recebida"):
        assert "id_clube_mandante" in por_nome[nome] and "id_clube_visitante" not in por_nome[nome], nome
    assert "id_clube_visitante" in por_nome["Torcida visitante levada"] and "id_clube_mandante" not in por_nome["Torcida visitante levada"]


def test_medidas_do_financeiro_leem_as_tabelas_novas_e_so_elas():
    por_nome = {m[1]: m[2] for m in g.M}
    assert "fato_despesa[valor]" in por_nome["Despesas"] and "fato_ingresso[arrecadacao]" in por_nome["Arrecadação dos ingressos"] and "fato_ingresso[ingressos]" in por_nome["Ingressos vendidos"]
    assert "fato_rateio[liquido]" in por_nome["Líquido a receber"] and "deducao_inss" in por_nome["Deduções"] and "deducao_outras" in por_nome["Deduções"]
    assert "setor_visitante] = 1" in por_nome["Ingressos em setor de visitante"]
    assert "ALL(fato_ingresso[categoria])" in por_nome["% dos ingressos"] and "ALL(fato_ingresso[categoria])" in por_nome["% da arrecadação"]
    assert "ALL(fato_despesa[grupo])" in por_nome["% das despesas"] and "ALL(fato_despesa[bloco_codigo])" in por_nome["% das despesas"]
    assert 'situacao] = "reserva"' in por_nome["Gols de reservas"] and "fato_substituicao" in por_nome["Substituições"] and "fato_escalacao[jogou] = 1" in por_nome["Atletas em campo"]


def csv(tmp_path, linhas):
    arq = tmp_path / "r.csv"
    arq.write_text("[ind],[escopo],[chave],[clube],[unidade],[ref],[medida]\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return arq


def test_comparador_aceita_igualdade_e_acusa_diferenca_e_vazio(tmp_path):
    ok = csv(tmp_path, ['I07,geral,,,%,"47,2222","0,4722222222222222"', 'I18,geral,,,R$/pagante,"58,74","58,7402"', "I01,geral,,,jogos,72,72", 'I11,geral,,,pessoas/jogo,"10894,0139","10894,013888888889"'])
    r = g.comparar(ok)
    assert (r["ok"], r["divergentes"], r["sem_valor"]) == (4, [], [])
    ruim = csv(tmp_path, ["I01,geral,,,jogos,72,71", 'I07,geral,,,%,"47,2222","0,50"', "I19,fase,FINAL,,jogos,0,"])
    r = g.comparar(ruim)
    assert r["ok"] == 0 and len(r["divergentes"]) == 2 and len(r["sem_valor"]) == 1


def test_o_gabarito_do_aproveitamento_nao_tem_arredondamento_duplo():
    # Botafogo: 11 pontos em 8 jogos = 45,8333% (e não 45,83, que vinha de arredondar a fração antes)
    import indicadores
    assert indicadores.pct(11, 24) == 45.8333


def test_modelo_salvo_pelo_desktop_tem_a_tabela_e_as_pastas():
    arq = MODELO / "tables" / "_Medidas.tmdl"
    if not arq.exists():
        pytest.skip("o Desktop ainda não salvou o projeto com a tabela _Medidas")
    texto = arq.read_text(encoding="utf-8")
    for pasta, nome, *_ in g.M:
        assert f"measure '{nome}'" in texto or f"measure {nome}" in texto, nome
    assert "displayFolder: 06 Classificação (Art. 16)" in texto or "displayFolder: '06 Classificação (Art. 16)'" in texto


def test_descricoes_completas_seguem_o_padrao_e_ficam_em_uma_linha():
    desc = g.definicoes_descricoes_mcp()
    assert len(desc) == 72 and [d["Name"] for d in desc] == [m[1] for m in g.M]
    for d, (pasta, nome, dax, fmt, ind, curta) in zip(desc, g.M):
        t = d["Description"]
        assert "\n" not in t and 150 < len(t) < 600, nome
        assert t.startswith(f"{ind}. {curta}" if ind else curta), nome
        assert curta.endswith("."), nome
        assert "Formato: " in t and ("Conferida linha a linha contra o gabarito" in t or "conferida contra a tabela oficial" in t), nome
    por_nome = {d["Name"]: d["Description"] for d in desc}
    assert "não filtra a partida" in por_nome["Jogos"] and "USERELATIONSHIP" in por_nome["Gols pró"]
    assert "Só faz sentido com um clube selecionado" in por_nome["Posição 1ª fase"] and "Só faz sentido com um clube selecionado" in por_nome["Chave Art. 16"]
    assert "Qualidade dos dados" in por_nome["Regras executadas"] and "atleta" in por_nome["Gols do atleta"]


def test_definicoes_de_criacao_usam_a_mesma_descricao():
    assert {d["Name"]: d["Description"] for d in g.definicoes_mcp()} == {d["Name"]: d["Description"] for d in g.definicoes_descricoes_mcp()}


def test_modelo_salvo_pelo_desktop_guarda_a_descricao_de_cada_medida():
    for tabela in ("_Medidas", "aux_dashboard"):
        arq = MODELO / "tables" / f"{tabela}.tmdl"
        if not arq.exists():
            pytest.skip("o Desktop ainda não salvou o projeto")
        linhas = arq.read_text(encoding="utf-8").split("\n")
        medidas = [i for i, l in enumerate(linhas) if l.startswith("\tmeasure ")]
        assert medidas, tabela
        for i in medidas:
            assert linhas[i - 1].startswith("\t/// "), f"{tabela}: {linhas[i][:60]} sem descrição"


def test_o_arquivo_tmdl_e_o_que_a_lista_produz_e_nao_perde_o_que_o_desktop_gravou():
    arq = MODELO / "tables" / "_Medidas.tmdl"
    atual = arq.read_text(encoding="utf-8")
    assert g.tmdl_medidas(atual) == atual and g.tmdl_medidas(g.tmdl_medidas(atual)) == atual
    linhas = atual.split("\n")
    assert linhas[0].startswith("/// Medidas DAX") and linhas[1] == "table _Medidas"
    achadas = re.findall(r"^\tmeasure (?:'((?:[^']|'')+)'|(\w+)) = ", atual, re.M)
    assert [a or b for a, b in achadas] == [m[1] for m in g.M]
    tags = re.findall(r"^\t\tlineageTag: (\S+)$", atual, re.M)
    assert len(tags) == len(set(tags)) == 73  # 72 medidas e a coluna técnica
    i, j = atual.index("\t/// I38. "), atual.index("\tcolumn Value")
    parcial = atual[:i] + atual[j:]
    assert parcial.count("\tmeasure ") == 50 and g.tmdl_medidas(parcial) == atual  # só com as 50 antigas: as 22 voltam, com os mesmos identificadores


def test_nomes_com_espaco_ou_simbolo_vao_entre_aspas_no_tmdl():
    assert g.nome_tmdl("Despesas") == "Despesas" and g.nome_tmdl("Deduções") == "Deduções"
    assert g.nome_tmdl("% despesas sobre renda bruta") == "'% despesas sobre renda bruta'" and g.nome_tmdl("Líquido a receber") == "'Líquido a receber'"
    assert g.nome_tmdl("d'agua") == "'d''agua'"


def test_recusa_gravar_com_o_desktop_aberto(tmp_path, monkeypatch):
    copia = tmp_path / "_Medidas.tmdl"
    copia.write_text("conteúdo do Desktop", encoding="utf-8")
    monkeypatch.setattr(g, "TMDL", copia)
    monkeypatch.setattr(g, "desktop_aberto", lambda: True)
    monkeypatch.setattr(sys, "argv", ["10", "--escrever-tmdl"])
    assert g.escrever_tmdl() == 1 and copia.read_text(encoding="utf-8") == "conteúdo do Desktop"
