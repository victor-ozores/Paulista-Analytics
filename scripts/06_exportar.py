"""Gera o Excel de conferência com fórmulas vivas.

Entradas : data/processed/ e docs/dicionario_indicadores.md
Saída    : excel/Paulista_Analytics_conferencia_A1_2026.xlsx (não versionado)

Cada indicador do dicionário é recalculado por fórmula de Excel sobre as abas de dados e comparado
com o valor que o Python calculou (aba "Referência Python"). A classificação é refeita com o
desempate do Art. 16 e comparada com a tabela oficial da FPF. Veja a aba LEIA-ME.

Uso: python scripts/06_exportar.py [--saida CAMINHO]
Depois: python scripts/verificar_excel.py --salvar   (recalcula no Excel e confere)
"""
import re
import sys
from collections import namedtuple
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.table import Table, TableStyleInfo

from comum import RAIZ, ler_csv

PROC = RAIZ / "data" / "processed"
SAIDA = RAIZ / "excel" / "Paulista_Analytics_conferencia_A1_2026.xlsx"
DICIONARIO = RAIZ / "docs" / "dicionario_indicadores.md"
FASE_CLASSIFICACAO = "PRIMEIRA FASE"

FMT_DATA, FMT_INT, FMT_DIN, FMT_DEC = "dd/mm/yyyy", "#,##0", '"R$" #,##0.00', "#,##0.0000"
AZUL, CINZA = "1F3A5F", "6B7280"
VERDE, VERMELHO, AMARELO, NEUTRO = "C6EFCE", "FFC7CE", "FFEB9C", "E5E7EB"
Col = namedtuple("Col", "titulo chave fmt larg nome formula", defaults=(None, None, None, None))

ROTULOS = {
    "I01": "Jogos", "I02": "Gols", "I03": "Gols por jogo", "I04": "Vitórias do mandante", "I05": "Empates", "I06": "Vitórias do visitante",
    "I07": "% de vitórias do mandante", "I08": "% de empates", "I09": "% de vitórias do visitante", "I10": "Público total", "I11": "Público médio",
    "I12": "Maior público", "I13": "Menor público", "I14": "Público pagante", "I15": "% de pagantes", "I16": "Renda bruta", "I17": "Renda líquida",
    "I18": "Ticket médio", "I19": "Jogos com renda líquida negativa", "I20": "Cartões amarelos (regra da FPF)", "I21": "Cartões vermelhos (regra da FPF)",
    "I22": "Cartões por jogo", "I23": "Acréscimo médio por jogo (min)", "I24": "Gols na faixa de minutos", "I25": "Gols de pênalti", "I26": "Jogos sem gols",
    "I38": "Despesas", "I39": "Despesas sobre a renda bruta (%)", "I40": "Despesa por ingresso", "I41": "Ingressos em setor de visitante", "I42": "Torcida visitante (% do público)", "I43": "Deduções sobre a renda líquida", "I44": "Líquido a receber",
    "I45": "Ingressos vendidos", "I46": "Arrecadação dos ingressos", "I47": "Preço médio do ingresso", "I48": "% dos ingressos", "I49": "% da arrecadação", "I50": "% das despesas", "I51": "Renda bruta como mandante", "I52": "Renda líquida como mandante",
    "I53": "Torcida visitante recebida", "I54": "Torcida visitante levada", "I55": "Atletas em campo", "I56": "Titulares", "I57": "Reservas que entraram", "I58": "Substituições", "I59": "Gols de reservas",
    "I34": "Regras de conferência executadas", "I35": "Regras sem nenhuma ocorrência", "I36": "Inconsistências abertas", "I37": "Inconsistências explicadas, aceitas ou corrigidas",
}
GERAIS = ["I01", "I02", "I03", "I04", "I05", "I06", "I07", "I08", "I09", "I10", "I11", "I12", "I13", "I14", "I15", "I16", "I17", "I18", "I19", "I20", "I21", "I22", "I23", "I25", "I26"]
POR_FASE = ["I01", "I02", "I03", "I10", "I11", "I16", "I17", "I20", "I21"]
QUALIDADE = ["I34", "I35", "I36", "I37"]
FAIXAS = [("01-15", 0, 15), ("16-30", 16, 30), ("31-45", 31, 45), ("46-60", 46, 60), ("61-75", 61, 75), ("76-90+", 76, 999)]


def num(s):
    if s in ("", None):
        return None
    try:
        return int(s)
    except ValueError:
        return float(s)


def tolerancia(unidade):
    if unidade.startswith("R$"):
        return 0.005
    if unidade in ("%", "gols/jogo", "pessoas/jogo", "cartões/jogo", "min/jogo"):
        return 0.00006
    return 0


def formato(unidade):
    if unidade.startswith("R$"):
        return FMT_DIN
    return FMT_INT if unidade in ("jogos", "gols", "pessoas", "cartões", "regras", "ocorrências", "pontos", "posição", "ingressos", "atletas-jogo", "substituições") else FMT_DEC


def definir_nome(wb, nome, ws, letra, r1, r2=None):
    r2 = r2 or r1
    alvo = f"${letra}${r1}" if r1 == r2 else f"${letra}${r1}:${letra}${r2}"
    wb.defined_names[nome] = DefinedName(nome, attr_text=f"'{ws.title}'!{alvo}")


