import importlib.util
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import regras  # noqa: E402
from comum import ler_csv  # noqa: E402
from fpf_pdf import ler_comissao, ler_escalacao, ler_substituicoes, texto_pdf  # noqa: E402

PROC = RAIZ / "data" / "processed"
PDFS = RAIZ / "data" / "raw" / "fpf_pdf" / "2026"
precisa_pdf = pytest.mark.skipif(not (PDFS / "sumula" / "57.pdf").exists(), reason="PDFs brutos ausentes (rode scripts/03_coletar_fpf_pdf.py)")
precisa_proc = pytest.mark.skipif(not (PROC / "fato_escalacao.csv").exists(), reason="rode 03b_ler_fpf_pdf e 04_tratar antes")


def carregar(nome, arquivo):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


tratar = carregar("tratar04", "04_tratar.py")


# ---------- texto no modo layout, montado como o pypdf devolve ----------

def atleta_txt(num, nome, tr="T", reg="500000/25", pa="P"):
    return f"{num:<5}{nome:<44}{tr}     {pa}     {reg}"


def linha_jogadores(esq=None, dir_=None):
    return (" " * 10 + (esq or "")).ljust(92) + (dir_ or "")


CABECALHO = (" " * 10 + "Nº    Nome Completo do Jogador          T/R    P/A     Registro").ljust(92) + "Nº    Nome Completo do Jogador          T/R    P/A    Registro"


def texto_relacao(linhas):
    return "\n".join(["Relação de Jogadores", " " * 40 + "Time A" + " " * 60 + "Time B", CABECALHO, *linhas, " T = Titular | R = Reserva | P = Profissional | A = Amador", "Federação Paulista de Futebol    Publicação da Súmula: 01/01/2026 10:00"])


def linha_comissao(esq=None, dir_=None):
    return (" " * 9 + (f"{esq[0]:<28}{esq[1]}" if esq else "")).ljust(97) + (f"{dir_[0]:<27}{dir_[1]}" if dir_ else "")


def texto_comissao(linhas):
    return "\n".join(["Comissão Técnica", " " * 40 + "Time A" + " " * 60 + "Time B", *linhas, "", " " * 70 + "Substituições"])


def linha_sub(equipe, ns, nome_s, ne, nome_e, tempo, per):
    return f"{'':9}{equipe:<44}{ns:<6}{nome_s:<48}{ne:<6}{nome_e:<46}{tempo:>6}{'':9}{per}"


def texto_subs(regulares, concussao):
    return "\n".join([" " * 70 + "Substituições", "         Equipe                      Nº    Saiu                    Nº    Entrou                 Tempo       1T/2T", *regulares, "", " " * 60 + "Substituições por concussão", *concussao, "", " " * 80 + "Gols", "         Equipe      Nº     Nome do Jogador"])


def test_relacao_atribui_cada_coluna_ao_time_certo_inclusive_linha_com_um_so_atleta():
    t = texto_relacao([
        linha_jogadores(atleta_txt(1, "Goleiro A"), atleta_txt(1, "Goleiro B", reg="500001/25")),
        linha_jogadores(atleta_txt(12, "Reserva A1", "R", "500002/25"), atleta_txt(12, "Reserva B1", "R", "500003/25", pa="A")),
        linha_jogadores(atleta_txt(13, "Reserva A2", "R", "500004/25")),
        linha_jogadores(None, atleta_txt(14, "Reserva B2", "R", "500005/25")),
    ])
    a = ler_escalacao(t, ["Time A", "Time B"])
    assert [(x["equipe"], x["numero"], x["situacao"]) for x in a] == [("Time A", 1, "T"), ("Time B", 1, "T"), ("Time A", 12, "R"), ("Time B", 12, "R"), ("Time A", 13, "R"), ("Time B", 14, "R")]
    assert [x["vinculo"] for x in a] == ["P", "P", "P", "A", "P", "P"]
    assert a[0]["nome"] == "Goleiro A" and a[0]["registro"] == "500000/25"


def test_relacao_recusa_linha_com_tres_atletas_e_cabecalho_ausente():
    tres = linha_jogadores(atleta_txt(1, "A"), atleta_txt(2, "B", reg="500001/25")) + "   " + atleta_txt(3, "C", reg="500002/25")
    with pytest.raises(ValueError, match="mais de dois"):
        ler_escalacao(texto_relacao([tres]), ["Time A", "Time B"])
    with pytest.raises(ValueError, match="cabeçalho"):
        ler_escalacao("Relação de Jogadores\nsem tabela\n T = Titular", ["Time A", "Time B"])


