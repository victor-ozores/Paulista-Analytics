"""Define as medidas DAX do modelo (fonte única), gera o JSON do MCP, a conferência e a documentação.

As medidas ficam na tabela `_Medidas`, em pastas numeradas. Cada uma reproduz um indicador de
`docs/dicionario_indicadores.md` (I01 a I59) ou apoia a classificação pelo Art. 16.

Modos:
  python scripts/10_gerar_medidas.py             escreve docs/medidas_dax.md
  python scripts/10_gerar_medidas.py --escrever-tmdl   reescreve a tabela _Medidas do projeto PBIP a partir da lista M (recusa com o Power BI Desktop aberto; mantém os lineageTag existentes)
  python scripts/10_gerar_medidas.py --json      imprime as definições (MCP: measure_operations Create)
  python scripts/10_gerar_medidas.py --json-descricoes   imprime só as descrições completas (MCP: measure_operations Update, sem mexer em mais nada)
  python scripts/10_gerar_medidas.py --query     imprime a consulta DAX que calcula, com as medidas do modelo, as 586 linhas do gabarito
  python scripts/10_gerar_medidas.py --comparar ARQUIVO.csv    compara o resultado da consulta com o gabarito

Percentuais: as medidas devolvem fração (0,47 = 47%) com formato de porcentagem; o gabarito (`ref_indicadores`) usa 0 a 100.
"""
import csv
import json
import re
import subprocess
import sys
import uuid

from comum import RAIZ

DOC = RAIZ / "docs" / "medidas_dax.md"
TMDL = RAIZ / "powerbi" / "PaulistaAnalytics.SemanticModel" / "definition" / "tables" / "_Medidas.tmdl"
NS_TAG = uuid.UUID("5f0c1e1a-7e57-4c0a-9a55-0a1a6b1e0003")
TABELA = "_Medidas"
MAND = "USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube])"
VIS = "USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube])"
PRIMEIRA = 'dim_fase[nome_fase] = "PRIMEIRA FASE"'
GOLS_TIPOS = '{"gol", "gol_penalti", "gol_falta", "gol_contra"}'
F_INT, F_DEC, F_PCT, F_DIN = "#,0", "#,0.00", "0.0%", '"R$" #,0.00'
F_CHAVE = "0"

