import copy
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import financeiro  # noqa: E402
import regras  # noqa: E402
from comum import ler_csv  # noqa: E402
from fpf_pdf import ler_boletim_detalhe, texto_pdf  # noqa: E402

PDFS = RAIZ / "data" / "raw" / "fpf_pdf" / "2026"
PROC = RAIZ / "data" / "processed"
precisa_pdf = pytest.mark.skipif(not (PDFS / "boletim" / "1.pdf").exists(), reason="PDFs brutos ausentes (rode scripts/03_coletar_fpf_pdf.py)")
precisa_proc = pytest.mark.skipif(not (PROC / "fato_ingresso.csv").exists(), reason="rode scripts/03b_ler_fpf_pdf.py e 04_tratar.py antes")


def ing(loc, venda, dev, vend, preco, arr):
    return f"     {loc:<64}{venda:>8}{dev:>8}{vend:>8}      R$ {preco:>9}   R$ {arr:>12}"


def desp(rotulo, valor):
    return f"     {rotulo:<90}   R$ {valor:>30}"


def rateio(clube, pct, valor, inss, outras, liquido):
    return f" {clube} - ({pct}%)    R$ {valor:>14}   R$ {inss:>20}  R$ {outras:>20}   R$ {liquido:>24}"


def boletim(ingressos=None, totais="TOTAIS                               32      0      32                        R$           800,00", b1=None, b2=None, b3=None, retencoes=None, divisao=None, total_despesas="140,32", liquida="659,68"):
    ingressos = ingressos if ingressos is not None else [
        ing("SETOR LESTE - Inteira", 10, 0, 10, "40,00", "400,00"),
        ing("SETOR LESTE - Meia", 20, 0, 20, "20,00", "400,00"),
        ing("SETOR LESTE - Lei nº18.159- Gratuidade menor de 2 anos", 2, 0, 2, "0,00", "0,00"),
        "                                                                      R$        0,00   R$               0,00",
    ]
    b1 = b1 if b1 is not None else [desp("Seguro Público Pagante - FPF", "0,32"), "     R$   0,000"]
    b2 = b2 if b2 is not None else [desp("5% - FPF", "40,00"), "     R$   0,000"]
    b3 = b3 if b3 is not None else [desp("Ambulância", "100,00"), "     R$   0,000"]
    retencoes = retencoes if retencoes is not None else [desp("11% INSS Prestadores de Serviços", "5,00"), "     R$   0,00"]
    divisao = divisao if divisao is not None else [rateio("Time A", 100, "659,68", "0,00", "10,00", "649,68"), rateio("Time B", 0, "-", "-", "-", "-")]
    linhas = ["BOLETIM FINANCEIRO 1/2026", "Data: 10/01/2026 15:00     Jogo: Time A x Time B     ESTÁDIO", "", "   LOCALIDADES      A VENDA   DEVOLVIDOS   VENDIDOS   PREÇO   ARRECADAÇÃO", *ingressos, totais,
              "     B1 - ALUGUÉIS E SEGUROS", *b1, "                         TOTAL B1      R$        0,32",
              "     B2 - TAXAS E IMPOSTOS", *b2, "                         TOTAL B2      R$       40,00",
              "     B3 - DESPESAS OPERACIONAIS", *b3, "                         TOTAL B3      R$      100,00",
              f"                  TOTAL DAS DESPESAS (B1+B2+B3)       R$       {total_despesas}", *retencoes,
              f"                  RENDA LÍQUIDA (RECEITA - DESPESA)   R$       {liquida}",
              "                  DIVISÃO DA RENDA LÍQUIDA", "   CLUBES      VALOR      INSS 5%      LÍQUIDO A RECEBER", "                 PARC. ESPECIAL   OUTRAS", *divisao,
              "   Assinado digitalmente - 10/01/2026 16:53h"]
    return "\n".join(linhas)


# ---------- leitor do detalhe do boletim ----------