def test_comissao_com_nome_vazio_nome_truncado_e_linha_so_do_time_da_direita():
    t = texto_comissao([
        linha_comissao(("Técnico", "Fulano Um"), ("Técnico", "Sicrano Dois")),
        linha_comissao(("Auxiliar Técnico", "Beltrano Tres"), ("Auxiliar Técnico", "")),
        linha_comissao(("Auxiliar Técnico", ""), ("Auxiliar Técnico", "Nome muito comprido de pessoa da comissão...")),
        linha_comissao(None, ("Massagista", "Ciclano Cinco")),
        linha_comissao(("Médico", "Doutor Seis"), None),
    ])
    p = ler_comissao(t, ["Time A", "Time B"])
    assert [(x["equipe"], x["funcao"], x["nome"]) for x in p] == [
        ("Time A", "Técnico", "Fulano Um"), ("Time B", "Técnico", "Sicrano Dois"),
        ("Time A", "Auxiliar Técnico", "Beltrano Tres"), ("Time B", "Auxiliar Técnico", None),
        ("Time A", "Auxiliar Técnico", None), ("Time B", "Auxiliar Técnico", "Nome muito comprido de pessoa da comissão..."),
        ("Time B", "Massagista", "Ciclano Cinco"), ("Time A", "Médico", "Doutor Seis")]
    assert [x["nome_truncado"] for x in p] == [0, 0, 0, 0, 0, 1, 0, 0]


def test_substituicoes_intervalo_acrescimo_e_bloco_de_concussao_com_motivo_em_varias_linhas():
    t = texto_subs(
        [linha_sub("Time A", 10, "Saiu no intervalo", 20, "Entrou no intervalo", "-", "INT"),
         linha_sub("Time A", 11, "Saiu no segundo tempo", 21, "Entrou no segundo tempo", "66:00", "2T"),
         linha_sub("Time B", 5, "Saiu no acréscimo", 15, "Entrou no acréscimo", "+ 3", "2T"),
         linha_sub("Time B", 6, "Saiu cedo", 16, "Entrou cedo", "+ 2", "1T")],
        [linha_sub("Time A", 7, "Saiu concussão...", 46, "Entrou concussão", "35:00", "1T"),
         "         Motivo: Informo que a 6 (sexta) substituição ocorreu",
         "         devido a concussão do atleta.",
         "Federação Paulista de Futebol    Publicação da Súmula: 01/01/2026 10:00",
         "4 Página 2 de"])
    s = ler_substituicoes(t, ["Time A", "Time B"])
    assert [(x["equipe"], x["numero_saiu"], x["numero_entrou"], x["periodo"], x["minuto"], x["acrescimo"], x["bloco"]) for x in s] == [
        ("Time A", 10, 20, "INT", None, 0, "regular"), ("Time A", 11, 21, "2T", 66, 0, "regular"),
        ("Time B", 5, 15, "2T", 90, 3, "regular"), ("Time B", 6, 16, "1T", 45, 2, "regular"),
        ("Time A", 7, 46, "1T", 35, 0, "concussao")]
    assert s[0]["nome_saiu"] == "Saiu no intervalo" and s[3]["nome_entrou"] == "Entrou cedo"
    assert s[4]["motivo"] == "Informo que a 6 (sexta) substituição ocorreu devido a concussão do atleta."
    assert all(x["motivo"] == "" for x in s[:4])


def test_substituicoes_sem_nenhuma_e_linha_desconhecida():
    vazio = "\n".join([" " * 70 + "Substituições", " " * 50 + "NÃO HOUVE SUBSTITUIÇÕES", " " * 60 + "Substituições por concussão", " " * 50 + "NÃO HOUVE SUBSTITUIÇÕES", " " * 80 + "Gols"])
    assert ler_substituicoes(vazio, ["Time A", "Time B"]) == []
    estranho = "\n".join([" " * 70 + "Substituições", "linha que não é substituição", " " * 60 + "Substituições por concussão", " " * 80 + "Gols"])
    with pytest.raises(ValueError, match="não reconhecida"):
        ler_substituicoes(estranho, ["Time A", "Time B"])
    with pytest.raises(ValueError, match="não encontrados"):
        ler_substituicoes("nada", ["Time A", "Time B"])


# ---------- as súmulas reais ----------

def jogos_ref():
    return {int(l["numero"]): [l["mandante"], l["visitante"]] for l in ler_csv(RAIZ / "data" / "referencia" / "fpf_a1_2026_jogos.csv")}


def layout(n):
    return texto_pdf(PDFS / "sumula" / f"{n}.pdf", layout=True)