# (pasta, nome, expressão DAX, formato, indicador(es), descrição)
M = [
    ("01 Resultados", "Jogos", "COUNTROWS(fato_partida)", F_INT, "I01", "Quantos jogos."),
    ("01 Resultados", "Gols", "SUM(fato_partida[gols_mandante]) + SUM(fato_partida[gols_visitante])", F_INT, "I02", "Gols do placar (inclui pênalti, falta e gol contra; sem a disputa de pênaltis)."),
    ("01 Resultados", "Gols por jogo", "DIVIDE([Gols], [Jogos])", F_DEC, "I03", "Média de gols por jogo."),
    ("01 Resultados", "Vitórias do mandante", "COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] > fato_partida[gols_visitante]))", F_INT, "I04", "Jogos em que o mandante fez mais gols no tempo regulamentar."),
    ("01 Resultados", "Empates", "COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] = fato_partida[gols_visitante]))", F_INT, "I05", "Jogos empatados no tempo regulamentar (o decidido nos pênaltis conta como empate)."),
    ("01 Resultados", "Vitórias do visitante", "COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] < fato_partida[gols_visitante]))", F_INT, "I06", "Jogos em que o visitante fez mais gols no tempo regulamentar."),
    ("01 Resultados", "% vitórias do mandante", "DIVIDE([Vitórias do mandante], [Jogos])", F_PCT, "I07", "Vitórias do mandante sobre o total de jogos."),
    ("01 Resultados", "% empates", "DIVIDE([Empates], [Jogos])", F_PCT, "I08", "Empates sobre o total de jogos."),
    ("01 Resultados", "% vitórias do visitante", "DIVIDE([Vitórias do visitante], [Jogos])", F_PCT, "I09", "Vitórias do visitante sobre o total de jogos."),
    ("01 Resultados", "Jogos sem gols", "COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] + fato_partida[gols_visitante] = 0))", F_INT, "I26", "Jogos 0 x 0."),
    ("02 Gols e tempo", "Gols de pênalti", 'CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "gol_penalti")', F_INT, "I25", "Gols de pênalti durante o jogo."),
    ("02 Gols e tempo", "Acréscimo médio (min)", "AVERAGEX(fato_partida, fato_partida[acrescimo_1t_min] + fato_partida[acrescimo_2t_min])", F_DEC, "I23", "Minutos de acréscimo por jogo (1º mais 2º tempo), pela súmula."),
] + [
    (r"02 Gols e tempo\Faixas de minuto", f"Gols {nome}", f"CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {GOLS_TIPOS}, fato_evento[minuto] >= {a}, fato_evento[minuto] <= {b})", F_INT, "I24", f"Gols entre os minutos {nome} (o acréscimo fica na última faixa do tempo).")
    for nome, a, b in (("01-15", 0, 15), ("16-30", 16, 30), ("31-45", 31, 45), ("46-60", 46, 60), ("61-75", 61, 75), ("76-90+", 76, 999))
] + [
    ("03 Público e renda", "Público total", "SUM(fato_partida[publico_boletim])", F_INT, "I10", "Ingressos vendidos (boletim financeiro)."),
    ("03 Público e renda", "Público médio", "DIVIDE([Público total], [Jogos])", F_DEC, "I11", "Público médio por jogo."),
    ("03 Público e renda", "Maior público", "MAX(fato_partida[publico_boletim])", F_INT, "I12", "Maior público de um jogo."),
    ("03 Público e renda", "Menor público", "MIN(fato_partida[publico_boletim])", F_INT, "I13", "Menor público de um jogo."),
    ("03 Público e renda", "Público pagante", "SUM(fato_partida[publico_pagante])", F_INT, "I14", "Pessoas que pagaram ingresso."),
    ("03 Público e renda", "% de pagantes", "DIVIDE([Público pagante], [Público total])", F_PCT, "I15", "Parte do público que pagou."),
    ("03 Público e renda", "Renda bruta", "SUM(fato_partida[renda_bruta])", F_DIN, "I16", "Arrecadação de ingressos antes das despesas."),
    ("03 Público e renda", "Renda líquida", "SUM(fato_partida[renda_liquida])", F_DIN, "I17", "Renda bruta menos as despesas do jogo (pode ser negativa)."),
    ("03 Público e renda", "Ticket médio", "DIVIDE([Renda bruta], [Público pagante])", F_DIN, "I18", "Renda bruta dividida pelo público pagante."),
    ("03 Público e renda", "Jogos com renda líquida negativa", "COUNTROWS(FILTER(fato_partida, fato_partida[renda_liquida] < 0))", F_INT, "I19", "Jogos em que as despesas passaram da arrecadação."),
    ("04 Disciplina", "Amarelos", 'CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "amarelo") - CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "segundo_amarelo")', F_INT, "I20", "Regra da FPF: todas as advertências (atletas e comissão) menos os segundos amarelos."),
    ("04 Disciplina", "Vermelhos", 'CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "vermelho") + CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "segundo_amarelo")', F_INT, "I21", "Regra da FPF: vermelhos diretos mais as expulsões por segundo amarelo."),
    ("04 Disciplina", "Cartões por jogo", "DIVIDE([Amarelos] + [Vermelhos], [Jogos])", F_DEC, "I22", "Amarelos mais vermelhos por jogo."),
    ("05 Clube", "Jogos do clube", f"CALCULATE(COUNTROWS(fato_partida), {MAND}) + CALCULATE(COUNTROWS(fato_partida), {VIS})", F_INT, "I01", "Jogos do clube selecionado, como mandante ou visitante."),
    ("05 Clube", "Gols pró", f"CALCULATE(SUM(fato_partida[gols_mandante]), {MAND}) + CALCULATE(SUM(fato_partida[gols_visitante]), {VIS})", F_INT, "I27", "Gols que o clube fez."),
    ("05 Clube", "Gols contra", f"CALCULATE(SUM(fato_partida[gols_visitante]), {MAND}) + CALCULATE(SUM(fato_partida[gols_mandante]), {VIS})", F_INT, "I28", "Gols que o clube levou."),
    ("05 Clube", "Pontos", f"CALCULATE(SUMX(fato_partida, SWITCH(TRUE(), fato_partida[gols_mandante] > fato_partida[gols_visitante], 3, fato_partida[gols_mandante] = fato_partida[gols_visitante], 1, 0)), {MAND}) + CALCULATE(SUMX(fato_partida, SWITCH(TRUE(), fato_partida[gols_visitante] > fato_partida[gols_mandante], 3, fato_partida[gols_mandante] = fato_partida[gols_visitante], 1, 0)), {VIS})", F_INT, "", "Pontos do clube nos jogos do contexto (3 por vitória, 1 por empate no tempo regulamentar)."),
    ("05 Clube", "Pontos 1ª fase", f"CALCULATE([Pontos], {PRIMEIRA})", F_INT, "I29", "Pontos do clube na primeira fase."),
    ("05 Clube", "Aproveitamento 1ª fase", f"DIVIDE([Pontos 1ª fase], 3 * CALCULATE([Jogos do clube], {PRIMEIRA}))", F_PCT, "I30", "Pontos conquistados sobre os disputados na primeira fase."),
    ("05 Clube", "Público médio como mandante", f"CALCULATE(AVERAGE(fato_partida[publico_boletim]), {MAND})", F_DEC, "I32", "Público médio dos jogos em que o clube foi mandante."),
    ("06 Classificação (Art. 16)", "Vitórias 1ª fase", f"CALCULATE(COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] > fato_partida[gols_visitante])), {MAND}, {PRIMEIRA}) + CALCULATE(COUNTROWS(FILTER(fato_partida, fato_partida[gols_visitante] > fato_partida[gols_mandante])), {VIS}, {PRIMEIRA})", F_INT, "", "Vitórias do clube na primeira fase."),
    ("06 Classificação (Art. 16)", "Gols pró 1ª fase", f"CALCULATE([Gols pró], {PRIMEIRA})", F_INT, "", "Gols marcados na primeira fase."),
    ("06 Classificação (Art. 16)", "Saldo 1ª fase", f"[Gols pró 1ª fase] - CALCULATE([Gols contra], {PRIMEIRA})", F_INT, "", "Saldo de gols na primeira fase."),
    ("06 Classificação (Art. 16)", "Amarelos 1ª fase", f"CALCULATE([Amarelos], {PRIMEIRA})", F_INT, "", "Amarelos do clube na primeira fase (regra da FPF)."),
    ("06 Classificação (Art. 16)", "Vermelhos 1ª fase", f"CALCULATE([Vermelhos], {PRIMEIRA})", F_INT, "", "Vermelhos do clube na primeira fase (regra da FPF)."),
    ("06 Classificação (Art. 16)", "Chave Art. 16", "[Pontos 1ª fase] * 10^12 + [Vitórias 1ª fase] * 10^10 + ([Saldo 1ª fase] + 100) * 10^7 + [Gols pró 1ª fase] * 10^5 + (99 - [Vermelhos 1ª fase]) * 10^3 + (999 - [Amarelos 1ª fase])", F_CHAVE, "", "Número que ordena a primeira fase pelo Art. 16: pontos, vitórias, saldo, gols marcados, menos vermelhos, menos amarelos (cada critério numa casa própria; maior é melhor)."),
    ("06 Classificação (Art. 16)", "Posição 1ª fase", "RANKX(ALL(dim_clube), [Chave Art. 16], , DESC, SKIP)", F_INT, "I31", "Posição do clube na primeira fase pelo desempate do Art. 16."),
    ("07 Artilharia", "Gols do atleta", 'CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta"})', F_INT, "I33", "Gols do atleta pelo próprio clube (gol de pênalti e de falta contam; gol contra não)."),
    ("08 Qualidade dos dados", "Regras executadas", "COUNTROWS(resultado_regra)", F_INT, "I34", "Regras de conferência que rodaram."),
    ("08 Qualidade dos dados", "Regras sem ocorrência", 'COUNTROWS(FILTER(resultado_regra, resultado_regra[resultado] = "ok"))', F_INT, "I35", "Regras em que as fontes concordam por completo."),
    ("08 Qualidade dos dados", "Inconsistências abertas", 'CALCULATE(COUNTROWS(fato_inconsistencia), fato_inconsistencia[status] = "aberta")', F_INT, "I36", "Divergências ainda sem solução."),
    ("08 Qualidade dos dados", "Inconsistências explicadas", 'CALCULATE(COUNTROWS(fato_inconsistencia), fato_inconsistencia[status] IN {"explicada", "aceita", "corrigida"})', F_INT, "I37", "Divergências com causa conhecida e decisão registrada (explicadas, aceitas ou corrigidas)."),
    ("09 Financeiro", "Despesas", "SUM(fato_despesa[valor])", F_DIN, "I38", "Despesas dos jogos: soma das rubricas dos blocos B1, B2 e B3 do boletim. Com um grupo de despesa ou um bloco filtrado, só o que é dele."),
    ("09 Financeiro", "% despesas sobre renda bruta", "DIVIDE([Despesas], [Renda bruta])", F_PCT, "I39", "Quanto da arrecadação foi gasto em despesas."),
    ("09 Financeiro", "Despesa por ingresso", "DIVIDE([Despesas], [Público total])", F_DIN, "I40", "Despesa média por ingresso vendido."),
    ("09 Financeiro", "Ingressos em setor de visitante", "CALCULATE(SUM(fato_ingresso[ingressos]), fato_ingresso[setor_visitante] = 1)", F_INT, "I41", "Ingressos vendidos em setores cujo nome cita visitante (estimativa pelo nome do setor)."),
    ("09 Financeiro", "% torcida visitante", "DIVIDE([Ingressos em setor de visitante], [Público total])", F_PCT, "I42", "Parte do público que está em setor de visitante."),
    ("09 Financeiro", "Deduções", "SUM(fato_rateio[deducao_inss]) + SUM(fato_rateio[deducao_outras])", F_DIN, "I43", "Descontos que o boletim aplica sobre a parte de cada clube na divisão da renda líquida (INSS e outras)."),
    ("09 Financeiro", "Líquido a receber", "SUM(fato_rateio[liquido])", F_DIN, "I44", "O que o clube recebe da renda líquida depois das deduções (em 2026 o mandante fica com 100% e o visitante com 0%)."),
    ("09 Financeiro", "Ingressos vendidos", "SUM(fato_ingresso[ingressos])", F_INT, "I45", "Ingressos vendidos, somando as linhas do boletim; com uma categoria filtrada, os dela."),
    ("09 Financeiro", "Arrecadação dos ingressos", "SUM(fato_ingresso[arrecadacao])", F_DIN, "I46", "Dinheiro arrecadado pelas linhas de ingresso; com uma categoria filtrada, o dela."),
    ("09 Financeiro", "Preço médio por ingresso", "DIVIDE([Arrecadação dos ingressos], [Ingressos vendidos])", F_DIN, "I47", "Quanto cada ingresso rendeu, em média (a gratuidade por lei não tem preço: zero)."),
    ("09 Financeiro", "% dos ingressos", "DIVIDE([Ingressos vendidos], CALCULATE([Ingressos vendidos], ALL(fato_ingresso[categoria])))", F_PCT, "I48", "Parte dos ingressos vendidos que é da categoria filtrada."),
    ("09 Financeiro", "% da arrecadação", "DIVIDE([Arrecadação dos ingressos], CALCULATE([Arrecadação dos ingressos], ALL(fato_ingresso[categoria])))", F_PCT, "I49", "Parte da arrecadação que é da categoria filtrada."),
    ("09 Financeiro", "% das despesas", "DIVIDE([Despesas], CALCULATE([Despesas], ALL(fato_despesa[grupo]), ALL(fato_despesa[bloco_codigo])))", F_PCT, "I50", "Parte das despesas que é do grupo de despesa ou do bloco filtrado."),
    (r"09 Financeiro\Clube", "Renda bruta como mandante", f"CALCULATE([Renda bruta], {MAND})", F_DIN, "I51", "Arrecadação dos jogos em que o clube foi mandante (a renda do jogo é do mandante)."),
    (r"09 Financeiro\Clube", "Renda líquida como mandante", f"CALCULATE([Renda líquida], {MAND})", F_DIN, "I52", "Renda líquida dos jogos em que o clube foi mandante (pode ser negativa)."),
    (r"09 Financeiro\Clube", "Torcida visitante recebida", f"CALCULATE([Ingressos em setor de visitante], {MAND})", F_INT, "I53", "Ingressos em setor de visitante vendidos nos jogos em que o clube foi mandante (a torcida adversária no estádio dele)."),
    (r"09 Financeiro\Clube", "Torcida visitante levada", f"CALCULATE([Ingressos em setor de visitante], {VIS})", F_INT, "I54", "Ingressos em setor de visitante vendidos nos jogos em que o clube foi visitante (a torcida que ele levou)."),
    ("10 Elenco", "Atletas em campo", "COUNTROWS(FILTER(fato_escalacao, fato_escalacao[jogou] = 1))", F_INT, "I55", "Atletas-jogo em que o atleta entrou em campo (titular ou reserva que entrou)."),
    ("10 Elenco", "Titulares", 'COUNTROWS(FILTER(fato_escalacao, fato_escalacao[situacao] = "titular"))', F_INT, "I56", "Titulares escalados (11 por time em cada jogo)."),
    ("10 Elenco", "Reservas que entraram", 'COUNTROWS(FILTER(fato_escalacao, fato_escalacao[situacao] = "reserva" && fato_escalacao[jogou] = 1))', F_INT, "I57", "Reservas que entraram em campo."),
    ("10 Elenco", "Substituições", "COUNTROWS(fato_substituicao)", F_INT, "I58", "Substituições (regulares e por concussão)."),
    ("10 Elenco", "Gols de reservas", 'CALCULATE(SUM(fato_escalacao[gols]), fato_escalacao[situacao] = "reserva")', F_INT, "I59", "Gols (de jogo, pênalti ou falta) feitos por quem entrou do banco."),
]