def test_leitor_le_ingressos_despesas_retencoes_e_divisao():
    d = ler_boletim_detalhe(boletim())
    assert [(x["localidade"], x["vendidos"], x["preco"], x["arrecadacao"]) for x in d["ingressos"]] == [
        ("SETOR LESTE - Inteira", 10, Decimal("40.00"), Decimal("400.00")),
        ("SETOR LESTE - Meia", 20, Decimal("20.00"), Decimal("400.00")),
        ("SETOR LESTE - Lei nº18.159- Gratuidade menor de 2 anos", 2, Decimal("0.00"), Decimal("0.00"))]
    assert [x["ordem"] for x in d["ingressos"]] == [1, 2, 3]
    assert d["totais"] == {"a_venda": 32, "devolvidos": 0, "vendidos": 32, "arrecadacao": Decimal("800.00")}
    assert [(x["bloco"], x["ordem"], x["rubrica"], x["valor"]) for x in d["despesas"]] == [("B1", 1, "Seguro Público Pagante - FPF", Decimal("0.32")), ("B2", 1, "5% - FPF", Decimal("40.00")), ("B3", 1, "Ambulância", Decimal("100.00"))]
    assert d["subtotais"] == {"B1": Decimal("0.32"), "B2": Decimal("40.00"), "B3": Decimal("100.00")}
    assert d["total_despesas"] == Decimal("140.32") and d["renda_liquida"] == Decimal("659.68")
    assert d["retencoes"] == [{"rubrica": "11% INSS Prestadores de Serviços", "valor": Decimal("5.00")}]


def test_leitor_trata_traco_como_zero_e_le_a_divisao_na_ordem():
    d = ler_boletim_detalhe(boletim())
    assert [(x["clube"], x["percentual"], x["valor"], x["deducao_inss"], x["deducao_outras"], x["liquido"]) for x in d["rateio"]] == [
        ("Time A", Decimal("100"), Decimal("659.68"), Decimal("0.00"), Decimal("10.00"), Decimal("649.68")),
        ("Time B", Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))]


def test_leitor_aceita_milhar_e_valor_negativo():
    d = ler_boletim_detalhe(boletim(ingressos=[ing("ARQUIBANCADA NORTE OREO - Inteira", 1234, 0, 1234, "40,00", "49.360,00")], totais="TOTAIS    1234    0    1234     R$   49.360,00", liquida="-13.503,80"))
    assert d["ingressos"][0]["arrecadacao"] == Decimal("49360.00") and d["totais"]["arrecadacao"] == Decimal("49360.00")
    assert d["renda_liquida"] == Decimal("-13503.80")


def test_leitor_recusa_linha_de_ingresso_desconhecida():
    with pytest.raises(ValueError, match="linha de ingresso não reconhecida"):
        ler_boletim_detalhe(boletim(ingressos=[ing("SETOR LESTE - Inteira", 10, 0, 10, "40,00", "400,00"), "SETOR LESTE - Meia   vinte ingressos"]))


def test_leitor_recusa_linha_de_despesa_desconhecida():
    with pytest.raises(ValueError, match="linha de despesa não reconhecida"):
        ler_boletim_detalhe(boletim(b3=[desp("Ambulância", "100,00"), "Gerador sem valor informado"]))


def test_leitor_recusa_boletim_incompleto():
    with pytest.raises(ValueError, match="boletim incompleto"):
        ler_boletim_detalhe(boletim(divisao=[]))
    with pytest.raises(ValueError, match="boletim incompleto"):
        ler_boletim_detalhe("BOLETIM FINANCEIRO 1/2026\nsem tabela")


@precisa_pdf
def test_boletim_1_tem_as_linhas_conhecidas():
    d = ler_boletim_detalhe(texto_pdf(PDFS / "boletim" / "1.pdf", layout=True))
    assert len(d["ingressos"]) == 9 and sum(x["vendidos"] for x in d["ingressos"]) == 1175
    assert sum(x["arrecadacao"] for x in d["ingressos"]) == Decimal("28580.00")
    assert [(k, sum(1 for x in d["despesas"] if x["bloco"] == k)) for k in ("B1", "B2", "B3")] == [("B1", 1), ("B2", 2), ("B3", 15)]
    assert d["total_despesas"] == Decimal("42083.80") and d["renda_liquida"] == Decimal("-13503.80")
    assert [x["rubrica"] for x in d["retencoes"]] == ["11% INSS Prestadores de Serviços", "11% INSS Quadro Móvel - Clube", "11% INSS Quadro Móvel - Federação Local"]
    assert [(x["clube"], x["percentual"], x["liquido"]) for x in d["rateio"]] == [("São Bernardo FC", Decimal("100"), Decimal("-13503.80")), ("Capivariano", Decimal("0"), Decimal("0.00"))]