@precisa_pdf
def test_sumula_2_atleta_sozinho_na_linha_da_coluna_esquerda():
    eq = jogos_ref()[2]
    a = ler_escalacao(layout(2), eq)
    por_time = Counter(x["equipe"] for x in a)
    assert por_time == {"Santos": 23, "Grêmio Novorizontino": 22}
    sozinho = next(x for x in a if x["nome"] == "Gustavo Henrique Pereira")
    assert (sozinho["equipe"], sozinho["numero"], sozinho["situacao"]) == ("Santos", 48, "R")


@precisa_pdf
@pytest.mark.parametrize("n", [9, 14, 20, 28, 46])
def test_sumula_com_atleta_sozinho_na_coluna_direita_vai_para_o_visitante(n):
    eq = jogos_ref()[n]
    por_time = Counter(x["equipe"] for x in ler_escalacao(layout(n), eq))
    assert por_time[eq[1]] == por_time[eq[0]] + 1


@precisa_pdf
def test_sumula_52_substituicoes_do_intervalo_e_por_concussao():
    eq = jogos_ref()[52]
    s = ler_substituicoes(layout(52), eq)
    assert Counter(x["bloco"] for x in s) == {"regular": 10, "concussao": 2}
    assert sum(1 for x in s if x["periodo"] == "INT") == 2 and all(x["minuto"] is None for x in s if x["periodo"] == "INT")
    conc = [x for x in s if x["bloco"] == "concussao"]
    assert {x["equipe"] for x in conc} == {"São Paulo", "Primavera SAF"}
    assert any("concussão" in x["motivo"] for x in conc)
    com = ler_comissao(layout(52), eq)
    assert {(c["equipe"], c["nome"]) for c in com if c["funcao"] == "Técnico"} == {("São Paulo", "Hernan Jorge Crespo"), ("Primavera SAF", "Rafael Marques Mariano")}


@precisa_pdf
def test_sumula_60_traz_o_cargo_de_tecnico_do_palmeiras_sem_nome():
    com = ler_comissao(layout(60), jogos_ref()[60])
    tecnicos = {c["equipe"]: c["nome"] for c in com if c["funcao"] == "Técnico"}
    assert tecnicos == {"Palmeiras": None, "Guarani": "Matheus Silva Ferreira da Costa"}


@precisa_pdf
def test_as_72_sumulas_dao_22_titulares_e_os_totais_conhecidos():
    atletas = subs = 0
    for n, eq in jogos_ref().items():
        a = ler_escalacao(layout(n), eq)
        atletas += len(a)
        assert Counter(x["equipe"] for x in a if x["situacao"] == "T") == {eq[0]: 11, eq[1]: 11}, n
        subs += len(ler_substituicoes(layout(n), eq))
    assert (atletas, subs) == (3292, 706)


# ---------- ETL: minutos, gols, cartões e nomes (dados inventados) ----------

def esc_linha(num, nome, sit="T", lado="mandante", equipe="Time A", reg=None, vinc="P", jogo=1):
    return {"numero_jogo": str(jogo), "fase": "PRIMEIRA FASE", "lado": lado, "equipe": equipe, "numero": str(num), "nome": nome, "situacao": sit, "vinculo": vinc, "registro": reg or f"{600000 + num}/25"}


def sub_linha(ns, ne, periodo, minuto, acr=0, bloco="regular", equipe="Time A", motivo="", jogo=1):
    return {"numero_jogo": str(jogo), "fase": "PRIMEIRA FASE", "ordem": "1", "equipe": equipe, "bloco": bloco, "numero_saiu": str(ns), "nome_saiu": "x", "numero_entrou": str(ne), "nome_entrou": "y", "tempo": "", "periodo": periodo, "minuto": "" if minuto is None else str(minuto), "acrescimo": str(acr), "motivo": motivo}


def ev(num, tipo, periodo="2T", minuto=50, clube=1, apelido=None):
    return {"id_partida": 100, "id_clube": clube, "funcao": "Atleta", "numero_camisa": num, "tipo_evento": tipo, "apelido": apelido, "minuto": minuto, "periodo": periodo}


def elenco(esc, subs=(), com=(), evs=()):
    return tratar.montar_elenco(list(esc), list(subs), list(com), list(evs), {"Time A": 1, "Time B": 2}, {1: 100})


def time_a():
    return [esc_linha(n, f"Atleta Numero {n}") for n in range(1, 12)] + [esc_linha(n, f"Reserva Numero {n}", "R") for n in range(12, 16)]