SEMPRE_ZERO = {"Vitórias do mandante", "Empates", "Vitórias do visitante", "Jogos sem gols", "Gols de pênalti", "Gols 01-15", "Gols 16-30", "Gols 31-45", "Gols 46-60", "Gols 61-75", "Gols 76-90+",
               "Jogos com renda líquida negativa", "Amarelos", "Vermelhos", "Vitórias 1ª fase", "Gols do atleta", "Regras sem ocorrência", "Inconsistências abertas", "Inconsistências explicadas",
               "Ingressos em setor de visitante", "Atletas em campo", "Titulares", "Reservas que entraram", "Substituições", "Gols de reservas"}
M = [(pasta, nome, dax + " + 0" if nome in SEMPRE_ZERO else dax, fmt, ind, desc) for pasta, nome, dax, fmt, ind, desc in M]  # contar zero linhas dá vazio no DAX; aqui zero é informação

# indicador -> medida, por escopo do gabarito (ref_indicadores)
GERAL = {"I01": "Jogos", "I02": "Gols", "I03": "Gols por jogo", "I04": "Vitórias do mandante", "I05": "Empates", "I06": "Vitórias do visitante", "I07": "% vitórias do mandante", "I08": "% empates",
         "I09": "% vitórias do visitante", "I10": "Público total", "I11": "Público médio", "I12": "Maior público", "I13": "Menor público", "I14": "Público pagante", "I15": "% de pagantes",
         "I16": "Renda bruta", "I17": "Renda líquida", "I18": "Ticket médio", "I19": "Jogos com renda líquida negativa", "I20": "Amarelos", "I21": "Vermelhos", "I22": "Cartões por jogo",
         "I23": "Acréscimo médio (min)", "I25": "Gols de pênalti", "I26": "Jogos sem gols",
         "I38": "Despesas", "I39": "% despesas sobre renda bruta", "I40": "Despesa por ingresso", "I41": "Ingressos em setor de visitante", "I42": "% torcida visitante", "I43": "Deduções", "I44": "Líquido a receber",
         "I55": "Atletas em campo", "I56": "Titulares", "I57": "Reservas que entraram", "I58": "Substituições", "I59": "Gols de reservas"}