@precisa_pdf
def test_os_72_boletins_fecham_publico_renda_bruta_e_despesas():
    bol = {int(r["numero_jogo"]): r for r in ler_csv(PROC / "fpf" / "boletim_partida.csv")}
    linhas = 0
    for n in range(1, 73):
        d = ler_boletim_detalhe(texto_pdf(PDFS / "boletim" / f"{n}.pdf", layout=True))
        linhas += len(d["ingressos"])
        assert sum(x["vendidos"] for x in d["ingressos"]) == d["totais"]["vendidos"] == int(bol[n]["publico"]), n
        assert sum(x["arrecadacao"] for x in d["ingressos"]) == d["totais"]["arrecadacao"] == Decimal(bol[n]["renda_bruta"]), n
        assert all(x["preco"] * x["vendidos"] == x["arrecadacao"] and x["devolvidos"] == 0 and x["a_venda"] == x["vendidos"] for x in d["ingressos"]), n
        assert {k: sum(x["valor"] for x in d["despesas"] if x["bloco"] == k) for k in ("B1", "B2", "B3")} == d["subtotais"], n
        assert sum(d["subtotais"].values()) == d["total_despesas"] == Decimal(bol[n]["despesas_total"]), n
        assert d["totais"]["arrecadacao"] - d["total_despesas"] == d["renda_liquida"] == Decimal(bol[n]["renda_liquida"]), n
        assert sum(x["percentual"] for x in d["rateio"]) == 100 and sum(x["valor"] for x in d["rateio"]) == d["renda_liquida"], n
    assert linhas == 2388


# ---------- categorias de ingresso e grupos de despesa ----------

@pytest.mark.parametrize("rotulo,preco,esperado", [
    ("SETOR LESTE - Inteira", "40.00", "Inteira"),
    ("SETOR LESTE - Meia", "20.00", "Meia-entrada"),
    ("CAMAROTE - Meia", "30.00", "Meia-entrada"),
    ("ARQUIBANCADA - Lei nº18.159- Meia entrada, menores de 12 anos", "20.00", "Meia-entrada"),
    ("SETOR LESTE - Lei nº18.159- Gratuidade menor de 2 anos", "0.00", "Gratuidade por lei"),
    ("SETOR LESTE - Inteira", "0.00", "Gratuidade por lei"),
    ("NORTE - Fiel Torcedor", "35.00", "Sócio-torcedor"),
    ("B- GOL - - - Avanti - 100% Desconto", "20.00", "Sócio-torcedor"),
    ("ARQUIBANCADA LESTE LACTA - ST - DIAMANTE", "30.00", "Sócio-torcedor"),
    ("ARQUIBANCADA COBERTA - Carnê - Inteira", "30.00", "Sócio-torcedor"),
    ("CAMAROTES - Carnê de Relacionamento", "30.00", "Sócio-torcedor"),
    ("SETOR OESTE (VITALÍCIAS) - Sócio", "30.00", "Sócio-torcedor"),
    ("CAMAROTES - VENDA PROIBIDA", "20.00", "Cadeira e camarote"),
    ("CADEIRA VITALÍCIA - TC10 VITALÍCIA - ADICIONAL", "20.00", "Cadeira e camarote"),
    ("SETOR 1 (OESTE) - Passaporte", "25.00", "Outros"),
    ("CADEIRA TÉRREA OESTE OURO BRANCO - PCD - P.C.D. - Acompanhante", "25.00", "Outros"),
])
def test_categoria_do_ingresso_segue_as_regras_do_arquivo_de_referencia(rotulo, preco, esperado):
    regra = financeiro.classificar_ingresso(rotulo, Decimal(preco), financeiro.ler_regras_ingresso())
    assert regra["categoria"] == esperado


def test_ordem_de_exibicao_das_categorias_e_unica_e_vai_de_um_a_seis():
    regras_ing = financeiro.ler_regras_ingresso()
    assert sorted(r["ordem_exibicao"] for r in regras_ing) == [1, 2, 3, 4, 5, 6]
    assert regras_ing[0]["condicao"] == "preco_zero" and regras_ing[-1]["condicao"] == "resto"