def test_minutos_de_quem_ficou_saiu_entrou_no_intervalo_ou_no_acrescimo():
    subs = [sub_linha(2, 12, "2T", 54), sub_linha(3, 13, "INT", None), sub_linha(4, 14, "2T", 90, 3), sub_linha(5, 15, "1T", 45, 2)]
    _, esc, _, _ = elenco(time_a(), subs)
    m = {e["numero_camisa"]: e for e in esc}
    assert (m[1]["minutos_jogados"], m[2]["minutos_jogados"], m[12]["minutos_jogados"]) == (90, 54, 36)
    assert (m[3]["minutos_jogados"], m[13]["minutos_jogados"]) == (45, 45)
    assert (m[4]["minutos_jogados"], m[14]["minutos_jogados"], m[14]["jogou"]) == (90, 0, 1)
    assert (m[5]["minutos_jogados"], m[15]["minutos_jogados"]) == (45, 45)
    assert sum(e["minutos_jogados"] for e in esc) == 990


def test_minutos_encerram_na_expulsao_e_nao_voltam_a_contar_depois_da_troca():
    evs = [ev(6, "vermelho", "2T", 80), ev(7, "vermelho", "2T", 90), ev(8, "segundo_amarelo", "1T", 30), ev(9, "vermelho", "PJ", None)]
    subs = [sub_linha(10, 12, "2T", 85), sub_linha(11, 13, "2T", 60)]
    evs += [ev(11, "vermelho", "2T", 90)]
    _, esc, _, _ = elenco(time_a(), subs, evs=evs)
    m = {e["numero_camisa"]: e for e in esc}
    assert (m[6]["minutos_jogados"], m[7]["minutos_jogados"], m[8]["minutos_jogados"], m[9]["minutos_jogados"]) == (80, 90, 30, 90)
    assert m[11]["minutos_jogados"] == 60
    assert m[12]["minutos_jogados"] == 5


def test_reserva_que_nao_entrou_nao_joga_mesmo_com_cartao():
    _, esc, _, _ = elenco(time_a(), evs=[ev(14, "amarelo", "2T", 70), ev(15, "vermelho", "2T", 75)])
    m = {e["numero_camisa"]: e for e in esc}
    assert (m[14]["jogou"], m[14]["minutos_jogados"], m[14]["amarelos"]) == (0, 0, 1)
    assert (m[15]["jogou"], m[15]["minutos_jogados"], m[15]["vermelhos"]) == (0, 0, 1)
    assert m[14]["periodo_entrada"] is None and m[14]["minuto_entrada"] is None


def test_gols_gols_contra_e_regra_da_fpf_para_cartoes_por_atleta():
    evs = [ev(9, "gol", "1T", 10), ev(9, "gol_penalti", "2T", 70), ev(10, "gol_contra", "1T", 20), ev(6, "amarelo", "1T", 30), ev(6, "segundo_amarelo", "2T", 60), ev(7, "amarelo", "2T", 10), ev(8, "vermelho", "2T", 50), ev(1, "gol_falta", "2T", 80)]
    _, esc, _, _ = elenco(time_a(), evs=evs)
    m = {e["numero_camisa"]: e for e in esc}
    assert (m[9]["gols"], m[9]["gols_contra"]) == (2, 0)
    assert (m[10]["gols"], m[10]["gols_contra"]) == (0, 1)
    assert (m[1]["gols"], m[6]["amarelos"], m[6]["vermelhos"]) == (1, 0, 1)
    assert (m[7]["amarelos"], m[7]["vermelhos"], m[8]["amarelos"], m[8]["vermelhos"]) == (1, 0, 0, 1)


def test_eventos_de_comissao_e_disputa_de_penaltis_nao_entram_na_escalacao():
    evs = [{**ev(None, "penalti_disputa", "PEN", 0), "numero_camisa": None}, {**ev(3, "amarelo"), "funcao": "Técnico"}]
    _, esc, _, _ = elenco(time_a(), evs=evs)
    assert all(e["amarelos"] == 0 and e["gols"] == 0 for e in esc)


def test_substituicao_ordenada_no_tempo_com_atletas_ligados_e_concussao():
    subs = [sub_linha(4, 14, "2T", 70), sub_linha(2, 12, "INT", None), sub_linha(3, 13, "2T", 70, bloco="concussao", motivo="texto"), sub_linha(5, 15, "2T", 54)]
    atl, _, sb, _ = elenco(time_a(), subs)
    assert [(s["ordem"], s["numero_saiu"], s["periodo"], s["minuto"], s["tipo"]) for s in sb] == [(1, 2, "INT", None, "regular"), (2, 5, "2T", 54, "regular"), (3, 4, "2T", 70, "regular"), (4, 3, "2T", 70, "concussao")]
    assert sb[0]["id_atleta_saiu"] == "atleta-numero-2" and sb[0]["id_atleta_entrou"] == "reserva-numero-12"
    assert sb[0]["minuto_total"] is None and sb[1]["minuto_total"] == 54 and sb[3]["motivo"] == "texto"
    assert sb[0]["id_substituicao"] == "100-1-01"