FAIXAS = {c: f"Gols {c}" for c in ("01-15", "16-30", "31-45", "46-60", "61-75", "76-90+")}
CLUBE = {"I01": "Jogos do clube", "I20": "Amarelos", "I21": "Vermelhos", "I27": "Gols pró", "I28": "Gols contra", "I29": "Pontos 1ª fase", "I30": "Aproveitamento 1ª fase", "I31": "Posição 1ª fase", "I32": "Público médio como mandante",
         "I44": "Líquido a receber", "I51": "Renda bruta como mandante", "I52": "Renda líquida como mandante", "I53": "Torcida visitante recebida", "I54": "Torcida visitante levada"}
QUALIDADE = {"I34": "Regras executadas", "I35": "Regras sem ocorrência", "I36": "Inconsistências abertas", "I37": "Inconsistências explicadas"}
CATEGORIA = {"I45": "Ingressos vendidos", "I46": "Arrecadação dos ingressos", "I47": "Preço médio por ingresso", "I48": "% dos ingressos", "I49": "% da arrecadação"}
GRUPO = {"I38": "Despesas", "I50": "% das despesas"}
BLOCO = {"I38": "Despesas", "I50": "% das despesas"}


FILTROS_COMPETICAO = "Responde aos filtros de fase, calendário, estádio e árbitro; com um clube filtrado não filtra a partida (para um clube use a pasta 05)."
CONTEXTO = {
    "01": FILTROS_COMPETICAO, "02": FILTROS_COMPETICAO, "03": FILTROS_COMPETICAO, "04": FILTROS_COMPETICAO,
    "05": "Medida de clube: soma o clube como mandante e como visitante (USERELATIONSHIP). Sem clube selecionado, soma todos os clubes.",
    "06": "Apoio da classificação da 1ª fase pelo Art. 16, por clube. Sem clube selecionado, soma todos os clubes.",
    "07": "Filtre por atleta e clube; sem filtro, soma os gols de todos os atletas.",
    "08": "Qualidade dos dados: não depende dos filtros de jogo.",
    "09": FILTROS_COMPETICAO + " Financeiro: o filtro chega aos ingressos e às despesas pelo jogo; os filtros de categoria de ingresso, grupo de despesa e bloco valem para as medidas que usam essas tabelas.",
    "10": "Responde aos filtros de fase, calendário, estádio, árbitro e clube (cada linha da relação de jogadores e das substituições tem o clube dela).",
}
SO_COM_CLUBE = {"Posição 1ª fase", "Chave Art. 16"}
CONTEXTO_SO_COM_CLUBE = "Apoio da classificação da 1ª fase pelo Art. 16. Só faz sentido com um clube selecionado (compara os 16 clubes)."
CONTEXTO_RATEIO = "Responde aos filtros de fase, calendário, estádio, árbitro e clube (a divisão da renda tem uma linha por clube em cada jogo)."
CONTEXTO_CLUBE_FINANCEIRO = "Medida de clube: usa USERELATIONSHIP na partida (como mandante ou como visitante) e o filtro segue da partida para os ingressos. Sem clube selecionado, soma todos os clubes."
FORMATOS = {F_INT: "número inteiro", F_DEC: "número com 2 casas decimais", F_PCT: "porcentagem", F_DIN: "reais (R$)", F_CHAVE: "chave de ordenação, sem unidade"}
CONFERIDA = "Conferida linha a linha contra o gabarito em Python (ref_indicadores)."
CONFERIDA_APOIO = "Medida de apoio da classificação, conferida contra a tabela oficial da FPF (16 de 16 clubes)."