def escrever_tabela(wb, ws, tabela, prefixo, colunas, linhas, topo=1):
    letra = {c.chave: get_column_letter(i) for i, c in enumerate(colunas, 1)}
    for i, c in enumerate(colunas, 1):
        ws.cell(topo, i, c.titulo)
        if c.larg:
            ws.column_dimensions[get_column_letter(i)].width = c.larg
    for k, linha in enumerate(linhas):
        r = topo + 1 + k
        for i, c in enumerate(colunas, 1):
            cel = ws.cell(r, i, c.formula(r, letra) if c.formula else linha.get(c.chave))
            if c.fmt:
                cel.number_format = c.fmt
    fim = topo + len(linhas)
    t = Table(displayName=tabela, ref=f"A{topo}:{get_column_letter(len(colunas))}{fim}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(t)
    for c in colunas:
        if c.nome:
            definir_nome(wb, f"{prefixo}_{c.nome}", ws, letra[c.chave], topo + 1, fim)
    return letra, topo + 1, fim


def titulo(ws, texto, sub=None):
    ws["A1"] = texto
    ws["A1"].font = Font(size=16, bold=True, color=AZUL)
    if sub:
        ws["A2"] = sub
        ws["A2"].font = Font(italic=True, color=CINZA)


def colorir(ws, intervalo, regras):
    for valor, cor in regras.items():
        ws.conditional_formatting.add(intervalo, CellIsRule(operator="equal", formula=[f'"{valor}"'], fill=PatternFill("solid", bgColor=cor, fgColor=cor)))


def ler_dicionario():
    linhas = []
    for l in DICIONARIO.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\| I\d\d \|", l):
            cel = [c.strip().replace("`", "") for c in l.strip().strip("|").split("|")]
            if len(cel) != 7:
                raise ValueError(f"linha do dicionário com {len(cel)} colunas (esperava 7): {l[:60]}")
            linhas.append(cel)
    return linhas


def carregar():
    nomes = ("fato_partida", "fato_evento", "dim_clube", "dim_fase", "dim_estadio", "dim_arbitro", "fato_classificacao_oficial", "fato_inconsistencia", "resultado_regra", "ref_indicadores", "fato_ingresso", "fato_despesa", "fato_rateio", "fato_escalacao", "fato_substituicao", "dim_atleta")
    t = {n: ler_csv(PROC / f"{n}.csv") for n in nomes}
    d = {"clube": {c["id_clube"]: c["nome_popular"] for c in t["dim_clube"]}, "fase": {f["id_fase"]: f["nome_fase"] for f in t["dim_fase"]}, "estadio": {e["id_estadio"]: e for e in t["dim_estadio"]}, "arbitro": {a["id_arbitro"]: a["nome"] for a in t["dim_arbitro"]}}
    return t, d


def construir(destino=SAIDA):
    t, d = carregar()
    wb = Workbook()
    abas = {}
    for nome, cor in (("LEIA-ME", "1F3A5F"), ("Resumo", "1F3A5F"), ("Classificação", "1F3A5F"), ("Artilharia", "1F3A5F"), ("Financeiro", "1F3A5F"), ("Elenco", "1F3A5F"), ("Partidas", "2E7D32"), ("Eventos", "2E7D32"), ("Escalações", "2E7D32"), ("Trocas", "2E7D32"), ("Ingressos", "2E7D32"), ("Despesas", "2E7D32"), ("Rateio", "2E7D32"), ("Clubes", "2E7D32"), ("FPF oficial", "2E7D32"),
                      ("Qualidade", "EF6C00"), ("Log", "EF6C00"), ("Correções", "EF6C00"), ("Dicionário", "757575"), ("Referência Python", "757575")):
        abas[nome] = wb.active if nome == "LEIA-ME" else wb.create_sheet(nome)
        abas[nome].title = nome
        abas[nome].sheet_properties.tabColor = cor

    # ---------- dados ----------
    partidas = []
    for p in sorted(t["fato_partida"], key=lambda x: int(x["numero_jogo"])):
        est = d["estadio"][p["id_estadio"]]
        partidas.append({"jogo": int(p["numero_jogo"]), "id": int(p["id_partida"]), "fase": d["fase"][p["id_fase"]], "rodada": int(p["rodada"]), "data": datetime.strptime(p["data_jogo"], "%Y-%m-%d"), "hora": p["hora_programada"],
                         "mand": d["clube"][p["id_clube_mandante"]], "vis": d["clube"][p["id_clube_visitante"]], "gm": int(p["gols_mandante"]), "gv": int(p["gols_visitante"]), "pm": num(p["penaltis_mandante"]), "pv": num(p["penaltis_visitante"]),
                         "estadio": est["nome_fpf"], "municipio": est["municipio"], "arbitro": d["arbitro"][p["id_arbitro"]], "publico": int(p["publico_boletim"]), "pagante": int(p["publico_pagante"]),
                         "bruta": num(p["renda_bruta"]), "despesas": num(p["despesas_total"]), "liquida": num(p["renda_liquida"]), "ac1": int(p["acrescimo_1t_min"]), "ac2": int(p["acrescimo_2t_min"])})
    fase_da_partida = {p["id_partida"]: d["fase"][p["id_fase"]] for p in t["fato_partida"]}
    jogo_da_partida = {p["id_partida"]: int(p["numero_jogo"]) for p in t["fato_partida"]}
    eventos = [{"id": e["id_evento"], "jogo": jogo_da_partida[e["id_partida"]], "fase": fase_da_partida[e["id_partida"]], "clube": d["clube"][e["id_clube"]], "tipo": e["tipo_evento"], "pessoa": e["pessoa"], "funcao": e["funcao"],
                "camisa": num(e["numero_camisa"]), "minuto": num(e["minuto"]), "acresc": num(e["acrescimo"]), "periodo": e["periodo"], "correcao": e["id_correcao"] or None, "fonte": e["fonte"]} for e in t["fato_evento"]]

    ws = abas["Partidas"]
    letra, p1, p2 = escrever_tabela(wb, ws, "tbl_partidas", "P", [
        Col("Jogo", "jogo", "0", 7, "jogo"), Col("ID FPF", "id", "0", 9), Col("Fase", "fase", None, 18, "fase"), Col("Rodada", "rodada", "0", 8), Col("Data", "data", FMT_DATA, 11), Col("Hora", "hora", None, 7),
        Col("Mandante", "mand", None, 20, "mand"), Col("Visitante", "vis", None, 20, "vis"), Col("Gols mandante", "gm", "0", 9, "gm"), Col("Gols visitante", "gv", "0", 9, "gv"), Col("Pênaltis mandante", "pm", "0", 9), Col("Pênaltis visitante", "pv", "0", 9),
        Col("Estádio", "estadio", None, 34), Col("Município", "municipio", None, 22), Col("Árbitro", "arbitro", None, 28), Col("Público (boletim)", "publico", FMT_INT, 11, "publico"), Col("Pagantes", "pagante", FMT_INT, 10, "pagante"),
        Col("Renda bruta", "bruta", FMT_DIN, 14, "bruta"), Col("Despesas", "despesas", FMT_DIN, 14, "despesas"), Col("Renda líquida", "liquida", FMT_DIN, 14, "liquida"), Col("Acréscimo 1º tempo (min)", "ac1", "0", 11), Col("Acréscimo 2º tempo (min)", "ac2", "0", 11),
        Col("Gols no jogo", "gols", "0", 9, "gols", lambda r, L: f"={L['gm']}{r}+{L['gv']}{r}"),
        Col("Resultado (M, E, V)", "res", None, 11, "res", lambda r, L: f'=IF({L["gm"]}{r}>{L["gv"]}{r},"M",IF({L["gm"]}{r}={L["gv"]}{r},"E","V"))'),
        Col("Acréscimo total (min)", "acresc", "0", 11, "acresc", lambda r, L: f"={L['ac1']}{r}+{L['ac2']}{r}")], partidas)
    ws.freeze_panes = "C2"

    ws = abas["Eventos"]
    escrever_tabela(wb, ws, "tbl_eventos", "E", [
        Col("Evento", "id", None, 12), Col("Jogo", "jogo", "0", 7, "jogo"), Col("Fase", "fase", None, 18, "fase"), Col("Clube", "clube", None, 20, "clube"), Col("Tipo", "tipo", None, 16, "tipo"), Col("Pessoa", "pessoa", None, 34, "pessoa"),
        Col("Função", "funcao", None, 16, "funcao"), Col("Camisa", "camisa", "0", 8), Col("Minuto", "minuto", "0", 8, "minuto"), Col("Acréscimo", "acresc", "0", 10), Col("Período", "periodo", None, 9), Col("Correção", "correcao", None, 10), Col("Fonte", "fonte", None, 9),
        Col("É gol (1/0)", "gol", "0", 10, "gol", lambda r, L: f'=IF(OR({L["tipo"]}{r}="gol",{L["tipo"]}{r}="gol_penalti",{L["tipo"]}{r}="gol_falta",{L["tipo"]}{r}="gol_contra"),1,0)')], eventos)
    ws.freeze_panes = "A2"

    ws = abas["Clubes"]
    clubes = sorted(t["dim_clube"], key=lambda c: c["nome_popular"])
    escrever_tabela(wb, ws, "tbl_clubes", "C", [Col("Escudo", "escudo", None, 9), Col("ID FPF", "id_clube", "0", 9), Col("Clube", "nome_popular", None, 22), Col("Nome oficial", "nome_oficial", None, 48), Col("Sigla", "sigla", None, 8), Col("Cor (hex)", "cor_hex", None, 11)],
                    [{**c, "id_clube": int(c["id_clube"]), "escudo": None} for c in clubes])
    for i, c in enumerate(clubes, 2):
        ws.row_dimensions[i].height = 34
        arq = PROC / c["arquivo_escudo"]
        if arq.exists():
            img = XLImage(str(arq))
            img.width = img.height = 32
            ws.add_image(img, f"A{i}")
        ws.cell(i, 6).fill = PatternFill("solid", fgColor=c["cor_hex"], bgColor=c["cor_hex"])

    ws = abas["FPF oficial"]
    oficial = [{"fase": o["fase"], "pos": int(o["posicao"]), "clube": d["clube"][o["id_clube"]], "pontos": int(o["pontos"]), "jogos": int(o["jogos"]), "v": int(o["vitorias"]), "e": int(o["empates"]), "d": int(o["derrotas"]), "gp": int(o["gols_pro"]),
                "gc": int(o["gols_contra"]), "sg": int(o["saldo"]), "vp": int(o["vp"]), "dp": int(o["dp"]), "ca": int(o["amarelos"]), "cv": int(o["vermelhos"])} for o in t["fato_classificacao_oficial"]]
    escrever_tabela(wb, ws, "tbl_fpf", "O", [
        Col("Fase", "fase", None, 18), Col("Pos.", "pos", "0", 6, "pos"), Col("Clube", "clube", None, 22), Col("Pontos", "pontos", "0", 8, "pontos"), Col("Jogos", "jogos", "0", 7, "jogos"), Col("V", "v", "0", 5, "v"), Col("E", "e", "0", 5, "e"), Col("D", "d", "0", 5, "d"),
        Col("Gols pró", "gp", "0", 8, "gp"), Col("Gols contra", "gc", "0", 10, "gc"), Col("Saldo", "sg", "0", 7, "sg"), Col("VP", "vp", "0", 5), Col("DP", "dp", "0", 5), Col("Amarelos", "ca", "0", 9, "ca"), Col("Vermelhos", "cv", "0", 10, "cv"),
        Col("Chave (fase|clube)", "chave", None, 34, "chave", lambda r, L: f'={L["fase"]}{r}&"|"&{L["clube"]}{r}')], oficial)
    abas["FPF oficial"]["R1"] = "Cópia da tabela oficial da FPF (captura do portal, 09/03/2026). Serve só para conferir a classificação refeita em Classificação."
    abas["FPF oficial"]["R1"].font = Font(italic=True, color=CINZA)

    # ---------- dados do financeiro e do elenco ----------
    mand_da_partida = {p["id_partida"]: d["clube"][p["id_clube_mandante"]] for p in t["fato_partida"]}
    vis_da_partida = {p["id_partida"]: d["clube"][p["id_clube_visitante"]] for p in t["fato_partida"]}
    nome_atleta = {a["id_atleta"]: a["nome"] for a in t["dim_atleta"]}

    ws = abas["Ingressos"]
    ingressos = [{"jogo": jogo_da_partida[i["id_partida"]], "fase": fase_da_partida[i["id_partida"]], "mand": mand_da_partida[i["id_partida"]], "vis": vis_da_partida[i["id_partida"]], "localidade": i["localidade"], "categoria": i["categoria"],
                  "setorvis": int(i["setor_visitante"]), "ingressos": int(i["ingressos"]), "preco": num(i["preco"]), "arrec": num(i["arrecadacao"])} for i in t["fato_ingresso"]]
    escrever_tabela(wb, ws, "tbl_ingressos", "IG", [
        Col("Jogo", "jogo", "0", 7, "jogo"), Col("Fase", "fase", None, 18, "fase"), Col("Mandante", "mand", None, 20, "mand"), Col("Visitante", "vis", None, 20, "vis"), Col("Localidade (rótulo do boletim)", "localidade", None, 46),
        Col("Categoria (projeto)", "categoria", None, 20, "categoria"), Col("Setor de visitante (1/0)", "setorvis", "0", 11, "setorvis"), Col("Ingressos", "ingressos", FMT_INT, 10, "ingressos"), Col("Preço", "preco", FMT_DIN, 10),
        Col("Arrecadação", "arrec", FMT_DIN, 14, "arrec")], ingressos)
    ws.freeze_panes = "A2"

    ws = abas["Despesas"]
    despesas = [{"jogo": jogo_da_partida[x["id_partida"]], "fase": fase_da_partida[x["id_partida"]], "bcod": x["bloco_codigo"], "bnome": x["bloco"], "rubrica": x["rubrica"], "grupo": x["grupo"], "valor": num(x["valor"])} for x in t["fato_despesa"]]
    escrever_tabela(wb, ws, "tbl_despesas", "DS", [
        Col("Jogo", "jogo", "0", 7, "jogo"), Col("Fase", "fase", None, 18, "fase"), Col("Bloco", "bcod", None, 8, "bloco"), Col("Nome do bloco", "bnome", None, 24), Col("Rubrica", "rubrica", None, 46), Col("Grupo (projeto)", "grupo", None, 26, "grupo"),
        Col("Valor", "valor", FMT_DIN, 14, "valor")], despesas)
    ws.freeze_panes = "A2"

    ws = abas["Rateio"]
    rateio = [{"jogo": jogo_da_partida[x["id_partida"]], "fase": fase_da_partida[x["id_partida"]], "clube": d["clube"][x["id_clube"]], "lado": x["lado"], "perc": num(x["percentual"]), "valor": num(x["valor"]), "inss": num(x["deducao_inss"]),
              "outras": num(x["deducao_outras"]), "liquido": num(x["liquido"])} for x in t["fato_rateio"]]
    escrever_tabela(wb, ws, "tbl_rateio", "RT", [
        Col("Jogo", "jogo", "0", 7, "jogo"), Col("Fase", "fase", None, 18, "fase"), Col("Clube", "clube", None, 20, "clube"), Col("Lado", "lado", None, 10), Col("Percentual", "perc", "0.00", 11), Col("Valor da divisão", "valor", FMT_DIN, 16, "valor"),
        Col("Dedução INSS", "inss", FMT_DIN, 14, "inss"), Col("Outras deduções", "outras", FMT_DIN, 14, "outras"), Col("Líquido a receber", "liquido", FMT_DIN, 16, "liquido")], rateio)
    ws.freeze_panes = "A2"

    ws = abas["Escalações"]
    elenco = [{"jogo": jogo_da_partida[e["id_partida"]], "fase": fase_da_partida[e["id_partida"]], "clube": d["clube"][e["id_clube"]], "atleta": nome_atleta[e["id_atleta"]], "camisa": int(e["numero_camisa"]), "situacao": e["situacao"],
               "vinculo": e["vinculo"], "jogou": int(e["jogou"]), "entrada": num(e["minuto_entrada"]), "saida": num(e["minuto_saida"]), "min": num(e["minutos_jogados"]), "gols": int(e["gols"]), "contra": int(e["gols_contra"]),
               "amarelos": int(e["amarelos"]), "vermelhos": int(e["vermelhos"])} for e in t["fato_escalacao"]]
    escrever_tabela(wb, ws, "tbl_elenco", "ES", [
        Col("Jogo", "jogo", "0", 7, "jogo"), Col("Fase", "fase", None, 18, "fase"), Col("Clube", "clube", None, 20, "clube"), Col("Atleta (nome na súmula)", "atleta", None, 36), Col("Camisa", "camisa", "0", 8), Col("Situação", "situacao", None, 10, "situacao"),
        Col("Vínculo", "vinculo", None, 12), Col("Jogou (1/0)", "jogou", "0", 10, "jogou"), Col("Minuto de entrada", "entrada", "0", 10), Col("Minuto de saída", "saida", "0", 10), Col("Minutos jogados", "min", "0", 10, "min"), Col("Gols", "gols", "0", 7, "gols"),
        Col("Gols contra", "contra", "0", 9, "contra"), Col("Amarelos", "amarelos", "0", 9, "amarelos"), Col("Vermelhos", "vermelhos", "0", 10, "vermelhos")], elenco)
    ws.freeze_panes = "A2"

    ws = abas["Trocas"]
    trocas = [{"jogo": jogo_da_partida[s["id_partida"]], "fase": fase_da_partida[s["id_partida"]], "clube": d["clube"][s["id_clube"]], "ordem": int(s["ordem"]), "tipo": s["tipo"], "saiu": nome_atleta.get(s["id_atleta_saiu"]),
               "num_saiu": num(s["numero_saiu"]), "entrou": nome_atleta.get(s["id_atleta_entrou"]), "num_entrou": num(s["numero_entrou"]), "periodo": s["periodo"], "minuto": num(s["minuto"])} for s in t["fato_substituicao"]]
    escrever_tabela(wb, ws, "tbl_trocas", "TR", [
        Col("Jogo", "jogo", "0", 7, "jogo"), Col("Fase", "fase", None, 18, "fase"), Col("Clube", "clube", None, 20, "clube"), Col("Ordem", "ordem", "0", 7), Col("Tipo", "tipo", None, 10, "tipo"), Col("Saiu (atleta)", "saiu", None, 36),
        Col("Camisa que saiu", "num_saiu", "0", 9), Col("Entrou (atleta)", "entrou", None, 36), Col("Camisa que entrou", "num_entrou", "0", 9), Col("Período", "periodo", None, 9), Col("Minuto", "minuto", "0", 8)], trocas)
    ws.freeze_panes = "A2"

    # ---------- referência Python ----------
    ws = abas["Referência Python"]
    ref = [{"busca": f"{r['id_indicador']}|{r['escopo']}|{r['chave']}|{r['id_clube']}", "id": r["id_indicador"], "indicador": r["indicador"], "escopo": r["escopo"], "chave": r["chave"], "id_clube": num(r["id_clube"]), "valor": num(r["valor"]), "unidade": r["unidade"]} for r in t["ref_indicadores"]]
    escrever_tabela(wb, ws, "tbl_ref", "R", [Col("Chave de busca (id|escopo|chave|id_clube)", "busca", None, 52, "busca"), Col("ID", "id", None, 7), Col("Indicador", "indicador", None, 34), Col("Escopo", "escopo", None, 13), Col("Chave", "chave", None, 34), Col("ID clube", "id_clube", "0", 9),
                                             Col("Valor (Python)", "valor", "#,##0.0000", 16, "valor"), Col("Unidade", "unidade", None, 14)], ref)
    ws.freeze_panes = "A2"

    # ---------- dicionário ----------
    ws = abas["Dicionário"]
    escrever_tabela(wb, ws, "tbl_dicionario", "D", [Col("ID", "i", None, 7), Col("Nome", "n", None, 28), Col("O que significa", "s", None, 46), Col("Como calcula", "c", None, 52), Col("De onde vem", "o", None, 26), Col("Escopos", "e", None, 9), Col("Valor geral (A1 2026)", "v", None, 24)],
                    [dict(zip("insceov", linha)) for linha in ler_dicionario()])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    abas["Dicionário"]["I1"] = "G = geral, F = por fase, C = por clube, M = faixa de minuto, A = artilheiro, Q = qualidade. Texto completo e cuidados em docs/dicionario_indicadores.md."
    abas["Dicionário"]["I1"].font = Font(italic=True, color=CINZA)

    # ---------- qualidade ----------
    ws = abas["Qualidade"]
    titulo(ws, "Qualidade dos dados", "Resultado das regras de conferência (scripts/regras.py). Cada ocorrência está na aba Log.")
    regras = [{"codigo": r["codigo"], "titulo": r["titulo"], "sev": r["severidade"], "verif": int(r["verificados"]), "oc": int(r["ocorrencias"]), "ab": int(r["abertas"]), "res": r["resultado"], "resumo": r["resumo"]} for r in t["resultado_regra"]]
    escrever_tabela(wb, ws, "tbl_regras", "Q", [Col("Código", "codigo", None, 9, "codigo"), Col("Verificação", "titulo", None, 105), Col("Severidade", "sev", None, 11), Col("Itens verificados", "verif", "0", 12), Col("Ocorrências", "oc", "0", 12), Col("Abertas", "ab", "0", 9),
                                              Col("Resultado", "res", None, 12, "resultado"), Col("Resumo", "resumo", None, 80)], regras, topo=11)
    ws["A4"], ws["A5"], ws["A6"], ws["A7"], ws["A8"] = "Regras executadas", "Regras sem ocorrência (ok)", "Regras com divergência explicada", "Regras com divergência aberta", "Regras só informativas"
    ws["D4"], ws["D5"], ws["D6"], ws["D7"], ws["D8"] = "=ROWS(Q_codigo)", '=COUNTIF(Q_resultado,"ok")', '=COUNTIF(Q_resultado,"explicada")', '=COUNTIF(Q_resultado,"aberta")', '=COUNTIF(Q_resultado,"info")'
    for r in range(4, 9):
        ws.cell(r, 4).font = Font(bold=True)
    colorir(ws, "G12:G200", {"ok": VERDE, "explicada": AMARELO, "aberta": VERMELHO, "info": NEUTRO})
    ws.freeze_panes = "A12"

    ws = abas["Log"]
    log = [{"id": l["id_inconsistencia"], "regra": l["codigo_regra"], "titulo": l["titulo_regra"], "jogo": num(l["numero_jogo"]), "clube": d["clube"].get(l["id_clube"]) if l["id_clube"] else None, "fa": l["fonte_a"], "va": l["valor_a"], "fb": l["fonte_b"], "vb": l["valor_b"],
            "detalhe": l["detalhe"] or None, "sev": l["severidade"], "status": l["status"], "expl": l["explicacao"] or None} for l in t["fato_inconsistencia"]]
    escrever_tabela(wb, ws, "tbl_log", "L", [Col("ID", "id", None, 10), Col("Regra", "regra", None, 7, "regra"), Col("Verificação", "titulo", None, 44), Col("Jogo", "jogo", "0", 6), Col("Clube", "clube", None, 18), Col("Fonte A", "fa", None, 14), Col("Valor A", "va", None, 22),
                                             Col("Fonte B", "fb", None, 14), Col("Valor B", "vb", None, 22), Col("Detalhe", "detalhe", None, 28), Col("Severidade", "sev", None, 11), Col("Status", "status", None, 11, "status"), Col("Explicação (decisão)", "expl", None, 90)], log)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    colorir(ws, "L2:L200", {"aberta": VERMELHO, "explicada": AMARELO, "corrigida": VERDE, "aceita": NEUTRO})
    ws.freeze_panes = "B2"

    ws = abas["Correções"]
    corr = ler_csv(RAIZ / "data" / "referencia" / "correcoes_dados.csv")
    escrever_tabela(wb, ws, "tbl_correcoes", "K", [Col("ID", "id_correcao", None, 8), Col("Jogo", "numero_jogo", "0", 6), Col("Evento", "tipo_evento", None, 10), Col("Pessoa", "pessoa", None, 30), Col("Campo", "campo", None, 9), Col("Valor original (súmula)", "valor_original", None, 14),
                                                  Col("Valor corrigido", "valor_corrigido", None, 12), Col("Fontes", "fontes", None, 60), Col("Justificativa", "justificativa", None, 90)], [{**c, "numero_jogo": int(c["numero_jogo"])} for c in corr])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws["A5"] = "O dado bruto da súmula nunca é alterado: a correção só vale na base tratada (coluna Correção da aba Eventos) e exige fonte e justificativa."
    ws["A5"].font = Font(italic=True, color=CINZA)

    # ---------- classificação ----------
    ws = abas["Classificação"]
    titulo(ws, "Classificação da primeira fase refeita em Excel", "Pontos, vitórias, saldo, gols marcados, menos vermelhos, menos amarelos (Art. 16). Conferida com a tabela oficial da FPF.")
    ws["A3"], ws["B3"] = "Fase:", FASE_CLASSIFICACAO
    ws["A3"].font = Font(bold=True)
    definir_nome(wb, "Par_fase", ws, "B", 3)
    nomes = sorted(d["clube"].values())
    topo_calc = 27
    ini, fim = topo_calc + 1, topo_calc + len(nomes)
    campos = ["n", "clube", "j", "v", "e", "d", "gp", "gc", "sg", "pts", "aprov", "ca", "cv", "chave", "pos", "empate", "pos_fpf", "linha", "ok"]
    rotulos = ["#", "Clube", "J", "V", "E", "D", "GP", "GC", "SG", "Pts", "Aproveit. %", "CA", "CV", "Chave Art. 16", "Posição", "Empate total?", "Posição FPF", "Linha na FPF", "Confere?"]
    L = {c: get_column_letter(i) for i, c in enumerate(campos, 1)}
    ws.cell(topo_calc - 1, 1, "Cálculo e conferência (ordem alfabética)").font = Font(size=12, bold=True, color=AZUL)
    for i, c in enumerate(rotulos, 1):
        h = ws.cell(topo_calc, i, c)
        h.font, h.fill, h.alignment = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=AZUL), Alignment(horizontal="center", wrap_text=True)
    for k, nome in enumerate(nomes):
        r = ini + k
        c = lambda campo: f"{L[campo]}{r}"
        mand, vis = f"P_fase,Par_fase,P_mand,${L['clube']}{r}", f"P_fase,Par_fase,P_vis,${L['clube']}{r}"
        ev = f"E_fase,Par_fase,E_clube,${L['clube']}{r}"
        chaves = f"${L['chave']}${ini}:${L['chave']}${fim}"
        confere = ",".join(f"{c(a)}=INDEX(O_{b},{c('linha')})" for a, b in (("j", "jogos"), ("v", "v"), ("e", "e"), ("d", "d"), ("gp", "gp"), ("gc", "gc"), ("sg", "sg"), ("pts", "pontos"), ("ca", "ca"), ("cv", "cv")))
        f = {
            "n": k + 1,
            "clube": nome,
            "j": f"=COUNTIFS({mand})+COUNTIFS({vis})",
            "v": f'=COUNTIFS({mand},P_res,"M")+COUNTIFS({vis},P_res,"V")',
            "e": f'=COUNTIFS({mand},P_res,"E")+COUNTIFS({vis},P_res,"E")',
            "d": f"={c('j')}-{c('v')}-{c('e')}",
            "gp": f"=SUMIFS(P_gm,{mand})+SUMIFS(P_gv,{vis})",
            "gc": f"=SUMIFS(P_gv,{mand})+SUMIFS(P_gm,{vis})",
            "sg": f"={c('gp')}-{c('gc')}",
            "pts": f"=3*{c('v')}+{c('e')}",
            "aprov": f"={c('pts')}/(3*{c('j')})*100",
            "ca": f'=COUNTIFS({ev},E_tipo,"amarelo")-COUNTIFS({ev},E_tipo,"segundo_amarelo")',
            "cv": f'=COUNTIFS({ev},E_tipo,"vermelho")+COUNTIFS({ev},E_tipo,"segundo_amarelo")',
            "chave": f"={c('pts')}*10^12+{c('v')}*10^10+({c('sg')}+100)*10^7+{c('gp')}*10^5+(99-{c('cv')})*10^3+(999-{c('ca')})",
            "pos": f'=COUNTIF({chaves},">"&{c("chave")})+COUNTIF(${L["chave"]}${ini}:{c("chave")},{c("chave")})',
            "empate": f'=IF(COUNTIF({chaves},{c("chave")})>1,"sim","não")',
            "pos_fpf": f"=INDEX(O_pos,{c('linha')})",
            "linha": f'=MATCH(Par_fase&"|"&{c("clube")},O_chave,0)',
            "ok": f'=IF(AND({confere},{c("pos")}={c("pos_fpf")}),"OK","DIVERGE")',
        }
        for campo, v in f.items():
            ws[c(campo)].value = v
        ws[c("aprov")].number_format = "0.00"
        ws[c("chave")].number_format = "0"
    for campo in ("clube", "pos", "pts", "j", "v", "e", "d", "gp", "gc", "sg", "aprov", "ca", "cv", "pos_fpf"):
        definir_nome(wb, f"X_{campo}", ws, L[campo], ini, fim)
    definir_nome(wb, "Conf_status_class", ws, L["ok"], ini, fim)
    colorir(ws, f"{L['ok']}{ini}:{L['ok']}{fim}", {"OK": VERDE, "DIVERGE": VERMELHO})
    # tabela ordenada por posição (o que se lê)
    cab_vis = ["Pos.", "Clube", "Pts", "J", "V", "E", "D", "GP", "GC", "SG", "Aproveit. %", "CA", "CV", "Posição FPF", "Confere?"]
    origem = ["clube", "pts", "j", "v", "e", "d", "gp", "gc", "sg", "aprov", "ca", "cv", "pos_fpf"]
    for i, c in enumerate(cab_vis, 1):
        h = ws.cell(5, i, c)
        h.font, h.fill, h.alignment = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=AZUL), Alignment(horizontal="center", wrap_text=True)
    for k in range(len(nomes)):
        r = 6 + k
        ws.cell(r, 1, k + 1)
        for i, o in enumerate(origem, 2):
            ws.cell(r, i, f"=INDEX(X_{o},MATCH($A{r},X_pos,0))")
        ws.cell(r, 11).number_format = "0.00"
        ws.cell(r, 15, f'=INDEX(${L["ok"]}${ini}:${L["ok"]}${fim},MATCH($A{r},X_pos,0))')
        if k < 8:
            for i in range(1, 16):
                ws.cell(r, i).fill = PatternFill("solid", fgColor="EAF2E3")
    colorir(ws, "O6:O21", {"OK": VERDE, "DIVERGE": VERMELHO})
    ws["A23"] = "Verde claro: os 8 primeiros (vão às quartas de final). Os dois últimos foram rebaixados."
    ws["A23"].font = Font(italic=True, color=CINZA)
    ws["A24"] = "Chave Art. 16 = pontos, vitórias, saldo (+100), gols pró, 99 − vermelhos, 999 − amarelos, cada um numa casa decimal própria; quanto maior a chave, melhor a posição. \"Empate total?\" = sim exigiria sorteio (nenhum caso em 2026)."
    ws["A24"].font = Font(italic=True, color=CINZA)
    for i, larg in enumerate([7, 24, 7, 7, 7, 7, 7, 7, 7, 7, 11, 7, 7, 18, 11, 12, 11, 11, 11], 1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    ws.freeze_panes = "A6"

    # ---------- artilharia ----------
    ws = abas["Artilharia"]
    titulo(ws, "Artilharia refeita em Excel", "Gols do atleta pelo próprio clube (gol de pênalti e de falta contam; gol contra não). Fonte: súmulas. Gols contados por fórmula sobre a aba Eventos.")
    art = [{"pessoa": r["chave"], "clube": d["clube"][r["id_clube"]], "py": num(r["valor"]), "busca": f"I33|artilheiro|{r['chave']}|{r['id_clube']}"} for r in t["ref_indicadores"] if r["escopo"] == "artilheiro"]
    letra, a1, a2 = escrever_tabela(wb, ws, "tbl_artilharia", "A", [
        Col("Pos.", "pos", "0", 6, None, lambda r, L: f"=RANK({L['x']}{r},${L['x']}$4:${L['x']}${3 + len(art)})"), Col("Jogador", "pessoa", None, 38), Col("Clube", "clube", None, 22),
        Col("Gols (Excel)", "x", "0", 12, None, lambda r, L: f'=COUNTIFS(E_pessoa,{L["pessoa"]}{r},E_clube,{L["clube"]}{r},E_tipo,"gol")+COUNTIFS(E_pessoa,{L["pessoa"]}{r},E_clube,{L["clube"]}{r},E_tipo,"gol_penalti")+COUNTIFS(E_pessoa,{L["pessoa"]}{r},E_clube,{L["clube"]}{r},E_tipo,"gol_falta")'),
        Col("Gols (Python)", "py", "0", 12), Col("Confere?", "ok", None, 11, None, lambda r, L: f'=IF({L["x"]}{r}={L["py"]}{r},"OK","DIVERGE")')], art, topo=3)
    definir_nome(wb, "Conf_status_art", ws, letra["ok"], a1, a2)
    colorir(ws, f"{letra['ok']}{a1}:{letra['ok']}{a2}", {"OK": VERDE, "DIVERGE": VERMELHO})
    ws.freeze_panes = "A4"

    # ---------- financeiro e elenco refeitos em Excel ----------
    un_ref = {(r["id_indicador"], r["escopo"], r["chave"]): r["unidade"] for r in t["ref_indicadores"]}
    fases_ord = [f["nome_fase"] for f in sorted(t["dim_fase"], key=lambda x: int(x["ordem"]))]
    clubes_ord = sorted(d["clube"].items(), key=lambda kv: kv[1])
    chaves_de = lambda ident, escopo: [r["chave"] for r in t["ref_indicadores"] if r["id_indicador"] == ident and r["escopo"] == escopo]
    CAB = ["ID", "Indicador", "Escopo", "Chave", "Excel (fórmula)", "Python", "Diferença", "Confere?", "Unidade", "Chave de busca"]

    def conferencias(ws, topo, itens, nome_status):
        for i, c in enumerate(CAB, 1):
            h = ws.cell(topo, i, c)
            h.font, h.fill, h.alignment = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=AZUL), Alignment(horizontal="center", wrap_text=True)
        pos = {(i, esc, ch): topo + 1 + k for k, (i, esc, ch, _, _) in enumerate(itens)}
        cel = lambda i, esc, ch: f"E{pos[(i, esc, ch)]}"
        for k, (i, esc, ch, id_clube, frm) in enumerate(itens):
            r = topo + 1 + k
            un = un_ref[(i, esc, ch)]
            ws.cell(r, 1, i)
            ws.cell(r, 2, ROTULOS[i])
            ws.cell(r, 3, esc)
            ws.cell(r, 4, ch or None)
            ws.cell(r, 5, frm(r, cel))
            ws.cell(r, 6, f"=INDEX(R_valor,MATCH(J{r},R_busca,0))")
            ws.cell(r, 7, f"=E{r}-F{r}")
            ws.cell(r, 8, f'=IF(ABS(G{r})<={tolerancia(un)},"OK","DIVERGE")')
            ws.cell(r, 9, un)
            ws.cell(r, 10, f"{i}|{esc}|{ch}|{id_clube}").font = Font(color=CINZA, size=8)
            for c in (5, 6):
                ws.cell(r, c).number_format = formato(un)
            ws.cell(r, 7).number_format = "0.0000"
        fim = topo + len(itens)
        definir_nome(wb, nome_status, ws, "H", topo + 1, fim)
        colorir(ws, f"H{topo + 1}:H{fim}", {"OK": VERDE, "DIVERGE": VERMELHO})
        return fim

    def cabecalho_de_tabela(ws, topo, titulos):
        for i, c in enumerate(titulos, 1):
            h = ws.cell(topo, i, c)
            h.font, h.fill, h.alignment = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=AZUL), Alignment(horizontal="center", wrap_text=True)

    ws = abas["Financeiro"]
    titulo(ws, "Financeiro refeito em Excel", "Despesas, ingressos, torcida visitante, divisão da renda e renda por clube, recalculados por fórmula sobre as abas Ingressos, Despesas, Rateio e Partidas. Categorias e grupos são classificação do projeto.")
    itens = []
    geral_f = {
        "I38": lambda r, c: "=SUM(DS_valor)", "I39": lambda r, c: f"={c('I38', 'geral', '')}/SUM(P_bruta)*100", "I40": lambda r, c: f"={c('I38', 'geral', '')}/SUM(P_publico)",
        "I41": lambda r, c: "=SUMIFS(IG_ingressos,IG_setorvis,1)", "I42": lambda r, c: f"={c('I41', 'geral', '')}/SUM(P_publico)*100", "I43": lambda r, c: "=SUM(RT_inss)+SUM(RT_outras)", "I44": lambda r, c: "=SUM(RT_liquido)"}
    itens += [(i, "geral", "", "", f) for i, f in geral_f.items()]
    for fase in fases_ord:
        fase_f = {
            "I38": lambda r, c: f"=SUMIFS(DS_valor,DS_fase,$D{r})",
            "I39": lambda r, c, fase=fase: f"={c('I38', 'fase', fase)}/SUMIFS(P_bruta,P_fase,$D{r})*100",
            "I40": lambda r, c, fase=fase: f"={c('I38', 'fase', fase)}/SUMIFS(P_publico,P_fase,$D{r})",
            "I41": lambda r, c: f"=SUMIFS(IG_ingressos,IG_fase,$D{r},IG_setorvis,1)",
            "I42": lambda r, c, fase=fase: f"={c('I41', 'fase', fase)}/SUMIFS(P_publico,P_fase,$D{r})*100",
            "I43": lambda r, c: f"=SUMIFS(RT_inss,RT_fase,$D{r})+SUMIFS(RT_outras,RT_fase,$D{r})",
            "I44": lambda r, c: f"=SUMIFS(RT_liquido,RT_fase,$D{r})"}
        itens += [(i, "fase", fase, "", fx) for i, fx in fase_f.items()]
    for cat in chaves_de("I45", "categoria"):
        cat_f = {
            "I45": lambda r, c: f"=SUMIFS(IG_ingressos,IG_categoria,$D{r})",
            "I46": lambda r, c: f"=SUMIFS(IG_arrec,IG_categoria,$D{r})",
            "I47": lambda r, c, cat=cat: f"={c('I46', 'categoria', cat)}/{c('I45', 'categoria', cat)}",
            "I48": lambda r, c, cat=cat: f"={c('I45', 'categoria', cat)}/SUM(IG_ingressos)*100",
            "I49": lambda r, c, cat=cat: f"={c('I46', 'categoria', cat)}/SUM(IG_arrec)*100"}
        itens += [(i, "categoria", cat, "", fx) for i, fx in cat_f.items()]
    for grupo in chaves_de("I38", "grupo_despesa"):
        itens.append(("I38", "grupo_despesa", grupo, "", lambda r, c: f"=SUMIFS(DS_valor,DS_grupo,$D{r})"))
        itens.append(("I50", "grupo_despesa", grupo, "", lambda r, c, grupo=grupo: f"={c('I38', 'grupo_despesa', grupo)}/SUM(DS_valor)*100"))
    for bloco in chaves_de("I38", "bloco"):
        itens.append(("I38", "bloco", bloco, "", lambda r, c: f"=SUMIFS(DS_valor,DS_bloco,$D{r})"))
        itens.append(("I50", "bloco", bloco, "", lambda r, c, bloco=bloco: f"={c('I38', 'bloco', bloco)}/SUM(DS_valor)*100"))
    for id_clube, nome in clubes_ord:
        itens += [("I44", "clube", nome, id_clube, lambda r, c: f"=SUMIFS(RT_liquido,RT_clube,$D{r})"), ("I51", "clube", nome, id_clube, lambda r, c: f"=SUMIFS(P_bruta,P_mand,$D{r})"),
                  ("I52", "clube", nome, id_clube, lambda r, c: f"=SUMIFS(P_liquida,P_mand,$D{r})"), ("I53", "clube", nome, id_clube, lambda r, c: f"=SUMIFS(IG_ingressos,IG_mand,$D{r},IG_setorvis,1)"),
                  ("I54", "clube", nome, id_clube, lambda r, c: f"=SUMIFS(IG_ingressos,IG_vis,$D{r},IG_setorvis,1)")]
    TOPO_F = 5
    fim_f = conferencias(ws, TOPO_F, itens, "Conf_status_fin")
    n_fin = len(itens)
    # jogo a jogo: as somas das linhas de ingresso, rubrica e divisão fecham com o boletim
    t0 = fim_f + 4
    ws.cell(t0 - 1, 1, "Jogo a jogo: as linhas do boletim (ingressos, rubricas e divisão da renda) fecham com o total de cada jogo").font = Font(size=12, bold=True, color=AZUL)
    cabecalho_de_tabela(ws, t0, ["Jogo", "Mandante", "Visitante", "Ingressos (soma das linhas)", "Público (boletim)", "Arrecadação (soma das linhas)", "Renda bruta", "Rubricas (soma)", "Despesas (boletim)", "Divisão da renda (soma)", "Renda líquida", "Confere?"])
    for k, p in enumerate(partidas):
        r = t0 + 1 + k
        ws.cell(r, 1, p["jogo"])
        ws.cell(r, 2, p["mand"])
        ws.cell(r, 3, p["vis"])
        ws.cell(r, 4, f"=SUMIFS(IG_ingressos,IG_jogo,$A{r})")
        ws.cell(r, 5, f"=INDEX(P_publico,MATCH($A{r},P_jogo,0))")
        ws.cell(r, 6, f"=SUMIFS(IG_arrec,IG_jogo,$A{r})")
        ws.cell(r, 7, f"=INDEX(P_bruta,MATCH($A{r},P_jogo,0))")
        ws.cell(r, 8, f"=SUMIFS(DS_valor,DS_jogo,$A{r})")
        ws.cell(r, 9, f"=INDEX(P_despesas,MATCH($A{r},P_jogo,0))")
        ws.cell(r, 10, f"=SUMIFS(RT_valor,RT_jogo,$A{r})")
        ws.cell(r, 11, f"=INDEX(P_liquida,MATCH($A{r},P_jogo,0))")
        ws.cell(r, 12, f'=IF(AND(D{r}=E{r},ABS(F{r}-G{r})<0.005,ABS(H{r}-I{r})<0.005,ABS(J{r}-K{r})<0.005),"OK","DIVERGE")')
        for c in (4, 5):
            ws.cell(r, c).number_format = FMT_INT
        for c in (6, 7, 8, 9, 10, 11):
            ws.cell(r, c).number_format = FMT_DIN
    fim_fj = t0 + len(partidas)
    definir_nome(wb, "Conf_status_fin_jogo", ws, "L", t0 + 1, fim_fj)
    colorir(ws, f"L{t0 + 1}:L{fim_fj}", {"OK": VERDE, "DIVERGE": VERMELHO})
    for i, larg in enumerate([7, 40, 22, 22, 18, 18, 18, 18, 18, 18, 18, 11], 1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    ws.freeze_panes = f"A{TOPO_F + 1}"

    ws = abas["Elenco"]
    titulo(ws, "Elenco refeito em Excel", "Titulares, reservas que entraram, trocas e gols de reserva, recalculados por fórmula sobre as abas Escalações, Trocas e Eventos. Fonte: relação de jogadores e substituições da súmula.")
    itens = []
    geral_e = {
        "I55": lambda r, c: "=COUNTIF(ES_jogou,1)", "I56": lambda r, c: '=COUNTIF(ES_situacao,"titular")', "I57": lambda r, c: '=COUNTIFS(ES_situacao,"reserva",ES_jogou,1)', "I58": lambda r, c: "=ROWS(TR_jogo)",
        "I59": lambda r, c: '=SUMIFS(ES_gols,ES_situacao,"reserva")'}
    itens += [(i, "geral", "", "", f) for i, f in geral_e.items()]
    for fase in fases_ord:
        fase_e = {
            "I55": lambda r, c: f"=COUNTIFS(ES_fase,$D{r},ES_jogou,1)", "I56": lambda r, c: f'=COUNTIFS(ES_fase,$D{r},ES_situacao,"titular")', "I57": lambda r, c: f'=COUNTIFS(ES_fase,$D{r},ES_situacao,"reserva",ES_jogou,1)',
            "I58": lambda r, c: f"=COUNTIF(TR_fase,$D{r})", "I59": lambda r, c: f'=SUMIFS(ES_gols,ES_fase,$D{r},ES_situacao,"reserva")'}
        itens += [(i, "fase", fase, "", fx) for i, fx in fase_e.items()]
    fim_e = conferencias(ws, 5, itens, "Conf_status_elenco")
    n_ele = len(itens)
    t1 = fim_e + 4
    ws.cell(t1 - 1, 1, "Time a time, jogo a jogo: 11 titulares, reservas que entraram = trocas, gols da relação = placar, cartões da relação = cartões dos eventos").font = Font(size=12, bold=True, color=AZUL)
    cabecalho_de_tabela(ws, t1, ["Jogo", "Clube", "Lado (M/V)", "Adversário", "Titulares", "Reservas que entraram", "Trocas", "Gols dos atletas", "Gols contra do adversário", "Gols no placar", "Amarelos (relação)", "Amarelos (eventos)",
                                 "Vermelhos (relação)", "Vermelhos (eventos)", "Confere?"])
    linha = t1
    for p in partidas:
        for lado, clube, adv in (("M", p["mand"], p["vis"]), ("V", p["vis"], p["mand"])):
            linha += 1
            r = linha
            ev = f'E_jogo,$A{r},E_clube,$B{r},E_funcao,"Atleta"'
            ws.cell(r, 1, p["jogo"])
            ws.cell(r, 2, clube)
            ws.cell(r, 3, lado)
            ws.cell(r, 4, adv)
            ws.cell(r, 5, f'=COUNTIFS(ES_jogo,$A{r},ES_clube,$B{r},ES_situacao,"titular")')
            ws.cell(r, 6, f'=COUNTIFS(ES_jogo,$A{r},ES_clube,$B{r},ES_situacao,"reserva",ES_jogou,1)')
            ws.cell(r, 7, f"=COUNTIFS(TR_jogo,$A{r},TR_clube,$B{r})")
            ws.cell(r, 8, f"=SUMIFS(ES_gols,ES_jogo,$A{r},ES_clube,$B{r})")
            ws.cell(r, 9, f"=SUMIFS(ES_contra,ES_jogo,$A{r},ES_clube,$D{r})")
            ws.cell(r, 10, f'=IF($C{r}="M",INDEX(P_gm,MATCH($A{r},P_jogo,0)),INDEX(P_gv,MATCH($A{r},P_jogo,0)))')
            ws.cell(r, 11, f"=SUMIFS(ES_amarelos,ES_jogo,$A{r},ES_clube,$B{r})")
            ws.cell(r, 12, f'=COUNTIFS({ev},E_tipo,"amarelo")-COUNTIFS({ev},E_tipo,"segundo_amarelo")')
            ws.cell(r, 13, f"=SUMIFS(ES_vermelhos,ES_jogo,$A{r},ES_clube,$B{r})")
            ws.cell(r, 14, f'=COUNTIFS({ev},E_tipo,"vermelho")+COUNTIFS({ev},E_tipo,"segundo_amarelo")')
            ws.cell(r, 15, f'=IF(AND(E{r}=11,F{r}=G{r},H{r}+I{r}=J{r},K{r}=L{r},M{r}=N{r}),"OK","DIVERGE")')
    fim_et = linha
    n_tj = fim_et - t1
    definir_nome(wb, "Conf_status_elenco_tj", ws, "O", t1 + 1, fim_et)
    colorir(ws, f"O{t1 + 1}:O{fim_et}", {"OK": VERDE, "DIVERGE": VERMELHO})
    for i, larg in enumerate([7, 40, 22, 22, 18, 18, 12, 18, 18, 14, 14, 14, 14, 14, 11], 1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    ws.freeze_panes = "A6"

    # ---------- resumo ----------
    ws = abas["Resumo"]
    titulo(ws, "Conferência Excel × Python: Paulistão A1 2026", "Cada linha recalcula um indicador por fórmula de Excel (coluna Excel) e compara com o valor calculado pelo Python (coluna Python).")
    cab = ["ID", "Indicador", "Escopo", "Chave", "Excel (fórmula)", "Python", "Diferença", "Confere?", "Unidade", "Chave de busca"]
    TOPO = 11
    for i, c in enumerate(cab, 1):
        h = ws.cell(TOPO, i, c)
        h.font, h.fill, h.alignment = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=AZUL), Alignment(horizontal="center", wrap_text=True)
    unidade = {(r["id_indicador"], r["escopo"], r["chave"]): r["unidade"] for r in t["ref_indicadores"]}
    linhas = [(i, "geral", "") for i in GERAIS] + [("I24", "faixa_minuto", f[0]) for f in FAIXAS]
    fases = [f["nome_fase"] for f in sorted(t["dim_fase"], key=lambda x: int(x["ordem"]))]
    linhas += [(i, "fase", fase) for fase in fases for i in POR_FASE] + [(i, "qualidade", "") for i in QUALIDADE]
    linha_geral = {i: TOPO + 1 + k for k, (i, esc, _) in enumerate(linhas) if esc == "geral"}
    E = lambda i: f"E{linha_geral[i]}"
    geral = {"I01": "=ROWS(P_gols)", "I02": "=SUM(P_gols)", "I03": f"={E('I02')}/{E('I01')}", "I04": '=COUNTIF(P_res,"M")', "I05": '=COUNTIF(P_res,"E")', "I06": '=COUNTIF(P_res,"V")',
             "I07": f"={E('I04')}/{E('I01')}*100", "I08": f"={E('I05')}/{E('I01')}*100", "I09": f"={E('I06')}/{E('I01')}*100", "I10": "=SUM(P_publico)", "I11": "=AVERAGE(P_publico)", "I12": "=MAX(P_publico)", "I13": "=MIN(P_publico)",
             "I14": "=SUM(P_pagante)", "I15": f"={E('I14')}/{E('I10')}*100", "I16": "=SUM(P_bruta)", "I17": "=SUM(P_liquida)", "I18": f"={E('I16')}/{E('I14')}", "I19": '=COUNTIF(P_liquida,"<0")',
             "I20": '=COUNTIF(E_tipo,"amarelo")-COUNTIF(E_tipo,"segundo_amarelo")', "I21": '=COUNTIF(E_tipo,"vermelho")+COUNTIF(E_tipo,"segundo_amarelo")', "I22": f"=({E('I20')}+{E('I21')})/{E('I01')}",
             "I23": "=AVERAGE(P_acresc)", "I25": '=COUNTIF(E_tipo,"gol_penalti")', "I26": "=COUNTIF(P_gols,0)"}
    qual = {"I34": "=ROWS(Q_codigo)", "I35": '=COUNTIF(Q_resultado,"ok")', "I36": '=COUNTIF(L_status,"aberta")', "I37": '=COUNTIF(L_status,"explicada")+COUNTIF(L_status,"aceita")+COUNTIF(L_status,"corrigida")'}
    por_fase = {"I01": "=COUNTIF(P_fase,$D{r})", "I02": "=SUMIF(P_fase,$D{r},P_gols)", "I03": "=SUMIF(P_fase,$D{r},P_gols)/COUNTIF(P_fase,$D{r})", "I10": "=SUMIF(P_fase,$D{r},P_publico)", "I11": "=AVERAGEIF(P_fase,$D{r},P_publico)",
                "I16": "=SUMIF(P_fase,$D{r},P_bruta)", "I17": "=SUMIF(P_fase,$D{r},P_liquida)", "I20": '=COUNTIFS(E_fase,$D{r},E_tipo,"amarelo")-COUNTIFS(E_fase,$D{r},E_tipo,"segundo_amarelo")',
                "I21": '=COUNTIFS(E_fase,$D{r},E_tipo,"vermelho")+COUNTIFS(E_fase,$D{r},E_tipo,"segundo_amarelo")'}
    limites = {f[0]: (f[1], f[2]) for f in FAIXAS}
    for k, (i, esc, chave) in enumerate(linhas):
        r = TOPO + 1 + k
        un = unidade[(i, esc, chave)]
        if esc == "geral":
            frm = geral[i]
        elif esc == "faixa_minuto":
            a, b = limites[chave]
            frm = f'=COUNTIFS(E_gol,1,E_minuto,">="&{a},E_minuto,"<="&{b})'
        elif esc == "fase":
            frm = por_fase[i].format(r=r)
        else:
            frm = qual[i]
        rotulo = ROTULOS[i] + (f" {chave}" if esc == "faixa_minuto" else "")
        ws.cell(r, 1, i)
        ws.cell(r, 2, rotulo)
        ws.cell(r, 3, esc)
        ws.cell(r, 4, chave or None)
        ws.cell(r, 5, frm)
        ws.cell(r, 6, f"=INDEX(R_valor,MATCH(J{r},R_busca,0))")
        ws.cell(r, 7, f"=E{r}-F{r}")
        ws.cell(r, 8, f'=IF(ABS(G{r})<={tolerancia(un)},"OK","DIVERGE")')
        ws.cell(r, 9, un)
        ws.cell(r, 10, f"{i}|{esc}|{chave}|").font = Font(color=CINZA, size=8)
        for c in (5, 6):
            ws.cell(r, c).number_format = formato(un)
        ws.cell(r, 7).number_format = "0.0000"
    fim_r = TOPO + len(linhas)
    definir_nome(wb, "Conf_status_resumo", ws, "H", TOPO + 1, fim_r)
    colorir(ws, f"H{TOPO + 1}:H{fim_r}", {"OK": VERDE, "DIVERGE": VERMELHO})
    nomes_status = ["Conf_status_resumo", "Conf_status_class", "Conf_status_art", "Conf_status_fin", "Conf_status_fin_jogo", "Conf_status_elenco", "Conf_status_elenco_tj"]
    total = "+".join(f"ROWS({n})" for n in nomes_status)
    ok = "(" + "+".join(f'COUNTIF({n},"OK")' for n in nomes_status) + ")"
    ws["A4"], ws["A5"], ws["A6"], ws["A7"] = "Conferências feitas", "Conferências em que Excel e Python concordam", "Divergências", "Resultado"
    ws["E4"], ws["E5"], ws["E6"] = f"={total}", f"={ok}", "=E4-E5"
    ws["E7"] = '=IF(E6=0,"TUDO CONFERE","HÁ DIVERGÊNCIA")'
    definir_nome(wb, "Conf_total", ws, "E", 4)
    definir_nome(wb, "Conf_ok", ws, "E", 5)
    for r in range(4, 8):
        ws.cell(r, 1).font = Font(bold=True)
        ws.cell(r, 5).font = Font(bold=True, size=12)
    colorir(ws, "E7", {"TUDO CONFERE": VERDE, "HÁ DIVERGÊNCIA": VERMELHO})
    ws["A8"] = "Conferências = esta tabela + a Classificação (16 clubes) + a Artilharia (jogadores) + as abas Financeiro e Elenco (indicadores I38 a I59 e jogo a jogo). Tolerância: contagens e dinheiro exatos (dinheiro até meio centavo); médias e percentuais até 0,00006 (o Python guarda 4 casas)."
    ws["A8"].font = Font(italic=True, color=CINZA)
    for i, larg in enumerate([7, 46, 14, 22, 18, 18, 12, 11, 14, 36], 1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    ws.freeze_panes = f"A{TOPO + 1}"

    # ---------- leia-me ----------
    ws = abas["LEIA-ME"]
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 110
    ws["A1"] = "Paulista Analytics: planilha de conferência do Paulistão A1 2026"
    ws["A1"].font = Font(size=18, bold=True, color=AZUL)
    ws["A2"] = "Projeto independente de portfólio, sem vínculo com a Federação Paulista de Futebol nem com a ESPN. Dados públicos; os escudos pertencem aos clubes."
    ws["A2"].font = Font(italic=True, color=CINZA)
    texto = [
        ("Para que serve", "Provar que os números do dashboard estão certos por dois caminhos. Cada indicador é recalculado aqui por fórmula de Excel, a partir das abas de dados, e comparado com o valor que o Python calculou. Se os dois concordam, a linha mostra OK."),
        ("Comece por", "A aba Resumo: no topo diz quantas conferências foram feitas e se tudo confere. Depois veja a Classificação (refeita pelo desempate do Art. 16 e comparada com a tabela oficial), a Artilharia, o Financeiro (ingressos, despesas e divisão da renda, jogo a jogo e por clube) e o Elenco (titulares, trocas, gols e cartões da relação de jogadores)."),
        ("Abas azuis", "LEIA-ME, Resumo, Classificação, Artilharia, Financeiro e Elenco: o que se lê e confere."),
        ("Abas verdes", "Partidas, Eventos, Escalações, Trocas, Ingressos, Despesas, Rateio, Clubes e FPF oficial: os dados. Têm filtros. Só as colunas \"Gols no jogo\", \"Resultado\", \"Acréscimo total\" e \"É gol\" são fórmulas."),
        ("Abas laranja", f"Qualidade (as {len(regras)} regras de conferência), Log (cada divergência encontrada, com a decisão tomada) e Correções (o que foi corrigido na base, com a fonte)."),
        ("Abas cinza", "Dicionário (o que cada indicador significa) e Referência Python (os valores que o Python calculou)."),
        ("Cores", "Verde = confere. Vermelho = diverge ou aberta. Amarelo = divergência explicada. Cinza = informativo ou aceita."),
        ("De onde vêm os dados", "Tabela de jogos, classificação, súmulas e boletins financeiros oficiais da FPF (placar, gols, cartões, público, renda, arbitragem). A ESPN entra só como segunda opinião nas regras de conferência e nas 15 cobranças da disputa de pênaltis (o placar da disputa, 7 × 8, é o da súmula)."),
        ("Divergências abertas", "Duas, documentadas na aba Log: capacidade dos estádios sem fonte (não há taxa de ocupação) e súmula do jogo 47 com os horários dos tempos zerados."),
        ("Uma correção", "No jogo 15 o 3º gol está aos 60' na súmula e aos 76'-77' em duas reportagens e na ESPN; a base usa 76' (aba Correções). A súmula original não é alterada."),
        ("Como atualizar", "python scripts/06_exportar.py  e depois  python scripts/verificar_excel.py --salvar  (recalcula no Excel, confere e grava os valores)."),
        ("Gerada em", datetime.now().strftime("%d/%m/%Y")),
    ]
    for k, (a, b) in enumerate(texto):
        r = 4 + k
        ws.cell(r, 1, a).font = Font(bold=True, color=AZUL)
        ws.cell(r, 2, b).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 1).alignment = Alignment(vertical="top")

    for a in abas.values():
        a.sheet_view.showGridLines = a.title in ("Partidas", "Eventos", "Escalações", "Trocas", "Ingressos", "Despesas", "Rateio", "Clubes", "FPF oficial", "Qualidade", "Log", "Correções", "Dicionário", "Referência Python", "Artilharia")
        a.page_setup.orientation = "landscape"
        a.page_setup.fitToWidth = 1
        a.page_setup.fitToHeight = 0
        a.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        a.sheet_view.tabSelected = a.title == "Resumo"
    wb.active = 1
    wb.calculation.fullCalcOnLoad = True
    wb.properties.title = "Paulista Analytics: conferência do Paulistão A1 2026"
    wb.properties.creator = "Paulista Analytics (projeto independente)"
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return {"arquivo": destino, "conferencias": len(linhas) + len(nomes) + len(art) + n_fin + len(partidas) + n_ele + n_tj, "abas": list(abas)}


if __name__ == "__main__":
    saida = Path(sys.argv[sys.argv.index("--saida") + 1]) if "--saida" in sys.argv else SAIDA
    r = construir(saida)
    print(f"gerado: {r['arquivo']}  | {len(r['abas'])} abas | {r['conferencias']} conferências por fórmula")
