import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import indicadores  # noqa: E402
import regras  # noqa: E402
from comum import placar_disputa_espn  # noqa: E402

PROC = RAIZ / "data" / "processed"
precisa_dados = pytest.mark.skipif(not (PROC / "fato_partida.csv").exists() or not (RAIZ / "data" / "raw" / "espn").exists(), reason="rode 01_coletar_espn, 03b_ler_fpf_pdf e 04_tratar antes")


def carregar_validar():
    spec = importlib.util.spec_from_file_location("validar05", RAIZ / "scripts" / "05_validar.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


validar05 = carregar_validar()


def contexto(**attrs):
    """Contexto mínimo para exercitar uma regra com dados inventados."""
    c = regras.Contexto.__new__(regras.Contexto)
    c.id_partida = attrs.pop("id_partida", {})
    for k, v in attrs.items():
        setattr(c, k, v)
    return c


def executar(codigo, c):
    r = next(r for r in regras.REGRAS if r["codigo"] == codigo)
    return r["funcao"](c)


# ---------- registro de regras e decisões ----------

def test_regras_tem_codigos_unicos_e_sequenciais():
    codigos = [r["codigo"] for r in regras.REGRAS]
    assert len(codigos) == len(set(codigos))
    assert codigos == [f"A{i:02d}" for i in range(1, len(codigos) + 1)]
    assert all(r["severidade"] in validar05.SEVERIDADES for r in regras.REGRAS)


def decisao(**kw):
    return {"codigo_regra": "A06", "id_partida": "*", "id_clube": "*", "fonte_a": "*", "status": "explicada", "severidade": "", "explicacao": "x", **kw}


def ocorrencia(**kw):
    return {"id_partida": 81351, "id_clube": None, "fonte_a": "ESPN", **kw}


def test_decisao_curinga_casa_e_especifica_vence():
    geral, especifica = decisao(), decisao(id_partida="81351")
    assert validar05.casa(geral, ocorrencia(), "A06") == 0
    assert validar05.casa(especifica, ocorrencia(), "A06") == 1
    assert validar05.casa(especifica, ocorrencia(id_partida=81384), "A06") is None
    assert validar05.casa(geral, ocorrencia(), "A07") is None


def test_decisao_por_fonte():
    d = decisao(codigo_regra="A32", fonte_a="dim_estadio.capacidade")
    assert validar05.casa(d, ocorrencia(id_partida=None, fonte_a="dim_estadio.capacidade"), "A32") == 1
    assert validar05.casa(d, ocorrencia(id_partida=None, fonte_a="fato_partida.id_var"), "A32") is None


def test_decisoes_invalidas_sao_recusadas(tmp_path, monkeypatch):
    cab = "codigo_regra;id_partida;id_clube;fonte_a;status;severidade;explicacao\n"
    arq = tmp_path / "d.csv"
    monkeypatch.setattr(validar05, "DECISOES", arq)
    arq.write_text(cab + "A06;*;*;*;talvez;baixa;texto\n", encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        validar05.ler_decisoes()
    arq.write_text(cab + "A06;*;*;*;explicada;baixa;\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sem explicação"):
        validar05.ler_decisoes()
    arq.write_text(cab + "A06;*;*;*;aberta;urgente;texto\n", encoding="utf-8")
    with pytest.raises(ValueError, match="severidade"):
        validar05.ler_decisoes()
    arq.write_text("codigo_regra;status\nA06;aberta\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colunas"):
        validar05.ler_decisoes()


# ---------- as regras novas detectam o defeito que prometem detectar ----------

def jogo(num, rodada, id_jogo=None):
    return {"numero": str(num), "id_jogo": str(id_jogo or 1000 + num), "rodada": str(rodada)}


def test_a28_detecta_rodada_incompleta_e_jogo_repetido():
    jogos = [jogo(n, 1) for n in range(1, 9)] + [jogo(9, 2)]
    _, oc, _ = executar("A28", contexto(jogos=jogos))
    detalhes = " ".join(o["detalhe"] for o in oc)
    assert "rodada 2" in detalhes and "rodada 3" in detalhes  # rodada 2 incompleta, 3 ausente
    jogos = [jogo(n, 1) for n in range(1, 9)]
    jogos[1] = jogo(1, 1)  # número repetido
    _, oc, _ = executar("A28", contexto(jogos=jogos))
    assert any(o["detalhe"] == "repetido" and o["fonte_a"] == "numero" for o in oc)


def evento(**kw):
    return {"id_evento": "1-01", "id_partida": "1", "id_clube": "10", "id_clube_creditado": "10", "tipo_evento": "gol", "pessoa": "Fulano", "minuto": "30", "acrescimo": "0", "periodo": "1T", **kw}


def test_a29_detecta_minuto_fora_da_faixa_do_periodo():
    partida = [{"id_partida": "1", "numero_jogo": "1"}]
    ok = [evento(), evento(periodo="2T", minuto="90", acrescimo="6"), evento(periodo="PEN", minuto="")]
    ruim = [evento(periodo="2T", minuto="30"), evento(periodo="1T", minuto="50"), evento(minuto="44", acrescimo="25")]
    assert executar("A29", contexto(t={"fato_evento": ok, "fato_partida": partida}, num_partida={"1": 1}))[1] == []
    _, oc, _ = executar("A29", contexto(t={"fato_evento": ruim, "fato_partida": partida}, num_partida={"1": 1}))
    assert len(oc) == 3


def test_a30_detecta_evento_de_clube_que_nao_jogou():
    partidas = [{"id_partida": "1", "numero_jogo": "1", "id_clube_mandante": "10", "id_clube_visitante": "20"}]
    eventos = [evento(), evento(id_clube="99", id_clube_creditado="99"), evento(id_clube="10", id_clube_creditado="77")]
    _, oc, _ = executar("A30", contexto(t={"fato_evento": eventos, "fato_partida": partidas}))
    assert len(oc) == 2


def test_a32_detecta_coluna_vazia():
    t = {"fato_partida": [{c: "x" for c in ("id_arbitro", "id_assistente1", "id_assistente2", "id_quarto_arbitro", "id_var", "inicio_1t", "termino_1t", "inicio_2t", "termino_2t", "publico_boletim", "publico_pagante", "renda_bruta", "publico_espn", "id_estadio")}],
         "dim_estadio": [{"capacidade": ""}], "dim_clube": [{"sigla": "S", "cor_hex": "FFFFFF", "arquivo_escudo": "a.png"}], "fato_evento": [{"pessoa": "P"}]}
    _, oc, _ = executar("A32", contexto(t=t))
    assert [o["fonte_a"] for o in oc] == ["dim_estadio.capacidade"]


def sumula(**kw):
    return {"inicio_1t": "15:00", "termino_1t": "15:49", "inicio_2t": "16:04", "termino_2t": "16:57", "acrescimo_1t_min": "4", "acrescimo_2t_min": "8", **kw}


def test_a33_detecta_horarios_zerados_como_no_jogo_47():
    sp = {1: sumula(), 2: sumula(inicio_1t="00:00", termino_1t="00:03", inicio_2t="00:00", termino_2t="00:07"), 3: sumula(inicio_1t="23:30", termino_1t="00:19", inicio_2t="00:34", termino_2t="01:27")}
    _, oc, _ = executar("A33", contexto(sp=sp, id_partida={}))
    assert [o["numero_jogo"] for o in oc] == [2]  # a virada da meia-noite (jogo 3) é normal


def test_a31_detecta_publicacao_fora_de_um_dia():
    jogos = {1: {"data": "10/01/2026", "horario": "15h00"}, 2: {"data": "10/01/2026", "horario": "15h00"}}
    bo = {n: {"data": "10/01/2026", "horario": "15:00"} for n in jogos}
    sp = {1: {"publicada_em": "10/01/2026 18:08"}, 2: {"publicada_em": "14/01/2026 10:00"}}
    _, oc, _ = executar("A31", contexto(jogo=jogos, bo=bo, sp=sp))
    assert [o["numero_jogo"] for o in oc] == [2]


def jogo_espn(status, cobrancas=(), gols=()):
    detalhes = [{"shootout": True, "scoringPlay": convertida, "team": {"id": time}} for time, convertida in cobrancas] + [{"shootout": False, "scoringPlay": True, "team": {"id": time}} for time in gols]
    return {"status": {"type": {"name": status}}, "competitions": [{"competitors": [{"homeAway": "home", "team": {"id": "1"}}, {"homeAway": "away", "team": {"id": "2"}}], "details": detalhes}]}


def contexto_a15(espn, sumula):
    por_numero = {n: str(n) for n in espn}
    return contexto(eventos={str(n): e for n, e in espn.items()}, por_numero=por_numero, sp={n: ({"penaltis_mandante": str(a), "penaltis_visitante": str(b)} if (a, b) != (None, None) else {"penaltis_mandante": "", "penaltis_visitante": ""}) for n, (a, b) in sumula.items()},
                    class_fpf=[{"fase": "QUARTAS DE FINAL", "vp": "1", "dp": "0"}, {"fase": "QUARTAS DE FINAL", "vp": "0", "dp": "1"}], id_partida={5: 105})


def test_placar_da_disputa_na_espn_conta_so_cobrancas_convertidas_e_so_de_jogo_com_disputa():
    assert placar_disputa_espn(jogo_espn("STATUS_FINAL_PEN", [("1", True), ("2", True), ("1", True), ("2", False), ("1", False)], gols=["1"])) == (2, 1)
    assert placar_disputa_espn(jogo_espn("STATUS_FULL_TIME", gols=["1", "2"])) is None
    assert placar_disputa_espn(jogo_espn("STATUS_FINAL_PEN", [("1", False), ("2", False)])) is None


def test_a15_aceita_o_placar_da_disputa_igual_na_espn_e_na_sumula_e_conta_o_jogo_da_disputa():
    espn = {5: jogo_espn("STATUS_FINAL_PEN", [("1", True), ("2", True), ("2", True)]), 6: jogo_espn("STATUS_FULL_TIME", gols=["1"])}
    verificados, oc, _ = executar("A15", contexto_a15(espn, {5: (1, 2), 6: (None, None)}))
    assert oc == [] and verificados == 2


def test_a15_aponta_placar_da_disputa_diferente_e_disputa_so_de_um_lado():
    espn = {5: jogo_espn("STATUS_FINAL_PEN", [("1", True), ("2", True), ("2", True)]), 6: jogo_espn("STATUS_FULL_TIME", gols=["1"])}
    _, oc, _ = executar("A15", contexto_a15(espn, {5: (7, 8), 6: (None, None)}))
    assert [(o["numero_jogo"], o["valor_a"], o["valor_b"]) for o in oc] == [(5, (1, 2), (7, 8))]
    _, oc, _ = executar("A15", contexto_a15(espn, {5: (None, None), 6: (None, None)}))
    assert [(o["numero_jogo"], o["valor_a"], o["valor_b"]) for o in oc] == [(5, (1, 2), None)]
    _, oc, _ = executar("A15", contexto_a15({5: jogo_espn("STATUS_FULL_TIME", gols=["1"])}, {5: (3, 4)}))
    assert [(o["numero_jogo"], o["valor_a"], o["valor_b"]) for o in oc if o["detalhe"] == "placar da disputa de pênaltis"] == [(5, None, (3, 4))]


# ---------- indicadores: fórmulas com dados inventados ----------

def partida(idp, mand, vis, gm, gv, publico, pagantes, bruta, liquida, ac1=3, ac2=7):
    return {"id_partida": idp, "id_clube_mandante": mand, "id_clube_visitante": vis, "gols_mandante": str(gm), "gols_visitante": str(gv), "publico_boletim": str(publico), "publico_pagante": str(pagantes), "renda_bruta": bruta, "renda_liquida": liquida, "acrescimo_1t_min": str(ac1), "acrescimo_2t_min": str(ac2)}


def test_metricas_com_dados_inventados():
    partidas = [partida("1", "10", "20", 2, 0, 1000, 900, "9000.00", "4000.00"), partida("2", "20", "10", 1, 1, 500, 500, "1000.00", "-200.50", ac1=5, ac2=5)]
    eventos = [{"id_partida": "1", "id_clube": "10", "tipo_evento": t} for t in ("amarelo", "amarelo", "segundo_amarelo", "vermelho")]
    eventos += [{"id_partida": "2", "id_clube": "20", "tipo_evento": "gol_penalti"}]
    m = {k[1]: v[0] for k, v in indicadores.metricas(partidas, eventos).items()}
    assert (m["jogos"], m["gols"], m["gols_por_jogo"]) == (2, 4, 2.0)
    assert (m["vitorias_mandante"], m["empates"], m["vitorias_visitante"]) == (1, 1, 0)
    assert (m["pct_vitorias_mandante"], m["pct_empates"]) == (50.0, 50.0)
    assert (m["publico_total"], m["publico_medio"], m["publico_maximo"], m["publico_minimo"]) == (1500, 750.0, 1000, 500)
    assert m["pct_pagantes"] == 93.3333
    assert m["renda_bruta"] == Decimal("10000.00") and m["renda_liquida"] == Decimal("3799.50")
    assert m["ticket_medio"] == Decimal("7.14")  # 10000 / 1400 pagantes
    assert m["jogos_renda_liquida_negativa"] == 1
    # regra da FPF: amarelos = advertências - 2º amarelos (2 - 1); vermelhos = direto + 2º amarelo (1 + 1)
    assert (m["amarelos"], m["vermelhos"], m["cartoes_por_jogo"]) == (1, 2, 1.5)
    assert m["acrescimo_medio_min"] == 10.0 and m["gols_de_penalti"] == 1 and m["jogos_sem_gols"] == 0


def test_faixas_de_minuto_incluem_acrescimo_na_ultima_faixa_do_tempo():
    eventos = [evento(minuto=m) for m in ("0", "15", "16", "45", "46", "75", "76", "90")] + [evento(tipo_evento="amarelo", minuto="10")]
    f = indicadores.faixas_minuto(eventos)
    assert [f[n] for n in ("01-15", "16-30", "31-45", "46-60", "61-75", "76-90+")] == [2, 1, 1, 1, 1, 2]


# ---------- com os dados reais ----------

@precisa_dados
def test_nenhuma_divergencia_aberta_sem_decisao_do_autor():
    log, resultados, sem_uso = validar05.validar()
    novas = [x["id_inconsistencia"] for x in log if x["status"] == "aberta" and not x["explicacao"]]
    assert novas == [], f"divergências novas, sem decisão em inconsistencias_decisoes.csv: {novas}"
    assert not sem_uso, f"decisões sem ocorrência (dado corrigido?): {sem_uso}"
    assert len(resultados) == len(regras.REGRAS)


@precisa_dados
def test_resultado_de_cada_regra_confere_com_o_que_foi_decidido():
    log, resultados, _ = validar05.validar()
    por_resultado = {r["codigo"]: r["resultado"] for r in resultados}
    assert {c for c, r in por_resultado.items() if r == "aberta"} == {"A32", "A33"}
    assert {c for c, r in por_resultado.items() if r == "explicada"} == {"A06", "A12", "A13", "A24", "A26", "A27", "A40"}
    status = {x["id_inconsistencia"]: x["status"] for x in log if x["codigo_regra"] in ("A24", "A27")}
    assert sorted(status.values()) == ["aceita", "corrigida", "explicada"]
    assert por_resultado["A14"] == "info"
    assert all(x["status"] in validar05.STATUS and x["severidade"] in validar05.SEVERIDADES for x in log)


@precisa_dados
def test_indicadores_batem_com_fatos_verificados_e_fecham_entre_si():
    linhas = indicadores.calcular(PROC)
    geral = {l["indicador"]: l["valor"] for l in linhas if l["escopo"] == "geral"}
    assert (geral["jogos"], geral["gols"], geral["publico_total"], geral["publico_pagante"]) == (72, 168, 784369, 761489)
    assert (geral["amarelos"], geral["vermelhos"]) == (385, 28)
    assert (geral["vitorias_mandante"], geral["empates"], geral["vitorias_visitante"]) == (34, 17, 21)
    assert geral["renda_bruta"] == Decimal("44730003.80") and geral["renda_liquida"] == Decimal("24325256.66")
    assert geral["ticket_medio"] == Decimal("58.74") and geral["jogos_renda_liquida_negativa"] == 15
    por_fase = [l for l in linhas if l["escopo"] == "fase" and l["indicador"] == "gols"]
    assert sum(l["valor"] for l in por_fase) == geral["gols"]
    assert sum(l["valor"] for l in linhas if l["escopo"] == "faixa_minuto") == geral["gols"]
    assert sum(l["valor"] for l in linhas if l["escopo"] == "clube" and l["indicador"] == "gols_pro") == geral["gols"]
    assert sum(l["valor"] for l in linhas if l["escopo"] == "artilheiro") == geral["gols"] - 2  # sem os 2 gols contra
    top = next(l for l in linhas if l["escopo"] == "artilheiro")
    assert top["chave"].startswith("Robson") and top["valor"] == 7  # confere com a Wikipédia (artilheiro 2026)
    faixas = {l["chave"]: l["valor"] for l in linhas if l["escopo"] == "faixa_minuto"}
    assert faixas == {"01-15": 22, "16-30": 22, "31-45": 24, "46-60": 27, "61-75": 26, "76-90+": 47}  # com a correção C01 (60' -> 76')
    primeira = {l["chave"]: l["valor"] for l in linhas if l["indicador"] == "posicao_primeira_fase"}
    assert sorted(primeira.values()) == list(range(1, 17))