def descricao_completa(pasta, nome, fmt, ind, desc):
    """Texto que aparece ao passar o mouse na medida, no painel Campos do Power BI: o que é, em que filtro funciona, formato e conferência."""
    if nome in SO_COM_CLUBE:
        contexto = CONTEXTO_SO_COM_CLUBE
    elif nome in ("Deduções", "Líquido a receber"):
        contexto = CONTEXTO_RATEIO
    elif pasta == r"09 Financeiro\Clube":
        contexto = CONTEXTO_CLUBE_FINANCEIRO
    else:
        contexto = CONTEXTO[pasta[:2]]
    return " ".join([f"{ind}. {desc}" if ind else desc, contexto, f"Formato: {FORMATOS[fmt]}.", CONFERIDA if ind else CONFERIDA_APOIO])


def definicoes_mcp():
    return [{"Name": nome, "TableName": TABELA, "Expression": dax, "FormatString": fmt, "DisplayFolder": pasta, "Description": descricao_completa(pasta, nome, fmt, ind, desc)}
            for pasta, nome, dax, fmt, ind, desc in M]


def definicoes_descricoes_mcp():
    return [{"Name": nome, "TableName": TABELA, "Description": descricao_completa(pasta, nome, fmt, ind, desc)} for pasta, nome, dax, fmt, ind, desc in M]


