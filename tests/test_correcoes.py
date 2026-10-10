import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import correcoes  # noqa: E402
import regras  # noqa: E402
from comum import ler_csv  # noqa: E402

PROC = RAIZ / "data" / "processed"
precisa_proc = pytest.mark.skipif(not (PROC / "fato_evento.csv").exists(), reason="rode scripts/04_tratar.py antes")


def correcao(**kw):
    return {"id_correcao": "C99", "numero_jogo": "5", "tipo_evento": "gol", "pessoa": "Fulano de Tal", "campo": "minuto", "valor_original": "60", "valor_corrigido": "76", "fontes": "jornal x", "justificativa": "teste", **kw}


def evento(**kw):
    return {"tipo_evento": "gol", "pessoa": "Fulano de Tal", "minuto": 60, "acrescimo": 0, **kw}


def test_correcao_altera_so_o_evento_certo_e_marca_a_origem():
    alvo, outro_gol, outro_jogo = evento(), evento(minuto=30), evento()
    brutos = [(5, alvo), (5, outro_gol), (6, outro_jogo)]
    correcoes.aplicar_correcoes(brutos, [correcao()])
    assert (alvo["minuto"], alvo["id_correcao"]) == (76, "C99")
    assert (outro_gol["minuto"], outro_gol["id_correcao"]) == (30, None)
    assert (outro_jogo["minuto"], outro_jogo["id_correcao"]) == (60, None)


def test_correcao_recusa_valor_original_diferente():
    with pytest.raises(ValueError, match="esperava 1 evento"):
        correcoes.aplicar_correcoes([(5, evento(minuto=61))], [correcao()])


def test_correcao_recusa_evento_ambiguo():
    with pytest.raises(ValueError, match="achei 2"):
        correcoes.aplicar_correcoes([(5, evento()), (5, evento())], [correcao()])


def test_leitura_recusa_correcao_sem_fonte_campo_nao_suportado_e_id_repetido(tmp_path):
    cab = ";".join(correcoes.COLUNAS) + "\n"
    linha = lambda **kw: ";".join(correcao(**kw)[c] for c in correcoes.COLUNAS) + "\n"
    arq = tmp_path / "c.csv"
    arq.write_text(cab + linha(fontes=" "), encoding="utf-8")
    with pytest.raises(ValueError, match="sem fonte"):
        correcoes.ler_correcoes(arq)
    arq.write_text(cab + linha(campo="pessoa"), encoding="utf-8")
    with pytest.raises(ValueError, match="não suportado"):
        correcoes.ler_correcoes(arq)
    arq.write_text(cab + linha() + linha(), encoding="utf-8")
    with pytest.raises(ValueError, match="repetido"):
        correcoes.ler_correcoes(arq)
    arq.write_text(cab + linha(), encoding="utf-8")
    assert len(correcoes.ler_correcoes(arq)) == 1


def contexto_a34(aplicado=True, original_na_sumula=True):
    c = regras.Contexto.__new__(regras.Contexto)
    c.id_partida = {5: 1005}
    c.num_partida = {"1005": 5}
    c.t = {"fato_evento": [{"id_partida": "1005", "id_correcao": "C99" if aplicado else "", "minuto": "76"}]}
    c.sg = [{"numero_jogo": "5", "jogador": "Fulano de Tal - (Fulano)", "minuto": "60" if original_na_sumula else "61"}]
    c.sc = []
    return c


def executar_a34(monkeypatch, c):
    monkeypatch.setattr(regras, "ler_correcoes", lambda: [correcao()])
    return next(r for r in regras.REGRAS if r["codigo"] == "A34")["funcao"](c)


def test_a34_passa_quando_a_correcao_esta_aplicada_e_rastreavel(monkeypatch):
    assert executar_a34(monkeypatch, contexto_a34())[1] == []


def test_a34_dispara_se_a_correcao_nao_foi_aplicada(monkeypatch):
    _, oc, _ = executar_a34(monkeypatch, contexto_a34(aplicado=False))
    assert len(oc) == 1 and "não está aplicada" in oc[0]["detalhe"]


def test_a34_dispara_se_a_sumula_mudou(monkeypatch):
    _, oc, _ = executar_a34(monkeypatch, contexto_a34(original_na_sumula=False))
    assert len(oc) == 1 and "não traz mais" in oc[0]["detalhe"]


@precisa_proc
def test_correcoes_reais_estao_aplicadas_e_a_sumula_bruta_ficou_intacta():
    cs = correcoes.ler_correcoes()
    assert cs, "esperava ao menos a correção C01"
    eventos = ler_csv(PROC / "fato_evento.csv")
    for k in cs:
        aplicados = [e for e in eventos if e["id_correcao"] == k["id_correcao"]]
        assert len(aplicados) == 1 and aplicados[0][k["campo"]] == k["valor_corrigido"]
        assert aplicados[0]["minuto_total"] == str(int(k["valor_corrigido"]) + int(aplicados[0]["acrescimo"]))
    bruto = [g for g in ler_csv(PROC / "fpf" / "sumula_gol.csv") if g["numero_jogo"] == "15" and "Mosquera" in g["jogador"]]
    assert [g["minuto"] for g in bruto] == ["60"]  # o dado bruto da súmula não é alterado
    ids = [e["id_evento"] for e in eventos if e["id_partida"] == aplicados[0]["id_partida"]]
    assert ids == sorted(ids)
    minutos = [int(e["minuto_total"]) for e in eventos if e["id_partida"] == aplicados[0]["id_partida"] and e["periodo"] in ("1T", "2T") and e["minuto_total"]]
    assert minutos == sorted(minutos)  # a numeração continua em ordem cronológica depois da correção