@pytest.mark.parametrize("rotulo,esperado", [("SETOR SUL - VISITANTE - Visitante - Inteira", 1), ("ARQUIBANCADA VISITANTE - Meia", 1), ("CABECEIRA VISITANTES - Meia", 1), ("SETOR LESTE - Inteira", 0), ("TORCIDA ORGANIZADA - Meia", 0)])
def test_setor_visitante_pelo_rotulo(rotulo, esperado):
    assert financeiro.setor_visitante(rotulo) == esperado


def gravar_regras(tmp_path, linhas, cab="ordem_regra;categoria;ordem_exibicao;condicao;expressao;explicacao"):
    arq = tmp_path / "regras.csv"
    arq.write_text("\n".join([cab, *linhas]) + "\n", encoding="utf-8")
    return arq


def test_arquivo_de_regras_recusa_condicao_desconhecida_ordem_repetida_e_fim_sem_resto(tmp_path):
    with pytest.raises(ValueError, match="condição 'sempre'"):
        financeiro.ler_regras_ingresso(gravar_regras(tmp_path, ["1;A;1;sempre;;x", "2;B;2;resto;;x"]))
    with pytest.raises(ValueError, match="repetido"):
        financeiro.ler_regras_ingresso(gravar_regras(tmp_path, ["1;A;1;texto;meia;x", "1;B;2;resto;;x"]))
    with pytest.raises(ValueError, match="última regra"):
        financeiro.ler_regras_ingresso(gravar_regras(tmp_path, ["1;A;1;texto;meia;x", "2;B;2;texto;inteira;x"]))
    with pytest.raises(ValueError, match="sem expressão"):
        financeiro.ler_regras_ingresso(gravar_regras(tmp_path, ["1;A;1;texto;;x", "2;B;2;resto;;x"]))
    with pytest.raises(ValueError, match="não usa expressão"):
        financeiro.ler_regras_ingresso(gravar_regras(tmp_path, ["1;A;1;texto;meia;x", "2;B;2;resto;meia;x"]))


def test_arquivo_de_grupos_recusa_bloco_desconhecido_e_rubrica_repetida(tmp_path):
    arq = tmp_path / "grupos.csv"
    arq.write_text("rubrica;bloco;grupo\nAmbulância;B9;Saúde\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bloco 'B9'"):
        financeiro.ler_grupos_despesa(arq)
    arq.write_text("rubrica;bloco;grupo\nAmbulância;B3;Saúde\nAmbulância;B3;Outro\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rubrica repetida"):
        financeiro.ler_grupos_despesa(arq)
    arq.write_text("rubrica;bloco;grupo\nAmbulância;B3;\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vazio"):
        financeiro.ler_grupos_despesa(arq)


def test_arquivos_de_referencia_do_repositorio_sao_validos():
    assert len(financeiro.ler_regras_ingresso()) == 6
    grupos = financeiro.ler_grupos_despesa()
    assert len(grupos) == 43 and len(set(grupos.values())) == 10


# ---------- montagem das três tabelas ----------

JOGOS = {1: {"id_partida": 100, "id_mandante": 1, "id_visitante": 2, "jogo": "Time A x Time B"}}
GRUPOS = {"Seguro Público Pagante - FPF": "Taxas da FPF e seguro", "5% - FPF": "Taxas da FPF e seguro", "Ambulância": "Saúde e antidoping"}


def brutos(d):
    ing_raw = [{"numero_jogo": "1", **{k: str(v) for k, v in x.items()}} for x in d["ingressos"]]
    desp_raw = [{"numero_jogo": "1", **{k: str(v) for k, v in x.items()}} for x in d["despesas"]]
    rat_raw = [{"numero_jogo": "1", **{k: str(v) for k, v in x.items()}} for x in d["rateio"]]
    return ing_raw, desp_raw, rat_raw


def montar(d=None, grupos=None):
    d = d or ler_boletim_detalhe(boletim())
    return financeiro.montar_financeiro(*brutos(d), JOGOS, financeiro.ler_regras_ingresso(), GRUPOS if grupos is None else grupos)