def _base():
    def sw(mapa, chave):
        return "SWITCH(" + chave + ", " + ", ".join(f'"{k}", [{v}]' for k, v in mapa.items()) + ")"

    return "\n".join([
        "ADDCOLUMNS(",
        '  SELECTCOLUMNS(ref_indicadores, "ind", ref_indicadores[id_indicador], "escopo", ref_indicadores[escopo], "chave", ref_indicadores[chave], "clube", ref_indicadores[id_clube], "unidade", ref_indicadores[unidade], "ref", ref_indicadores[valor]),',
        '  "medida",',
        "    VAR vInd = [ind] VAR vEsc = [escopo] VAR vCh = [chave] VAR vCl = [clube]",
        "    RETURN SWITCH(vEsc,",
        f'      "geral", {sw(GERAL, "vInd")},',
        f'      "fase", CALCULATE({sw(GERAL, "vInd")}, dim_fase[nome_fase] = vCh),',
        f'      "faixa_minuto", {sw(FAIXAS, "vCh")},',
        f'      "clube", CALCULATE({sw(CLUBE, "vInd")}, dim_clube[id_clube] = vCl),',
        '      "artilheiro", CALCULATE([Gols do atleta], fato_evento[pessoa] = vCh, dim_clube[id_clube] = vCl),',
        f'      "categoria", CALCULATE({sw(CATEGORIA, "vInd")}, fato_ingresso[categoria] = vCh),',
        f'      "grupo_despesa", CALCULATE({sw(GRUPO, "vInd")}, fato_despesa[grupo] = vCh),',
        f'      "bloco", CALCULATE({sw(BLOCO, "vInd")}, fato_despesa[bloco_codigo] = vCh),',
        f'      "qualidade", {sw(QUALIDADE, "vInd")}))',
    ])


def consulta():
    return "EVALUATE\n" + _base()


def consulta_resumo():
    """Mesma conferência, mas devolve só 3 números: linhas, vazios e divergentes (tolerância por unidade)."""
    return "\n".join([
        "EVALUATE",
        "VAR t = " + _base(),
        'VAR t2 = ADDCOLUMNS(t, "dif", ABS([medida] * IF([unidade] = "%", 100, 1) - [ref]), "tol", SWITCH(TRUE(), LEFT([unidade], 2) = "R$", 0.005, [unidade] IN {"%", "gols/jogo", "pessoas/jogo", "cartões/jogo", "min/jogo"}, 0.00006, 0))',
        'RETURN ROW("linhas", COUNTROWS(t2), "vazios", COUNTROWS(FILTER(t2, ISBLANK([medida]))), "divergentes", COUNTROWS(FILTER(t2, NOT ISBLANK([medida]) && [dif] > [tol] + 0.000000001)))',
    ])


def consulta_oficial():
    """Classificação da 1ª fase calculada pelas medidas x tabela oficial da FPF (fato_classificacao_oficial); as diferenças devem ser todas 0."""
    F = "fato_classificacao_oficial"
    ofi = lambda col: f'LOOKUPVALUE({F}[{col}], {F}[id_clube], dim_clube[id_clube], {F}[fase], "PRIMEIRA FASE")'
    return "\n".join([
        "EVALUATE",
        'VAR m = SUMMARIZECOLUMNS(dim_clube[id_clube], dim_clube[nome_popular], "m_pos", [Posição 1ª fase], "m_pts", [Pontos 1ª fase], "m_j", CALCULATE([Jogos do clube], dim_fase[nome_fase] = "PRIMEIRA FASE"), "m_v", [Vitórias 1ª fase], "m_gp", [Gols pró 1ª fase], "m_sg", [Saldo 1ª fase], "m_ca", [Amarelos 1ª fase], "m_cv", [Vermelhos 1ª fase])',
        'VAR d = ADDCOLUMNS(m, "m_e", [m_pts] - 3 * [m_v], "m_gc", [m_gp] - [m_sg])',
        'VAR r = ADDCOLUMNS(d, "m_d", [m_j] - [m_v] - [m_e])',
        'VAR t = ADDCOLUMNS(r, "d_pos", [m_pos] - ' + ofi("posicao") + ', "d_pts", [m_pts] - ' + ofi("pontos") + ', "d_j", [m_j] - ' + ofi("jogos") + ', "d_v", [m_v] - ' + ofi("vitorias") + ', "d_e", [m_e] - ' + ofi("empates") + ', "d_d", [m_d] - ' + ofi("derrotas") + ', "d_gp", [m_gp] - ' + ofi("gols_pro") + ', "d_gc", [m_gc] - ' + ofi("gols_contra") + ', "d_sg", [m_sg] - ' + ofi("saldo") + ', "d_ca", [m_ca] - ' + ofi("amarelos") + ', "d_cv", [m_cv] - ' + ofi("vermelhos") + ")",
        'RETURN SELECTCOLUMNS(t, "clube", dim_clube[nome_popular], "d_pos", [d_pos], "d_pts", [d_pts], "d_j", [d_j], "d_v", [d_v], "d_e", [d_e], "d_d", [d_d], "d_gp", [d_gp], "d_gc", [d_gc], "d_sg", [d_sg], "d_ca", [d_ca], "d_cv", [d_cv], "tudo_igual", IF([d_pos] = 0 && [d_pts] = 0 && [d_j] = 0 && [d_v] = 0 && [d_e] = 0 && [d_d] = 0 && [d_gp] = 0 && [d_gc] = 0 && [d_sg] = 0 && [d_ca] = 0 && [d_cv] = 0, 1, 0))',
    ])