def test_substituicao_de_camisa_inexistente_fica_sem_atleta_para_a_regra_apontar():
    _, _, sb, _ = elenco(time_a(), [sub_linha(2, 99, "2T", 60)])
    assert sb[0]["id_atleta_saiu"] == "atleta-numero-2" and sb[0]["id_atleta_entrou"] is None


def test_camisa_repetida_e_atleta_que_sai_ou_entra_duas_vezes_param_o_etl():
    with pytest.raises(ValueError, match="camisa repetida"):
        elenco(time_a() + [esc_linha(3, "Outro", "R")])
    with pytest.raises(ValueError, match="duas vezes"):
        elenco(time_a(), [sub_linha(2, 12, "2T", 54), sub_linha(2, 13, "2T", 60)])
    with pytest.raises(ValueError, match="duas vezes"):
        elenco(time_a(), [sub_linha(2, 12, "2T", 54), sub_linha(3, 12, "2T", 60)])


def test_dim_atleta_apelido_vem_dos_gols_e_o_nome_curto_pula_particulas_e_palavra_cortada():
    esc = [esc_linha(1, "Luciano da Rocha Neves"), esc_linha(2, "Vinicius dos Santos de Oliveira P"), esc_linha(3, "Gabriel Barbosa Almeida"), esc_linha(4, "Neymar")]
    atl, _, _, _ = elenco(esc, evs=[ev(3, "gol", apelido="Gabigol"), ev(3, "gol", apelido="Gabigol"), ev(3, "gol", apelido="Gabi")])
    nomes = {a["id_atleta"]: a for a in atl}
    assert nomes["luciano-da-rocha-neves"]["nome_curto"] == "Luciano Neves"
    assert nomes["vinicius-dos-santos-de-oliveira-p"]["nome_truncado"] == 1 and nomes["vinicius-dos-santos-de-oliveira-p"]["nome_curto"] == "Vinicius Oliveira"
    assert (nomes["gabriel-barbosa-almeida"]["apelido"], nomes["gabriel-barbosa-almeida"]["nome_curto"]) == ("Gabigol", "Gabigol")
    assert nomes["neymar"]["nome_curto"] == "Neymar"


def test_dim_atleta_junta_os_registros_do_mesmo_nome_e_fica_com_o_clube_de_mais_jogos():
    a1 = [esc_linha(1, "Mesmo Atleta", reg="100/22", jogo=1), esc_linha(1, "Mesmo Atleta", reg="200/26", jogo=2)]
    b = [esc_linha(1, "Mesmo Atleta", reg="300/26", jogo=3, equipe="Time B", lado="visitante")]
    atl, esc, _, _ = tratar.montar_elenco(a1 + b, [], [], [], {"Time A": 1, "Time B": 2}, {1: 101, 2: 102, 3: 103})
    assert len(atl) == 1 and len(esc) == 3
    assert (atl[0]["registros"], atl[0]["id_clube"]) == ("100/22; 200/26; 300/26", 1)


def test_comissao_pula_cargo_sem_nome_e_numera_por_equipe_e_jogo():
    com = [{"numero_jogo": "1", "fase": "x", "equipe": "Time A", "funcao": f, "nome": n, "nome_truncado": "0"} for f, n in (("Técnico", "T Um"), ("Auxiliar Técnico", ""), ("Médico", "M Dois"))]
    _, _, _, c = elenco(time_a(), com=com)
    assert [(x["id_comissao"], x["funcao"]) for x in c] == [("100-1-01", "Técnico"), ("100-1-02", "Médico")]


# ---------- regras A35 a A41 detectam o defeito que prometem detectar ----------

def como_csv(linhas):
    return [{k: ("" if v is None else str(v)) for k, v in l.items()} for l in linhas]


def contexto_rodando(esc_raw, subs_raw=(), com_raw=(), evs=()):
    atl, esc, sb, com = elenco(esc_raw, subs_raw, com_raw, evs)
    nomes = {(r["equipe"], int(r["numero"])): r["nome"] for r in esc_raw}
    equipe_de = {1: "Time A", 2: "Time B"}
    c = regras.Contexto.__new__(regras.Contexto)
    c.id_partida = {1: 100}
    c.num_partida = {"100": 1}
    c.fpf_nome = {1: "Time A", 2: "Time B"}
    c.nome_para_id = {"Time A": 1, "Time B": 2}
    c.t = {"fato_partida": como_csv([{"id_partida": 100, "numero_jogo": 1, "id_clube_mandante": 1, "id_clube_visitante": 2}]),
           "fato_escalacao": como_csv(esc), "dim_atleta": como_csv(atl), "fato_substituicao": como_csv(sb), "fato_comissao": como_csv(com),
           "fato_evento": como_csv([{"id_evento": f"100-{i + 1:02d}", **e, "pessoa": e.get("pessoa") or nomes.get((equipe_de[e["id_clube"]], e["numero_camisa"]), "Desconhecido"), "acrescimo": e.get("acrescimo", 0), "id_clube_creditado": e["id_clube"]} for i, e in enumerate(evs)])}
    c.se, c.ss = esc_raw, subs_raw
    return c


