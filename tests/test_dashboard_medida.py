import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

PROC = RAIZ / "data" / "processed"
precisa_dados = pytest.mark.skipif(not (PROC / "ref_indicadores.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")
LIMITE_TESTADO = 800_000  # TESTADO: o maior texto já visto renderizando no Power BI Desktop tem 795.218 caracteres (a página com oito telas); passar disso exige abrir a página nova no Desktop e só então subir este número


def gerador():
    spec = importlib.util.spec_from_file_location("medida14", RAIZ / "scripts" / "14_gerar_medida_dashboard.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


g = gerador()
CODIGO = '<style>\n#a{font-family:"Segoe UI",Arial}\n</style>\n<script>\nvar G=__DADOS_VG__;\nvar J=__DADOS_GL__;\nvar S=__DADOS_DS__;\nvar K=__DADOS_JG__;\nvar D=__DADOS_VS__;\nvar F=__DADOS_FIN__;\nvar L=__DADOS_CLAS__;\nvar C=__DADOS_CONF__;\nconsole.log("oi");\n</script>'
DADOS = {
    "gl": '{"gols":[{"j":1,"mn":28,"t":"g"}],"t":"Gols · ⚽ 168"}',
    "ds": '{"cart":[{"j":1,"mn":null,"t":"a"}],"t":"Disciplina · 🟨 413"}',
    "jg": '{"esc":[[[[1,2,90]]]],"t":"Jogos · ↓67 ↑int. · 3.292"}',
    "vg": '{"j":[{"n":1,"g":"3 × 1"}],"t":"Visão geral · ★ 72 jogos"}',
    "vs": '{"a":"x\\"y","b":[1,2,3],"c":"ã · ×"}',
    "fin": '{"f":[10,20],"g":"R$ 1,5 mi — ok"}',
    "clas": '{"t":[{"c":1,"p":1}],"m":"Classificação · ★"}',
    "conf": '{"r":[1,2,3],"t":"Conferência e fontes · ✔ 45 regras"}',
}
PAGINA = CODIGO
for chave_, texto_ in DADOS.items():
    PAGINA = PAGINA.replace(g.marca_de(chave_), texto_)


def montar(tamanho):
    pedacos = {"cod": g.dividir(CODIGO.replace("\n", g.MARCA), tamanho)}
    for chave, pre, *_ in g.PACOTES:
        pedacos[pre] = g.dividir(DADOS[chave], tamanho)
    tmdl, nm = g.montar_tmdl(pedacos)
    return pedacos, tmdl, nm


def todas_as_medidas(nm):
    return g.todos_os_nomes(nm) + g.junta_nomes() + ["html_dashboard"]


def test_cada_tela_do_app_tem_seu_pacote_de_dados_na_medida():
    app = g.modulo13()
    assert [t[0] for t in g.PACOTES] == ["vg", "vs", "gl", "ds", "jg", "fin", "clas", "conf"]
    assert {t[0] for t in app.TELAS} == {p[0] for p in g.PACOTES}
    assert {t[2] for t in app.TELAS} == {g.marca_de(p[0]) for p in g.PACOTES}


@pytest.mark.parametrize("tamanho", [7, 23, 50, 8000])
def test_remontagem_identica_com_aspas_quebras_e_oito_pacotes_de_dados(tamanho):
    _, tmdl, _ = montar(tamanho)
    assert g.remontar(tmdl) == PAGINA


def test_nenhum_pedaco_passa_do_limite_e_aspas_vem_aos_pares():
    pedacos, tmdl, _ = montar(23)
    assert all(len(p) <= 23 for lista in pedacos.values() for p in lista)
    for dentro in re.findall(r'^\tmeasure html_dashboard_(?:cod|dvg|dvs|dgl|dds|djg|dfn|dcl|dco)_\d\d = "(.*)"$', tmdl, re.M):
        assert not re.search(r'(?<!")"(?!")', dentro.replace('""', ""))


def test_medidas_finais_juntam_todos_os_pedacos_em_ordem_e_trocam_as_oito_marcas():
    pedacos, tmdl, nm = montar(23)
    todas = g.todos_os_nomes(nm)
    assert len(set(todas)) == len(todas)
    codigo = re.search(r"measure html_dashboard_codigo = SUBSTITUTE\((.*), \"~~NL~~\", UNICHAR\(10\)\)", tmdl).group(1)
    assert re.findall(r"\[(\w+)\]", codigo) == nm["cod"]
    for chave, pre, suf, *_ in g.PACOTES:
        junta = re.search(rf"measure html_dashboard_{suf} = (.*)", tmdl).group(1)
        assert re.findall(r"\[(\w+)\]", junta) == nm[pre], suf
    esperado = "[html_dashboard_codigo]"
    for chave, pre, suf, *_ in g.PACOTES:
        esperado = f'SUBSTITUTE({esperado}, "{g.marca_de(chave)}", [html_dashboard_{suf}])'
    assert f"measure html_dashboard = {esperado}" in tmdl
    assert tmdl.count("isHidden") == len(todas) + 1 + len(g.PACOTES) + 1  # pedaços, a que junta o código, as que juntam os dados e a coluna técnica; só html_dashboard fica visível


def test_consulta_de_conferencia_cobre_todos_os_pedacos():
    pedacos, tmdl, nm = montar(23)
    q = g.consulta({"nomes": nm})
    for n in todas_as_medidas(nm):
        assert f'"{n}"' in q


def test_soma_ponderada_pela_posicao():
    assert g.soma("ab") == 1 * ord("a") + 2 * ord("b")


def visual_texto(entidade, medida):
    campo = {"Measure": {"Expression": {"SourceRef": {"Entity": entidade}}, "Property": medida}}
    return json.dumps({"visual": {"query": {"queryState": {"content": {"projections": [{"field": campo, "queryRef": f"{entidade}.{medida}", "nativeQueryRef": medida}]}}}},
                       "filterConfig": {"filters": [{"name": "x", "field": campo, "type": "Advanced"}]}}, indent=2)


def test_visual_ligado_reconhece_so_a_medida_do_dashboard(tmp_path, monkeypatch):
    arq = tmp_path / "visual.json"
    monkeypatch.setattr(g, "VISUAL", arq)
    arq.write_text(visual_texto("aux_dashboard", "html_dashboard"), encoding="utf-8")
    assert g.visual_ligado() is True
    for entidade, medida in (("_Medidas", "Jogos"), ("aux_versus", "html_versus")):
        arq.write_text(visual_texto(entidade, medida), encoding="utf-8")
        assert g.visual_ligado() is False


def test_ligar_visual_troca_as_seis_referencias_e_e_idempotente(tmp_path, monkeypatch):
    arq = tmp_path / "visual.json"
    monkeypatch.setattr(g, "VISUAL", arq)
    arq.write_text(visual_texto("aux_versus", "html_versus"), encoding="utf-8")
    assert g.ligar_visual() == 6  # Entity e Property no campo e no filtro, queryRef e nativeQueryRef
    assert g.visual_ligado() is True
    depois = arq.read_text(encoding="utf-8")
    assert "aux_versus" not in depois and "html_versus" not in depois
    assert g.ligar_visual() == 0 and arq.read_text(encoding="utf-8") == depois


def test_modelo_registra_a_tabela_uma_so_vez_e_tira_a_antiga(tmp_path, monkeypatch):
    modelo = tmp_path / "model.tmdl"
    modelo.write_text("ref table _Medidas\nref table aux_config\nref table aux_versus\n\nref cultureInfo pt-BR\n", encoding="utf-8")
    monkeypatch.setattr(g, "MODELO", tmp_path)
    assert g.registrar_no_modelo() is True
    texto = modelo.read_text(encoding="utf-8")
    assert texto.count("ref table aux_dashboard") == 1 and "aux_versus" not in texto
    assert texto.index("ref table aux_config") < texto.index("ref table aux_dashboard") < texto.index("ref cultureInfo")
    assert g.registrar_no_modelo() is False


def test_modelo_sem_nenhuma_tabela_registra_antes_da_cultura(tmp_path, monkeypatch):
    modelo = tmp_path / "model.tmdl"
    modelo.write_text("model Model\n\nref cultureInfo pt-BR\n", encoding="utf-8")
    monkeypatch.setattr(g, "MODELO", tmp_path)
    assert g.registrar_no_modelo() is True
    texto = modelo.read_text(encoding="utf-8")
    assert texto.index("ref table aux_dashboard") < texto.index("ref cultureInfo")


def test_tabela_e_todas_as_medidas_saem_com_descricao_de_uma_linha():
    pedacos, tmdl, nm = montar(23)
    desc = g.descricoes_medidas(nm)
    assert set(desc) == set(todas_as_medidas(nm))
    assert all(d and "\n" not in d and len(d) < 400 for d in desc.values())
    linhas = tmdl.split("\n")
    assert linhas[0].startswith("/// Tabela técnica do dashboard") and linhas[1] == "table aux_dashboard"
    for i, l in enumerate(linhas):
        if l.startswith("\tmeasure "):
            assert linhas[i - 1] == "\t/// " + desc[l.split()[1]], l[:60]
    assert desc["html_dashboard"].startswith("Página completa do dashboard") and all(g.marca_de(p[0]) in desc["html_dashboard"] for p in g.PACOTES)
    assert f"Pedaço 1 de {len(nm['cod'])} do código" in desc[nm["cod"][0]]
    for chave, pre, suf, nome, _ in g.PACOTES:
        assert f"Pedaço {len(nm[pre])} de {len(nm[pre])} dos dados {nome}" in desc[nm[pre][-1]], chave
        assert f"{nome} em {len(nm[pre])}" in linhas[0], chave


@precisa_dados
def test_pagina_real_remonta_identica_tem_sintaxe_valida_e_cabe_no_limite_testado():
    p = g.preparar(8000)
    marcas = sum(len(g.marca_de(c[0])) for c in g.PACOTES)
    assert len(p["pagina"]) == len(p["codigo"]) - marcas + sum(len(t) for t in p["textos"].values())
    assert all(len(t) <= 8000 for lista in p["pedacos"].values() for t in lista)
    for texto in p["textos"].values():
        json.loads(texto.replace("<\\/", "</"))
    assert len(p["pagina"]) < LIMITE_TESTADO
    if shutil.which("node"):
        assert g.checar_js(p["pagina"]) == 10


@precisa_dados
def test_a_medida_gravada_no_projeto_e_a_pagina_atual():
    if not g.TABELA.exists():
        pytest.skip("rode scripts/14_gerar_medida_dashboard.py (com o Power BI fechado)")
    p = g.preparar(8000)
    tmdl = g.TABELA.read_text(encoding="utf-8")
    assert g.remontar(tmdl) == p["pagina"], "a medida do projeto está desatualizada em relação aos fragmentos ou aos dados: rode scripts/14_gerar_medida_dashboard.py com o Power BI fechado"
    assert not g.TABELA_ANTIGA.exists()


@precisa_dados
def test_recusa_gravar_com_o_desktop_aberto(tmp_path, monkeypatch):
    destino = tmp_path / "aux_dashboard.tmdl"
    monkeypatch.setattr(g, "TABELA", destino)
    monkeypatch.setattr(g, "desktop_aberto", lambda: True)
    monkeypatch.setattr(sys, "argv", ["14"])
    assert g.main() == 1 and not destino.exists()