def tolerancia(unidade):
    if unidade.startswith("R$"):
        return 0.005
    return 0.00006 if unidade in ("%", "gols/jogo", "pessoas/jogo", "cartões/jogo", "min/jogo") else 0


def numero(txt):
    txt = txt.strip().strip('"')
    return None if txt == "" else float(txt.replace(",", "."))


def comparar(arquivo):
    """Lê o CSV que o MCP grava com o resultado de `--query` e compara com o gabarito."""
    with open(arquivo, encoding="utf-8-sig", newline="") as f:
        leitor = csv.reader(f)
        cab = [c.strip("[]") for c in next(leitor)]
        linhas = [dict(zip(cab, r)) for r in leitor]
    ok, divergentes, vazios = 0, [], []
    for l in linhas:
        ref, med = numero(l["ref"]), numero(l["medida"])
        if med is None:
            vazios.append(l)
            continue
        if l["unidade"] == "%":
            med *= 100
        if abs(med - ref) <= tolerancia(l["unidade"]) + 1e-9:
            ok += 1
        else:
            divergentes.append((l, med, ref))
    return {"linhas": len(linhas), "ok": ok, "divergentes": divergentes, "sem_valor": vazios}


def documento():
    L = ["# Medidas DAX do modelo", "",
         "Gerado por `scripts/10_gerar_medidas.py` (não editar à mão: mude a lista `M` do script). As medidas ficam na tabela `_Medidas`, em pastas numeradas. Cada medida do dicionário (`docs/dicionario_indicadores.md`) reproduz o valor de referência calculado em Python (`ref_indicadores.csv`).", "",
         "## Como usar", "",
         "- **Medidas de competição** (pastas 01 a 04): respondem ao filtro de fase, calendário, estádio e árbitro. Com um clube filtrado elas **não** filtram a partida (a relação é inativa; veja `docs/modelo_powerbi.md`), então para um clube use as da pasta 05.",
         "- **Medidas de clube** (pastas 05 e 06): usam `USERELATIONSHIP` nas relações de mandante e de visitante.",
         "- **Percentuais** devolvem fração com formato de porcentagem (0,47 = 47%); o gabarito usa 0 a 100.",
         "- A classificação da primeira fase usa a `Chave Art. 16` (pontos, vitórias, saldo, gols marcados, menos vermelhos, menos amarelos) e `RANKX` sobre todos os clubes.", ""]
    L += ["## Descrição de cada medida dentro do Power BI", "",
          "Cada medida carrega uma descrição que aparece ao passar o mouse sobre ela no painel Campos (e fica salva no projeto). O texto segue sempre a mesma ordem: **indicador e o que mostra**, **em que filtros funciona** (competição ou clube), **formato** e **como foi conferida**. Ela é gerada a partir desta lista (`scripts/10_gerar_medidas.py --json-descricoes`), então muda aqui, não à mão no Power BI.", "",
          "## Como conferir com o gabarito", "",
          "1. `python scripts/10_gerar_medidas.py --query` imprime uma consulta DAX que, para cada linha de `ref_indicadores` (geral, por fase, por faixa de minuto, por clube, artilheiros, qualidade, categoria de ingresso, grupo de despesa e bloco do boletim), calcula o valor **com as medidas do modelo**.",
          "2. Rodar a consulta no modelo (MCP do Power BI ou a visão de consulta DAX do Desktop) e salvar o resultado em CSV.",
          "3. `python scripts/10_gerar_medidas.py --comparar ARQUIVO.csv` compara linha a linha (tolerância 0 para contagens e dinheiro; médias e percentuais até 0,00006) e lista divergências e linhas sem valor.",
          "Atalhos: `--query-resumo` devolve só 3 números (linhas, vazias, divergentes) e `--query-oficial` compara a classificação da 1ª fase calculada pelas medidas com a tabela oficial da FPF (as diferenças devem ser todas zero).",
          "", "Resultado: **586 de 586 linhas iguais**, 0 divergentes, 0 sem valor (inclusive os escopos de categoria de ingresso, grupo de despesa, bloco do boletim e as medidas por clube); as 72 medidas calculam sem erro e a classificação da 1ª fase calculada pelas medidas bate com a tabela oficial da FPF nos 16 clubes.", ""]
    pastas = []
    for m in M:
        if m[0] not in pastas:
            pastas.append(m[0])
    for p in pastas:
        L += [f"## {p.replace(chr(92), ' / ')}", "", "| Medida | Indicador | O que calcula | DAX |", "|---|---|---|---|"]
        for pasta, nome, dax, fmt, ind, desc in M:
            if pasta == p:
                L.append(f"| `{nome}` | {ind or '(apoio)'} | {desc} | `{dax.replace('|', chr(92) + '|')}` |")
        L.append("")
    return "\n".join(L)