def contexto_bruto(se, ss):
    c = regras.Contexto.__new__(regras.Contexto)
    c.id_partida = {1: 100}
    c.nome_para_id = {"Time A": 1, "Time B": 2}
    c.se, c.ss = se, ss
    return c


def time_b():
    return [esc_linha(n, f"Atleta B {n}", "T" if n <= 11 else "R", lado="visitante", equipe="Time B", reg=f"{700000 + n}/25") for n in range(1, 14)]


def rodar(codigo, c):
    return next(r for r in regras.REGRAS if r["codigo"] == codigo)["funcao"](c)


def test_regras_novas_estao_registradas_em_sequencia():
    assert [r["codigo"] for r in regras.REGRAS][34:41] == [f"A{i}" for i in range(35, 42)]


def test_a35_detecta_time_sem_11_titulares_registro_repetido_e_atleta_nos_dois_times():
    ok = contexto_rodando(time_a() + time_b())
    assert rodar("A35", ok)[1] == []
    fraco = [e for e in time_a() if e["numero"] != "11"]
    _, oc, _ = rodar("A35", contexto_rodando(fraco + time_b()))
    assert len(oc) == 1 and oc[0]["valor_a"] == 10 and oc[0]["id_clube"] == 1
    repetido = time_a() + time_b()
    repetido[12]["registro"] = repetido[0]["registro"]
    _, oc, _ = rodar("A35", contexto_rodando(repetido))
    assert any("registro" in str(o["valor_a"]) for o in oc)
    nos_dois = time_a() + time_b()
    nos_dois[-1]["nome"] = nos_dois[0]["nome"]
    _, oc, _ = rodar("A35", contexto_rodando(nos_dois))
    assert any(o["detalhe"] == "atleta repetido no jogo" for o in oc)


def test_a36_detecta_camisa_fora_da_relacao_nome_diferente_titular_que_entra_e_troca_repetida():
    def sub(ns, nome_s, ne, nome_e, equipe="Time A"):
        return {**sub_linha(ns, ne, "2T", 60, equipe=equipe), "nome_saiu": nome_s, "nome_entrou": nome_e}

    esc = time_a() + time_b()
    boa = [sub(2, "Atleta Numero 2", 12, "Reserva Numero 12"), sub(3, "Atleta Numero...", 13, "Reserva Numero 13")]
    assert rodar("A36", contexto_bruto(esc, boa))[1] == []
    ruins = [sub(2, "Atleta Numero 2", 99, "Reserva Numero 99"), sub(3, "Outro Nome", 13, "Reserva Numero 13"), sub(4, "Atleta Numero 4", 5, "Atleta Numero 5"),
             sub(6, "Atleta Numero 6", 14, "Reserva Numero 14"), sub(7, "Atleta Numero 7", 14, "Reserva Numero 14")]
    _, oc, _ = rodar("A36", contexto_bruto(esc, ruins))
    detalhes = [o["detalhe"] for o in oc]
    assert "entrou" in detalhes and "saiu: nome diferente" in detalhes
    assert "entrou quem já era titular" in detalhes and "entrou duas vezes" in detalhes


def test_a37_detecta_seis_regulares_e_duas_de_concussao():
    esc = time_a() + time_b()
    seis = [sub_linha(n, n + 10, "2T", 60) for n in range(1, 7)]
    _, oc, _ = rodar("A37", contexto_bruto(esc, seis))
    assert len(oc) == 1 and oc[0]["valor_a"] == 6
    duas = [sub_linha(1, 12, "2T", 60, bloco="concussao"), sub_linha(2, 13, "2T", 61, bloco="concussao")]
    assert len(rodar("A37", contexto_bruto(esc, duas))[1]) == 1
    assert rodar("A37", contexto_bruto(esc, [sub_linha(n, n + 10, "2T", 60) for n in range(1, 6)] + [sub_linha(6, 16, "2T", 70, bloco="concussao")]))[1] == []