def test_montagem_dos_ingressos_ids_categorias_e_valores_com_duas_casas():
    ingressos, _, _ = montar()
    assert [(i["id_ingresso"], i["categoria"], i["ordem_categoria"], i["setor_visitante"], i["ingressos"], i["preco"], i["arrecadacao"]) for i in ingressos] == [
        ("100-01", "Inteira", 1, 0, 10, "40.00", "400.00"), ("100-02", "Meia-entrada", 2, 0, 20, "20.00", "400.00"), ("100-03", "Gratuidade por lei", 5, 0, 2, "0.00", "0.00")]
    assert list(ingressos[0]) == financeiro.COLUNAS_INGRESSO


def test_montagem_das_despesas_com_bloco_grupo_e_sem_grupo_para_rubrica_nova():
    _, despesas, _ = montar(grupos={"5% - FPF": "Taxas da FPF e seguro"})
    assert [(x["id_despesa"], x["bloco_codigo"], x["bloco"], x["rubrica"], x["grupo"], x["valor"]) for x in despesas] == [
        ("100-B1-01", "B1", "Aluguéis e seguros", "Seguro Público Pagante - FPF", "Sem grupo", "0.32"),
        ("100-B2-01", "B2", "Taxas e impostos", "5% - FPF", "Taxas da FPF e seguro", "40.00"),
        ("100-B3-01", "B3", "Despesas operacionais", "Ambulância", "Sem grupo", "100.00")]
    assert list(despesas[0]) == financeiro.COLUNAS_DESPESA


def test_montagem_ignora_despesa_de_valor_zero():
    d = ler_boletim_detalhe(boletim(b3=[desp("Ambulância", "100,00"), desp("Geradores", "0,00")]))
    _, despesas, _ = montar(d)
    assert [x["rubrica"] for x in despesas] == ["Seguro Público Pagante - FPF", "5% - FPF", "Ambulância"]


def test_montagem_da_divisao_liga_cada_linha_ao_mandante_e_ao_visitante():
    _, _, rateio_ = montar()
    assert [(r["id_rateio"], r["id_clube"], r["lado"], r["percentual"], r["valor"], r["deducao_outras"], r["liquido"]) for r in rateio_] == [
        ("100-1", 1, "mandante", "100.00", "659.68", "10.00", "649.68"), ("100-2", 2, "visitante", "0.00", "0.00", "0.00", "0.00")]
    assert list(rateio_[0]) == financeiro.COLUNAS_RATEIO


def test_montagem_recusa_clube_da_divisao_que_nao_e_do_jogo():
    d = ler_boletim_detalhe(boletim(divisao=[rateio("Time Z", 100, "659,68", "0,00", "0,00", "659,68"), rateio("Time B", 0, "-", "-", "-", "-")]))
    with pytest.raises(ValueError, match="Time Z"):
        montar(d)


# ---------- regras A42 a A45 ----------

def mundo(mudar=None):
    d = ler_boletim_detalhe(boletim())
    ing_raw, desp_raw, rat_raw = brutos(d)
    bo = {"jogo": "Time A x Time B", "publico": "32", "renda_bruta": "800.00", "ingressos_a_venda": "32", "ingressos_devolvidos": "0", "publico_pagante": "30", "despesas_total": "140.32", "renda_liquida": "659.68", "total_b1": "0.32", "total_b2": "40.00", "total_b3": "100.00", "retencao_inss_informada": "5.00"}
    m = {"bo": bo, "bi": ing_raw, "bd": desp_raw, "br": rat_raw, "grupos": dict(GRUPOS)}
    if mudar:
        mudar(m)
    ingressos, despesas, rateio_ = financeiro.montar_financeiro(m["bi"], m["bd"], m["br"], JOGOS, financeiro.ler_regras_ingresso(), m["grupos"])
    c = regras.Contexto.__new__(regras.Contexto)
    c.id_partida, c.num_partida = {1: 100}, {100: 1}
    c.bo, c.bi, c.bd, c.br = {1: m["bo"]}, m["bi"], m["bd"], m["br"]
    como_csv = lambda ls: [{k: str(v) for k, v in l.items()} for l in ls]
    c.t = {"fato_ingresso": como_csv(ingressos), "fato_despesa": como_csv(despesas), "fato_rateio": como_csv(rateio_)}
    return c


def rodar(codigo, mudar=None):
    return next(r for r in regras.REGRAS if r["codigo"] == codigo)["funcao"](mundo(mudar))