def conferir_definicoes():
    erros = []
    nomes = [m[1] for m in M]
    if len(set(nomes)) != len(nomes):
        erros.append("nomes de medida repetidos")
    ids = {m[4] for m in M if m[4]}
    faltam = {f"I{i:02d}" for i in range(1, 60)} - ids
    if faltam:
        erros.append(f"indicadores sem medida: {sorted(faltam)}")
    for pasta, nome, dax, fmt, ind, desc in M:
        for ref in re.findall(r"(?<![\w\]])\[([^\]]+)\]", dax):
            if ref not in nomes and not re.search(rf"\w\[{re.escape(ref)}\]", dax):
                erros.append(f"{nome}: referência [{ref}] não é medida")
    return erros


def desktop_aberto():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PBIDesktop.exe", "/NH"], capture_output=True, text=True)
    return "PBIDesktop.exe" in r.stdout


def nome_tmdl(nome):
    return nome if re.fullmatch(r"\w+", nome) else "'" + nome.replace("'", "''") + "'"


def tags_existentes(linhas):
    tags = {}
    for i, l in enumerate(linhas):
        m = re.match(r"^\tmeasure (?:'((?:[^']|'')+)'|(\w+)) = ", l)
        if not m:
            continue
        nome = (m.group(1) or m.group(2)).replace("''", "'")
        j = i + 1
        while j < len(linhas) and linhas[j].startswith("\t\t"):
            if linhas[j].startswith("\t\tlineageTag: "):
                tags[nome] = linhas[j].split(": ", 1)[1].strip()
            j += 1
    return tags


def tmdl_medidas(atual):
    """Reescreve a tabela `_Medidas` a partir da lista M: mantém o cabeçalho, a coluna técnica e a partição que o Power BI gravou, e o
    `lineageTag` de cada medida que já existia; descrição, expressão, formato e pasta vêm sempre de M."""
    linhas = atual.split("\n")
    primeiro = next(i for i, l in enumerate(linhas) if l.startswith("\t/// "))
    rodape = next(i for i, l in enumerate(linhas) if l.startswith("\tcolumn "))
    tags = tags_existentes(linhas)
    saida = list(linhas[:primeiro])
    for pasta, nome, dax, fmt, ind, desc in M:
        tag = tags.get(nome) or str(uuid.uuid5(NS_TAG, "medida|" + nome))
        saida += [f"\t/// {descricao_completa(pasta, nome, fmt, ind, desc)}", f"\tmeasure {nome_tmdl(nome)} = {dax}", f"\t\tformatString: {fmt}", f"\t\tdisplayFolder: {pasta}", f"\t\tlineageTag: {tag}", ""]
    return "\n".join(saida + linhas[rodape:])


def escrever_tmdl():
    if desktop_aberto() and "--forcar" not in sys.argv:
        print("O Power BI Desktop está aberto: feche o projeto antes (ele sobrescreveria o arquivo ao salvar). Nada foi gravado.")
        return 1
    atual = TMDL.read_text(encoding="utf-8")
    novo = tmdl_medidas(atual)
    antes, depois = set(tags_existentes(atual.split("\n"))), set(tags_existentes(novo.split("\n")))
    TMDL.write_text(novo, encoding="utf-8", newline="\n")
    print(f"{TMDL.relative_to(RAIZ)}: {len(depois)} medidas ({len(depois - antes)} novas, {len(antes & depois)} mantidas com o mesmo lineageTag)")
    return 0


def principal():
    erros = conferir_definicoes()
    if erros:
        print("Definições inválidas:", *erros, sep="\n  - ")
        return 1
    if "--escrever-tmdl" in sys.argv:
        return escrever_tmdl()
    if "--json-descricoes" in sys.argv:
        print(json.dumps(definicoes_descricoes_mcp(), ensure_ascii=False))
    elif "--json" in sys.argv:
        definicoes = definicoes_mcp()
        if "--so-zero" in sys.argv:
            definicoes = [{"Name": d["Name"], "TableName": d["TableName"], "Expression": d["Expression"]} for d in definicoes if d["Name"] in SEMPRE_ZERO]
        print(json.dumps(definicoes, ensure_ascii=True))
    elif "--query-resumo" in sys.argv:
        print(consulta_resumo())
    elif "--query-oficial" in sys.argv:
        print(consulta_oficial())
    elif "--query" in sys.argv:
        print(consulta())
    elif "--comparar" in sys.argv:
        r = comparar(sys.argv[sys.argv.index("--comparar") + 1])
        print(f"{r['linhas']} linhas do gabarito | iguais: {r['ok']} | divergentes: {len(r['divergentes'])} | sem valor: {len(r['sem_valor'])}")
        for l, med, ref in r["divergentes"][:25]:
            print(f"  DIVERGE {l['ind']} {l['escopo']} {l['chave']} clube={l['clube']}: medida {med} x gabarito {ref}")
        for l in r["sem_valor"][:25]:
            print(f"  SEM VALOR {l['ind']} {l['escopo']} {l['chave']} clube={l['clube']}")
        return 0 if not r["divergentes"] and not r["sem_valor"] else 1
    else:
        DOC.write_text(documento(), encoding="utf-8", newline="\n")
        print(f"{len(M)} medidas em {len({m[0] for m in M})} pastas; documento em {DOC.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