def test_a38_detecta_gol_de_quem_nao_estava_em_campo_ou_nao_esta_na_relacao():
    esc = time_a() + time_b()
    subs = [sub_linha(2, 12, "2T", 54)]
    ok = [ev(2, "gol", "1T", 20), ev(12, "gol", "2T", 54), ev(12, "gol", "2T", 80), ev(3, "gol", "2T", 90)]
    assert rodar("A38", contexto_rodando(esc, subs, evs=ok))[1] == []
    _, oc, _ = rodar("A38", contexto_rodando(esc, subs, evs=[ev(2, "gol", "2T", 60)]))
    assert oc[0]["valor_b"] == "atleta fora de campo"
    _, oc, _ = rodar("A38", contexto_rodando(esc, subs, evs=[ev(12, "gol", "1T", 30)]))
    assert len(oc) == 1
    _, oc, _ = rodar("A38", contexto_rodando(esc, subs, evs=[ev(99, "gol", "2T", 30)]))
    assert oc[0]["valor_b"] == "camisa ausente"
    _, oc, _ = rodar("A38", contexto_rodando(esc, subs, evs=[{**ev(3, "gol", "2T", 30), "pessoa": "Outra Pessoa"}]))
    assert "nome diferente" in oc[0]["detalhe"]


def test_a39_conta_cartao_no_banco_e_detecta_camisa_ausente():
    esc = time_a() + time_b()
    _, oc, resumo = rodar("A39", contexto_rodando(esc, evs=[ev(14, "amarelo", "2T", 70), ev(3, "amarelo", "1T", 10), ev(3, "segundo_amarelo", "2T", 50)]))
    assert oc == [] and "1 recebidos no banco" in resumo
    _, oc, _ = rodar("A39", contexto_rodando(esc, evs=[ev(99, "vermelho", "2T", 70)]))
    assert oc[0]["valor_b"] == "camisa ausente"


def test_a40_detecta_equipe_sem_tecnico_e_com_dois():
    def com(*nomes):
        return [{"numero_jogo": "1", "fase": "x", "equipe": e, "funcao": "Técnico", "nome": n, "nome_truncado": "0"} for e, n in nomes]

    esc = time_a() + time_b()
    assert rodar("A40", contexto_rodando(esc, com_raw=com(("Time A", "A1"), ("Time B", "B1"))))[1] == []
    _, oc, _ = rodar("A40", contexto_rodando(esc, com_raw=com(("Time A", "A1"), ("Time B", ""))))
    assert len(oc) == 1 and oc[0]["valor_a"] == "técnico sem nome" and oc[0]["id_clube"] == 2
    _, oc, _ = rodar("A40", contexto_rodando(esc, com_raw=com(("Time A", "A1"), ("Time A", "A2"), ("Time B", "B1"))))
    assert len(oc) == 1 and oc[0]["valor_a"] == "2 técnicos"


def test_a41_detecta_registro_com_dois_nomes_e_nome_em_dois_clubes_e_conta_dois_registros():
    ok = time_a() + time_b()
    assert rodar("A41", contexto_rodando(ok))[1] == []
    dois_nomes = time_a() + time_b()
    dois_nomes[1]["registro"] = dois_nomes[0]["registro"]
    assert any(o["fonte_a"] == "registro" for o in rodar("A41", contexto_rodando(dois_nomes))[1])
    dois_clubes = time_a() + time_b()
    dois_clubes[-1]["nome"] = dois_clubes[0]["nome"]
    assert any(o["fonte_a"] == "nome" for o in rodar("A41", contexto_rodando(dois_clubes))[1])
    renovado = time_a() + time_b() + [esc_linha(30, "Atleta Numero 1", "R", reg="999999/26")]
    _, oc, resumo = rodar("A41", contexto_rodando(renovado))
    assert oc == [] and "1 atletas com dois registros" in resumo


# ---------- as tabelas reais ----------

def tab(nome):
    return ler_csv(PROC / f"{nome}.csv")


@precisa_proc
def test_tabelas_do_elenco_tem_os_totais_da_temporada():
    assert (len(tab("dim_atleta")), len(tab("fato_escalacao")), len(tab("fato_substituicao")), len(tab("fato_comissao"))) == (505, 3292, 706, 1066)
    esc = tab("fato_escalacao")
    assert Counter(e["situacao"] for e in esc) == {"titular": 1584, "reserva": 1708}
    assert sum(1 for e in esc if e["jogou"] == "1") == 1584 + 706
    assert sum(1 for e in esc if e["vinculo"] == "amador") == 17


@precisa_proc
def test_chaves_unicas_e_chaves_estrangeiras_do_elenco():
    partidas = {p["id_partida"] for p in tab("fato_partida")}
    clubes = {c["id_clube"] for c in tab("dim_clube")}
    atletas = {a["id_atleta"] for a in tab("dim_atleta")}
    for nome, col in (("dim_atleta", "id_atleta"), ("fato_escalacao", "id_escalacao"), ("fato_substituicao", "id_substituicao"), ("fato_comissao", "id_comissao")):
        ids = [l[col] for l in tab(nome)]
        assert len(ids) == len(set(ids)), nome
    assert all(a["id_clube"] in clubes for a in tab("dim_atleta"))
    for e in tab("fato_escalacao"):
        assert e["id_partida"] in partidas and e["id_clube"] in clubes and e["id_atleta"] in atletas
    for s in tab("fato_substituicao"):
        assert s["id_partida"] in partidas and s["id_atleta_saiu"] in atletas and s["id_atleta_entrou"] in atletas
    assert all(c["id_partida"] in partidas and c["id_clube"] in clubes for c in tab("fato_comissao"))