def test_regras_do_financeiro_estao_registradas_depois_da_a41():
    assert [r["codigo"] for r in regras.REGRAS][41:45] == ["A42", "A43", "A44", "A45"]


@pytest.mark.parametrize("codigo", ["A42", "A43", "A44", "A45"])
def test_mundo_consistente_nao_gera_ocorrencia(codigo):
    verificados, oc, resumo = rodar(codigo)
    assert oc == [] and verificados > 0 and resumo


def test_a42_resumo_mostra_pagantes_e_gratuitos():
    assert "32 ingressos (30 pagantes, 2 gratuitos)" in rodar("A42")[2]


def test_a42_detecta_publico_renda_preco_e_pagante_diferentes():
    def publico(m):
        m["bo"]["publico"] = "33"

    def renda(m):
        m["bo"]["renda_bruta"] = "801.00"

    def preco(m):
        m["bi"][0]["preco"] = "41.00"

    def pagante(m):
        m["bo"]["publico_pagante"] = "29"

    def devolvido(m):
        m["bi"][1]["devolvidos"] = "1"

    achados = {f.__name__: {o["detalhe"] for o in rodar("A42", f)[1]} for f in (publico, renda, preco, pagante, devolvido)}
    assert achados["publico"] == {"público (vendidos)", "público na tabela fato_ingresso"}
    assert {"renda bruta", "renda bruta na tabela fato_ingresso"} == achados["renda"]
    assert "SETOR LESTE - Inteira" in achados["preco"]
    assert achados["pagante"] == {"público pagante"}
    assert "ingressos devolvidos" in achados["devolvido"] and "SETOR LESTE - Meia" in achados["devolvido"]


def test_a42_detecta_ingresso_perdido_pelo_etl():
    c = mundo()
    c.t["fato_ingresso"] = c.t["fato_ingresso"][:-1]
    achados = {o["detalhe"] for o in next(r for r in regras.REGRAS if r["codigo"] == "A42")["funcao"](c)[1]}
    assert achados == {"público na tabela fato_ingresso"}


def test_a43_detecta_subtotal_total_e_renda_liquida_diferentes():
    def subtotal(m):
        m["bo"]["total_b3"] = "101.00"

    def total(m):
        m["bo"]["despesas_total"] = "141.00"

    def liquida(m):
        m["bo"]["renda_liquida"] = "600.00"

    def linha(m):
        m["bd"][2]["valor"] = "110.00"

    achados = {f.__name__: {o["detalhe"] for o in rodar("A43", f)[1]} for f in (subtotal, total, liquida, linha)}
    assert achados["subtotal"] == {"subtotal B3"}
    assert achados["total"] == {"total das despesas", "despesas na tabela fato_despesa"}
    assert achados["liquida"] == {"renda líquida"}
    assert achados["linha"] == {"subtotal B3", "total das despesas", "renda líquida", "despesas na tabela fato_despesa"}


def test_a43_avisa_quando_a_leitura_por_conta_nao_achou_o_total():
    def sem_total(m):
        m["bo"]["despesas_total"] = ""

    verificados, oc, _ = rodar("A43", sem_total)
    assert len(oc) == 1 and oc[0]["fonte_a"] == "leitura por conta (boletim)"


def test_a43_resumo_diz_que_a_retencao_de_inss_fica_fora_da_conta():
    assert "retenções de INSS informadas depois do total (fora da conta): R$ 5,00 em 1 jogos" in rodar("A43")[2]


def test_a44_detecta_percentual_valor_deducao_clube_e_lado_errados():
    def percentual(m):
        m["br"][0]["percentual"] = "90"

    def valor(m):
        m["br"][0]["valor"] = "600.00"

    def deducao(m):
        m["br"][0]["liquido"] = "659.68"

    def clube(m):
        m["br"][0]["clube"], m["br"][1]["clube"] = "Time B", "Time A"

    achados = {f.__name__: {o["fonte_a"] for o in rodar("A44", f)[1]} for f in (percentual, valor, deducao)}
    assert achados["percentual"] == {"percentuais"}
    assert achados["valor"] == {"valores da divisão", "líquido a receber"}
    assert achados["deducao"] == {"líquido a receber"}
    assert any(o["fonte_a"] == "divisão da renda" for o in rodar("A44", clube)[1])


