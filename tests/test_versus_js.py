import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

PROC = RAIZ / "data" / "processed"
FRAGMENTO = RAIZ / "prototype" / "versus" / "fragmento.html"
HARNESS = RAIZ / "tests" / "js_harness.js"
precisa_dados = pytest.mark.skipif(not (PROC / "ref_indicadores.csv").exists(), reason="rode scripts/04_tratar.py e 05_validar.py antes")
precisa_node = pytest.mark.skipif(shutil.which("node") is None, reason="precisa do Node")

DIRECAO = {"pos1": -1, "pts1": 1, "aprov": 1, "v": 1, "d": -1, "gp": 1, "gc": -1, "sg": 1, "cpj": -1, "pubm": 1}


def gerador():
    spec = importlib.util.spec_from_file_location("versus11js", RAIZ / "scripts" / "11_montar_versus.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rodar(arq, extra=None):
    cmd = ["node", str(HARNESS), str(arq)] + ([extra] if extra else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert r.returncode == 0, r.stderr[:600]
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def dados():
    return gerador().montar_dados()


@pytest.fixture(scope="module")
def pagina(tmp_path_factory, dados):
    g = gerador()
    arq = tmp_path_factory.mktemp("js") / "pagina.html"
    arq.write_text("<html><body>" + FRAGMENTO.read_text(encoding="utf-8").replace("__DADOS__", g.dados_json(dados)) + "</body></html>", encoding="utf-8")
    return arq


@pytest.fixture(scope="module")
def saida(pagina):
    return rodar(pagina)


def por_curto(dados, nome):
    return next(c for c in dados["clubes"] if c["curto"] == nome)


def par(saida, a, b):
    return next(p for p in saida["pares"] if p["a"] == a["id"] and p["b"] == b["id"])


def css():
    t = FRAGMENTO.read_text(encoding="utf-8")
    return t[t.index("<style>"): t.index("</style>")]


@precisa_dados
@precisa_node
def test_sem_erro_de_execucao_em_todos_os_duelos_jogos_e_listas(saida):
    assert saida["erros"] == []
    assert len(saida["pares"]) == 16 * 15


@precisa_dados
@precisa_node
def test_contagem_de_criterios_bate_com_calculo_independente(saida, dados):
    cl = {c["id"]: c for c in dados["clubes"]}
    for p in saida["pares"]:
        A, B = cl[p["a"]], cl[p["b"]]
        ga = gb = emp = 0
        for k, d in DIRECAO.items():
            if A[k] == B[k]:
                emp += 1
            elif (A[k] > B[k]) == (d == 1):
                ga += 1
            else:
                gb += 1
        assert (ga, gb, emp) == (p["ga"], p["gb"], p["emp"]) and p["tot"] == 10, (A["curto"], B["curto"])


@precisa_dados
@precisa_node
def test_quem_fica_a_frente_na_1a_fase_bate_com_a_posicao_oficial(saida, dados):
    cl = {c["id"]: c for c in dados["clubes"]}
    chave = lambda c: (c["pts1"], c["v1"], c["sg1"], c["gp1"], -c["ve1"], -c["am1"])
    for p in saida["pares"]:
        A, B = cl[p["a"]], cl[p["b"]]
        if chave(A) == chave(B):
            assert p["dec"] is None
            continue
        a_frente = A if chave(A) > chave(B) else B
        assert p["dec"]["f"] == a_frente["id"], (A["curto"], B["curto"])
        assert a_frente["pos1"] < (B if a_frente is A else A)["pos1"], (A["curto"], B["curto"])
        assert a_frente["curto"] in p["fase1"]


@precisa_dados
@precisa_node
def test_frases_do_duelo_da_final(saida, dados):
    pal, nov = por_curto(dados, "Palmeiras"), por_curto(dados, "Novorizontino")
    p = par(saida, pal, nov)
    assert p["criterios"] == "Palmeiras vence em 5 dos 10 critérios e Novorizontino em 3; 2 empatam."
    assert p["fase1"] == "Na 1ª fase os dois fizeram 16 pontos; no desempate (Art. 16), Novorizontino ficou à frente no saldo de gols (+6 contra +1)."
    assert p["confronto"] == "Confronto direto em 2026: 3 jogos, Palmeiras 2 vitórias, Novorizontino 1 vitória."
    assert par(saida, nov, pal)["confronto"] == "Confronto direto em 2026: 3 jogos, Novorizontino 1 vitória, Palmeiras 2 vitórias."


@precisa_dados
@precisa_node
def test_frases_sem_confronto_e_com_penaltis(saida, dados):
    assert par(saida, por_curto(dados, "Botafogo"), por_curto(dados, "Corinthians"))["confronto"] == "Não se enfrentaram em 2026."
    assert par(saida, por_curto(dados, "Corinthians"), por_curto(dados, "Portuguesa"))["confronto"] == "Confronto direto em 2026: 1 jogo, Portuguesa 1 × 1 Corinthians (Corinthians 8 × 7 nos pênaltis)."


@precisa_dados
@precisa_node
def test_toda_frase_tem_pontuacao_final_e_nenhum_valor_indefinido(saida):
    for p in saida["pares"]:
        for t in (p["criterios"], p["fase1"], p["confronto"]):
            assert t.endswith(".") and "undefined" not in t and "NaN" not in t and "null" not in t


@precisa_dados
@precisa_node
def test_jornada_tem_um_cartao_por_jogo_na_ordem_da_forma(saida, dados):
    for c in dados["clubes"]:
        j = saida["jornada"][c["id"]]
        assert j["letras"] == "".join(f[0] for f in c["forma"]), c["curto"]
        assert j["tips"] == c["j"], c["curto"]


@precisa_dados
@precisa_node
def test_todo_lance_aparece_no_lado_do_time_certo_com_o_escudo_dele(saida):
    assert len(saida["campo"]) == 72
    for jogo, v in saida["campo"].items():
        assert v["marcasM"] == v["esperadoM"] and v["marcasV"] == v["esperadoV"], jogo
    t = saida["times"]
    assert t["semEscudo"] == [] and t["semFaixa"] == []
    assert t["eventos"] == 585 and t["semNomeNoTooltip"] == 0


@precisa_dados
@precisa_node
def test_campo_sem_nenhuma_sobreposicao_e_dentro_da_faixa_de_cada_time(saida):
    L = saida["layout"]
    assert L["jogos"] == 72 and L["itens"] > 500
    assert L["colide"] == 0, L["colide"]
    assert L["sobrepostos"] == [], L["sobrepostos"][:5]
    assert L["foraDaFaixa"] == [], L["foraDaFaixa"][:5]


@precisa_dados
@precisa_node
def test_campo_agrupa_cartoes_proximos_e_quase_todo_gol_tem_rotulo(saida):
    L = saida["layout"]
    grupos = sum(v["grupos"] for v in saida["campo"].values())
    eventos = sum(v["esperadoM"] + v["esperadoV"] for v in saida["campo"].values())
    assert grupos < eventos
    assert L["golsTotal"] == 168 and L["golsSemTexto"] <= 10


@precisa_dados
@precisa_node
def test_tooltips_de_gols_e_cartoes_trazem_jogador_time_e_motivo(saida):
    t = saida["tips"]
    assert t["total"] == 585 and t["vazios"] == 0 and t["golsSemTexto"] == 0
    assert t["cartoesComMotivoEsperado"] == 417 and t["cartoesComMotivo"] == 417


@precisa_dados
@precisa_node
def test_tooltips_do_comparativo_tem_titulo_dois_clubes_definicao_e_nota(saida):
    c = saida["compEstrutura"]
    assert c["linhas"] == 240 * 11 and c["ok"] == c["linhas"], c["falhas"]
    assert c["grupos"] == 240 * 3 and c["gruposComTip"] == c["grupos"]
    assert "Gols sofridos" in saida["rotulos"] and "Gols contra" not in saida["rotulos"]
    assert saida["linhas"][:3] == ["pos1", "pts1", "aprov"]


@precisa_dados
@precisa_node
def test_tooltip_monta_titulo_linhas_com_destaque_paragrafo_e_nota_e_escapa_html(saida):
    h = saida["tipHtml"]["completo"]
    assert h.startswith("<b>Título</b>") and '<div class="tv">' in h and '<div class="li"><span>A</span><em>1</em></div>' in h
    assert "<span>Parágrafo</span>" in h and "<small>Nota</small>" in h
    assert "&lt;b&gt;" in saida["tipHtml"]["escapado"] and "&quot;y&quot;" in saida["tipHtml"]["escapado"]


@precisa_dados
@precisa_node
def test_placar_do_jogo_tem_times_placar_e_ficha_no_tooltip(saida):
    assert saida["placar"]["jogos"] == 72 and saida["placar"]["falhas"] == []


@precisa_dados
@precisa_node
def test_mouse_inclina_escudos_e_acende_a_luz_com_suavidade_e_volta_ao_repouso(saida):
    assert saida["alvoCanto"] == {"tx": 1, "ty": -1, "to": 1}
    assert saida["alvoPainel"] == {"tx": 0, "ty": 0, "to": 0}
    assert saida["alvoEsquerda"]["tx"] < -0.8 and saida["alvoEsquerda"]["to"] == 1
    ida, volta, io, vo = saida["pzIda"], saida["pzVolta"], saida["pzIdaO"], saida["pzVoltaO"]
    assert ida[0] < 0.2 and ida[-1] > 0.99 and io[0] < 0.25 and io[-1] > 0.99
    assert all(b >= a for a, b in zip(ida, ida[1:])) and all(b <= a for a, b in zip(volta, volta[1:]))
    assert all(b >= a for a, b in zip(io, io[1:])) and all(b <= a for a, b in zip(vo, vo[1:]))
    assert volta[-1] < 0.01 and vo[-1] < 0.01 and max(abs(x) for x in ida + volta) <= 1.0


@precisa_dados
@precisa_node
def test_brasas_mais_suaves_e_dentro_do_teto(saida):
    c = saida["cfgBrasas"]
    assert 300 < saida["brasas"] < c["teto"]
    assert c["alfa"] <= 0.8 and c["halo"] <= 0.16 and c["taxa"] <= 0.85 and c["tmax"] <= 3.9 and c["vmax"] <= 2.3 and c["rajada"] <= 130


@precisa_dados
@precisa_node
def test_gancho_de_teste_so_existe_com_debug(pagina):
    assert rodar(pagina, "sem-debug") == {"semGancho": True}


def test_sem_botao_pular_nem_placar_em_cima_do_vs_com_rodape_ajuda_e_aviso():
    t = FRAGMENTO.read_text(encoding="utf-8")
    assert "pular" not in t.lower() and "psc" not in t
    assert "Projeto independente, sem vínculo com a FPF" in t
    assert 'data-act="ajuda"' in t and "Como ler esta tela" in t and "conferidos por" in t


def test_efeito_do_mouse_nao_mexe_no_fundo_nem_na_marca_dagua():
    t = FRAGMENTO.read_text(encoding="utf-8")
    assert "vx-deriva" not in t
    assert "e.fa" not in t and "e.fb" not in t and "e.na" not in t and "e.vsb" not in t
    assert "mix-blend-mode:soft-light;opacity:0}" in t and ".foco" in t


def test_caixas_inclinadas_nao_cortam_conteudo_e_tem_margem_para_os_numeros():
    c = css()
    for seletor in (r"\.pnl", r"\.fl\.a", r"\.fl\.b", r"\.cen"):
        regras = re.findall(r"#vsx " + seletor + r"\{([^}]*)\}", c)
        assert regras and not any("clip-path" in r for r in regras), seletor
    assert "#vsx .cen::before{clip-path" in c and "#vsx .fl.a::before{clip-path" in c and "#vsx .fl.b::before{clip-path" in c
    assert re.search(r"#vsx \.cen\{[^}]*padding:12px 40px", c)
    assert re.search(r"#vsx \.fl\.a\{[^}]*padding-right:40px", c) and re.search(r"#vsx \.fl\.b\{[^}]*padding-left:40px", c)


def test_nenhuma_fonte_abaixo_de_16_px():
    t = FRAGMENTO.read_text(encoding="utf-8")
    tamanhos = [float(x) for x in re.findall(r"font-size:([\d.]+)px", css())]
    tamanhos += [float(x) for x in re.findall(r"font:(?:italic )?(?:\d{3} )?([\d.]+)px", css())]
    tamanhos += [float(x) for x in re.findall(r'font-size="([\d.]+)"', t)]
    assert len(tamanhos) > 40
    assert min(tamanhos) >= 16, sorted(tamanhos)[:5]


@precisa_dados
def test_tamanho_total_da_pagina_cabe_no_orcamento(dados):
    g = gerador()
    total = len(FRAGMENTO.read_text(encoding="utf-8")) + len(g.dados_json(dados))
    assert total < 300_000, total


def decodifica(t):
    return t.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def milhar(n):
    return f"{n:,}".replace(",", ".")


def rotulo_do_jogo(j):
    return ["", f"1ª fase · rodada {j['r']}", "Quartas de final", "Semifinal", "Final · jogo de ida" if j["r"] == 11 else "Final · jogo de volta"][j["f"]]


@precisa_dados
@precisa_node
def test_cada_botao_de_fase_da_escolha_do_duelo_diz_quantos_jogos_mostra(saida, dados):
    nomes = ["Todas as fases", "1ª fase", "Quartas de final", "Semifinal", "Final"]
    rotulos = ["Todas", "1ª fase", "Quartas", "Semifinal", "Final"]
    for escolhida in range(5):
        h = saida["listaDuelo"][str(escolhida)]["filtros"]
        botoes = re.findall(r'<button class="chp( on)?" data-act="filtro" data-v="(\d)" data-tip="([^"]*)"><span>([^<]*)</span></button>', h)
        assert [(int(v), rot) for _, v, _, rot in botoes] == list(enumerate(rotulos))
        assert [bool(on) for on, _, _, _ in botoes] == [i == escolhida for i in range(5)]
        for _, v, tip, _ in botoes:
            i = int(v)
            n = sum(1 for j in dados["jogos"] if not i or j["f"] == i)
            titulo, texto = decodifica(tip).split("||")
            assert titulo == nomes[i]
            assert texto == f"{'Mostra só os' if i else 'Mostra os'} {n} jogos {'desta fase.' if i else 'do campeonato.'} Clique em um jogo da lista para abrir o duelo dele."
    assert [sum(1 for j in dados["jogos"] if not i or j["f"] == i) for i in range(5)] == [72, 64, 4, 2, 2]


@precisa_dados
@precisa_node
def test_cada_cartao_de_jogo_da_escolha_do_duelo_tem_dica_com_fase_data_estadio_publico_e_penaltis(saida, dados):
    por_id = {j["i"]: j for j in dados["jogos"]}
    clube = {c["id"]: c for c in dados["clubes"]}
    for escolhida in range(5):
        h = saida["listaDuelo"][str(escolhida)]["lista"]
        cartoes = re.findall(r'<button class="gcard" data-act="abrir-jogo" data-id="([^"]+)" data-tip="([^"]*)">', h)
        esperados = [j for j in dados["jogos"] if not escolhida or j["f"] == escolhida]
        assert [i for i, _ in cartoes] == [j["i"] for j in esperados]
        for i, tip in cartoes:
            j = por_id[i]
            titulo, tabela, nota = decodifica(tip).split("||")
            assert titulo == f"{clube[j['m']]['curto']} {j['gm']} × {j['gv']} {clube[j['v']]['curto']}"
            ano, mes, dia = j["d"].split("-")
            linhas = [("Fase", rotulo_do_jogo(j)), ("Data", f"{dia}/{mes}/{ano} às {j['h']}"), ("Estádio", f"{j['e']} · {j['c']}"), ("Público", f"{milhar(j['pu'])} pessoas")]
            if j["pm"] is not None:
                linhas.append(("Pênaltis", f"{j['pm']} × {j['pv']}"))
            assert tabela == "@" + "\n".join(f"{a}::{b}" for a, b in linhas)
            assert nota == "Clique para abrir o duelo deste jogo."
    assert len(re.findall(r'<button class="gcard" ', saida["listaDuelo"]["0"]["lista"])) == 72


@precisa_dados
@precisa_node
def test_atalhos_do_duelo_tem_dica_com_o_jogo_a_data_e_a_frase_de_abrir(saida, dados):
    botoes = re.findall(r'<button class="chp" data-act="abrir-jogo" data-id="([^"]+)" data-tip="([^"]*)"><span>([^<]*)</span></button>', saida["atalhosDuelo"])
    assert [rot for _, _, rot in botoes] == ["Final · volta", "Maior público", "Maior goleada"]
    for _, tip, rot in botoes:
        secoes = decodifica(tip).split("||")
        assert secoes[0] == rot and secoes[1].startswith("@Jogo::") and "\nData::" in secoes[1] and secoes[-1].endswith(" Clique para abrir o duelo.")


@precisa_dados
@precisa_node
def test_botoes_do_confronto_direto_tem_dica_com_fase_data_e_penaltis_quando_houve(saida, dados):
    clube = {c["curto"]: c["id"] for c in dados["clubes"]}
    nome = {c["id"]: c["curto"] for c in dados["clubes"]}
    pares = {"palNov": ("Palmeiras", "Novorizontino"), "porCor": ("Portuguesa", "Corinthians")}
    total = 0
    for chave, (a, b) in pares.items():
        ids = {clube[a], clube[b]}
        jogos = [j for j in dados["jogos"] if {j["m"], j["v"]} == ids]
        botoes = re.findall(r'<button class="gj( on)?" data-act="jogo" data-id="([^"]+)" data-tip="([^"]*)">', saida["confrontoDireto"][chave])
        assert [i for _, i, _ in botoes] == [j["i"] for j in jogos] and len([1 for on, _, _ in botoes if on]) == 1
        for _, i, tip in botoes:
            j = next(x for x in jogos if x["i"] == i)
            titulo, tabela, nota = decodifica(tip).split("||")
            ano, mes, dia = j["d"].split("-")
            linhas = [("Fase", rotulo_do_jogo(j)), ("Data", f"{dia}/{mes}/{ano}")] + ([("Pênaltis", f"{j['pm']} × {j['pv']}")] if j["pm"] is not None else [])
            assert titulo == f"{nome[j['m']]} {j['gm']} × {j['gv']} {nome[j['v']]}"
            assert tabela == "@" + "\n".join(f"{x}::{y}" for x, y in linhas) and nota == "Clique para ver os gols e cartões deste jogo."
            total += 1
    assert total == 4


@precisa_dados
@precisa_node
def test_painel_do_clube_escolhido_diz_ponto_jogo_e_gol_no_singular_quando_o_numero_e_um(saida, dados):
    assert len(saida["paineisSel"]) == 16
    for p in saida["paineisSel"]:
        c = next(x for x in dados["clubes"] if x["id"] == p["id"])
        assert f"<b>{c['pts1']} {'ponto' if c['pts1'] == 1 else 'pontos'}</b> ({c['v1']}V {c['e1']}E {c['d1']}D)" in p["html"], c["curto"]
        assert f"{c['j']} {'jogo' if c['j'] == 1 else 'jogos'} · {c['gp']} {'gol marcado' if c['gp'] == 1 else 'gols marcados'}" in p["html"], c["curto"]
    ponte = next(c for c in dados["clubes"] if c["curto"] == "Ponte Preta")
    assert ponte["pts1"] == 1
    assert "<b>1 ponto</b>" in next(p for p in saida["paineisSel"] if p["id"] == ponte["id"])["html"]