@precisa_proc
def test_cada_equipe_em_cada_jogo_tem_11_titulares_e_os_minutos_fecham():
    por_tj, perdido = defaultdict(list), defaultdict(int)
    for e in tab("fato_escalacao"):
        por_tj[(e["id_partida"], e["id_clube"])].append(e)
    assert len(por_tj) == 144
    esc = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e for e in tab("fato_escalacao")}
    for e in tab("fato_evento"):
        if e["tipo_evento"] in ("vermelho", "segundo_amarelo") and e["funcao"] == "Atleta" and e["numero_camisa"] != "" and e["minuto"] != "":
            r = esc[(e["id_partida"], e["id_clube"], e["numero_camisa"])]
            saiu_antes = r["periodo_saida"] != "" and (45 if r["periodo_saida"] == "INT" else int(r["minuto_saida"])) <= int(e["minuto"])
            if r["jogou"] == "1" and not saiu_antes:
                perdido[(e["id_partida"], e["id_clube"])] += 90 - int(e["minuto"])
    for k, linhas in por_tj.items():
        assert sum(1 for l in linhas if l["situacao"] == "titular") == 11, k
        assert sum(int(l["minutos_jogados"]) for l in linhas) == 990 - perdido[k], k


@precisa_proc
def test_gols_dos_atletas_mais_gols_contra_do_adversario_fecham_o_placar():
    gols, contra = defaultdict(int), defaultdict(int)
    for e in tab("fato_escalacao"):
        gols[(e["id_partida"], e["id_clube"])] += int(e["gols"])
        contra[(e["id_partida"], e["id_clube"])] += int(e["gols_contra"])
    for p in tab("fato_partida"):
        m, v = p["id_clube_mandante"], p["id_clube_visitante"]
        assert gols[(p["id_partida"], m)] + contra[(p["id_partida"], v)] == int(p["gols_mandante"]), p["numero_jogo"]
        assert gols[(p["id_partida"], v)] + contra[(p["id_partida"], m)] == int(p["gols_visitante"]), p["numero_jogo"]
    reservas = sum(int(e["gols"]) for e in tab("fato_escalacao") if e["situacao"] == "reserva")
    assert reservas == 34


@precisa_proc
def test_cartoes_dos_atletas_mais_os_da_comissao_somam_o_total_oficial_da_fpf():
    esc, comissao = tab("fato_escalacao"), [e for e in tab("fato_evento") if e["funcao"] != "Atleta"]
    assert not any(e["tipo_evento"] == "segundo_amarelo" for e in comissao)
    assert sum(int(e["amarelos"]) for e in esc) + sum(1 for e in comissao if e["tipo_evento"] == "amarelo") == 385
    assert sum(int(e["vermelhos"]) for e in esc) + sum(1 for e in comissao if e["tipo_evento"] == "vermelho") == 28


@precisa_proc
def test_substituicoes_batem_com_a_escalacao():
    esc = {(e["id_partida"], e["id_clube"], e["id_atleta"]): e for e in tab("fato_escalacao")}
    for s in tab("fato_substituicao"):
        quem_entrou = esc[(s["id_partida"], s["id_clube"], s["id_atleta_entrou"])]
        quem_saiu = esc[(s["id_partida"], s["id_clube"], s["id_atleta_saiu"])]
        assert quem_entrou["situacao"] == "reserva" and quem_entrou["periodo_entrada"] == s["periodo"] and quem_entrou["minuto_entrada"] == s["minuto"]
        assert quem_saiu["periodo_saida"] == s["periodo"] and quem_saiu["minuto_saida"] == s["minuto"]


@precisa_proc
def test_o_tecnico_de_cada_clube_e_um_so_e_o_palmeiras_tem_um_jogo_sem_nome():
    tecnicos = defaultdict(set)
    for c in tab("fato_comissao"):
        if c["funcao"] == "Técnico":
            tecnicos[c["id_clube"]].add(c["nome"])
    assert len(tecnicos) == 16 and all(len(v) == 1 for v in tecnicos.values())
    assert sum(1 for c in tab("fato_comissao") if c["funcao"] == "Técnico") == 143
    assert tecnicos["3320"] == {"Abel Fernando Moreira Ferreira"}