def test_a44_detecta_divisao_que_o_etl_nao_gravou_para_os_dois_lados():
    c = mundo()
    c.t["fato_rateio"] = c.t["fato_rateio"][:1]
    oc = next(r for r in regras.REGRAS if r["codigo"] == "A44")["funcao"](c)[1]
    assert [o["fonte_a"] for o in oc] == ["tabela fato_rateio"]


def test_a45_pede_grupo_para_rubrica_nova():
    def sem_grupo(m):
        m["grupos"].pop("Ambulância")

    _, oc, _ = rodar("A45", sem_grupo)
    assert [(o["fonte_a"], o["valor_a"], o["valor_b"]) for o in oc] == [("boletim", "Ambulância", "sem grupo")]


def test_a45_avisa_quando_outros_passa_de_1_por_cento():
    def muito_outros(m):
        m["bi"][0]["localidade"] = "SETOR LESTE - Passaporte"

    _, oc, _ = rodar("A45", muito_outros)
    assert len(oc) == 1 and oc[0]["fonte_a"] == "ingressos" and "SETOR LESTE - Passaporte (10)" in oc[0]["detalhe"]


def test_a45_avisa_gratuidade_sem_lei_no_rotulo():
    def cortesia(m):
        m["bi"][2]["localidade"] = "SETOR LESTE - Cortesia"

    _, oc, _ = rodar("A45", cortesia)
    assert [o["fonte_a"] for o in oc] == ["linha de preço zero"] and oc[0]["numero_jogo"] == 1


# ---------- tabelas reais ----------

@precisa_proc
def test_tabelas_reais_fecham_com_as_totais_conhecidas():
    ingressos, despesas, rateio_ = (ler_csv(PROC / f"{n}.csv") for n in ("fato_ingresso", "fato_despesa", "fato_rateio"))
    assert (len(ingressos), len(despesas), len(rateio_)) == (2388, 1482, 144)
    assert sum(int(i["ingressos"]) for i in ingressos) == 784369
    assert sum(Decimal(i["arrecadacao"]) for i in ingressos) == Decimal("44730003.80")
    assert sum(Decimal(d["valor"]) for d in despesas) == Decimal("20404747.14")
    assert sum(Decimal(r["valor"]) for r in rateio_) == Decimal("24325256.66")
    assert all(d["grupo"] != "Sem grupo" for d in despesas)


@precisa_proc
def test_tabelas_reais_tem_chaves_unicas_e_partidas_existentes():
    ids_partida = {p["id_partida"] for p in ler_csv(PROC / "fato_partida.csv")}
    for nome, chave in (("fato_ingresso", "id_ingresso"), ("fato_despesa", "id_despesa"), ("fato_rateio", "id_rateio")):
        linhas = ler_csv(PROC / f"{nome}.csv")
        assert len({l[chave] for l in linhas}) == len(linhas)
        assert {l["id_partida"] for l in linhas} <= ids_partida


@precisa_proc
def test_categorias_reais_cobrem_todo_o_publico_e_so_usam_as_do_arquivo():
    ingressos = ler_csv(PROC / "fato_ingresso.csv")
    nomes = {r["categoria"] for r in financeiro.ler_regras_ingresso()}
    assert {i["categoria"] for i in ingressos} <= nomes
    por_ordem = {i["categoria"]: i["ordem_categoria"] for i in ingressos}
    assert len(set(por_ordem.values())) == len(por_ordem)
    gratis = [i for i in ingressos if i["categoria"] == "Gratuidade por lei"]
    assert gratis and all(Decimal(i["preco"]) == 0 for i in gratis)
    assert all(Decimal(i["preco"]) > 0 for i in ingressos if i["categoria"] != "Gratuidade por lei")


@precisa_proc
def test_regras_a42_a45_passam_nos_dados_reais():
    if not (RAIZ / "data" / "raw" / "espn").exists():
        pytest.skip("coleta da ESPN ausente")
    c = regras.Contexto()
    for codigo in ("A42", "A43", "A44", "A45"):
        verificados, oc, resumo = next(r for r in regras.REGRAS if r["codigo"] == codigo)["funcao"](c)
        assert oc == [], (codigo, oc[:3])
