# Medidas DAX do modelo

Gerado por `scripts/10_gerar_medidas.py` (não editar à mão: mude a lista `M` do script). As medidas ficam na tabela `_Medidas`, em pastas numeradas. Cada medida do dicionário (`docs/dicionario_indicadores.md`) reproduz o valor de referência calculado em Python (`ref_indicadores.csv`).

## Como usar

- **Medidas de competição** (pastas 01 a 04): respondem ao filtro de fase, calendário, estádio e árbitro. Com um clube filtrado elas **não** filtram a partida (a relação é inativa; veja `docs/modelo_powerbi.md`), então para um clube use as da pasta 05.
- **Medidas de clube** (pastas 05 e 06): usam `USERELATIONSHIP` nas relações de mandante e de visitante.
- **Percentuais** devolvem fração com formato de porcentagem (0,47 = 47%); o gabarito usa 0 a 100.
- A classificação da primeira fase usa a `Chave Art. 16` (pontos, vitórias, saldo, gols marcados, menos vermelhos, menos amarelos) e `RANKX` sobre todos os clubes.

## Descrição de cada medida dentro do Power BI

Cada medida carrega uma descrição que aparece ao passar o mouse sobre ela no painel Campos (e fica salva no projeto). O texto segue sempre a mesma ordem: **indicador e o que mostra**, **em que filtros funciona** (competição ou clube), **formato** e **como foi conferida**. Ela é gerada a partir desta lista (`scripts/10_gerar_medidas.py --json-descricoes`), então muda aqui, não à mão no Power BI.

## Como conferir com o gabarito

1. `python scripts/10_gerar_medidas.py --query` imprime uma consulta DAX que, para cada linha de `ref_indicadores` (geral, por fase, por faixa de minuto, por clube, artilheiros, qualidade, categoria de ingresso, grupo de despesa e bloco do boletim), calcula o valor **com as medidas do modelo**.
2. Rodar a consulta no modelo (MCP do Power BI ou a visão de consulta DAX do Desktop) e salvar o resultado em CSV.
3. `python scripts/10_gerar_medidas.py --comparar ARQUIVO.csv` compara linha a linha (tolerância 0 para contagens e dinheiro; médias e percentuais até 0,00006) e lista divergências e linhas sem valor.
Atalhos: `--query-resumo` devolve só 3 números (linhas, vazias, divergentes) e `--query-oficial` compara a classificação da 1ª fase calculada pelas medidas com a tabela oficial da FPF (as diferenças devem ser todas zero).

Resultado: **586 de 586 linhas iguais**, 0 divergentes, 0 sem valor (inclusive os escopos de categoria de ingresso, grupo de despesa, bloco do boletim e as medidas por clube); as 72 medidas calculam sem erro e a classificação da 1ª fase calculada pelas medidas bate com a tabela oficial da FPF nos 16 clubes.

## 01 Resultados

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Jogos` | I01 | Quantos jogos. | `COUNTROWS(fato_partida)` |
| `Gols` | I02 | Gols do placar (inclui pênalti, falta e gol contra; sem a disputa de pênaltis). | `SUM(fato_partida[gols_mandante]) + SUM(fato_partida[gols_visitante])` |
| `Gols por jogo` | I03 | Média de gols por jogo. | `DIVIDE([Gols], [Jogos])` |
| `Vitórias do mandante` | I04 | Jogos em que o mandante fez mais gols no tempo regulamentar. | `COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] > fato_partida[gols_visitante])) + 0` |
| `Empates` | I05 | Jogos empatados no tempo regulamentar (o decidido nos pênaltis conta como empate). | `COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] = fato_partida[gols_visitante])) + 0` |
| `Vitórias do visitante` | I06 | Jogos em que o visitante fez mais gols no tempo regulamentar. | `COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] < fato_partida[gols_visitante])) + 0` |
| `% vitórias do mandante` | I07 | Vitórias do mandante sobre o total de jogos. | `DIVIDE([Vitórias do mandante], [Jogos])` |
| `% empates` | I08 | Empates sobre o total de jogos. | `DIVIDE([Empates], [Jogos])` |
| `% vitórias do visitante` | I09 | Vitórias do visitante sobre o total de jogos. | `DIVIDE([Vitórias do visitante], [Jogos])` |
| `Jogos sem gols` | I26 | Jogos 0 x 0. | `COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] + fato_partida[gols_visitante] = 0)) + 0` |

## 02 Gols e tempo

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Gols de pênalti` | I25 | Gols de pênalti durante o jogo. | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "gol_penalti") + 0` |
| `Acréscimo médio (min)` | I23 | Minutos de acréscimo por jogo (1º mais 2º tempo), pela súmula. | `AVERAGEX(fato_partida, fato_partida[acrescimo_1t_min] + fato_partida[acrescimo_2t_min])` |

## 02 Gols e tempo / Faixas de minuto

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Gols 01-15` | I24 | Gols entre os minutos 01-15 (o acréscimo fica na última faixa do tempo). | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta", "gol_contra"}, fato_evento[minuto] >= 0, fato_evento[minuto] <= 15) + 0` |
| `Gols 16-30` | I24 | Gols entre os minutos 16-30 (o acréscimo fica na última faixa do tempo). | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta", "gol_contra"}, fato_evento[minuto] >= 16, fato_evento[minuto] <= 30) + 0` |
| `Gols 31-45` | I24 | Gols entre os minutos 31-45 (o acréscimo fica na última faixa do tempo). | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta", "gol_contra"}, fato_evento[minuto] >= 31, fato_evento[minuto] <= 45) + 0` |
| `Gols 46-60` | I24 | Gols entre os minutos 46-60 (o acréscimo fica na última faixa do tempo). | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta", "gol_contra"}, fato_evento[minuto] >= 46, fato_evento[minuto] <= 60) + 0` |
| `Gols 61-75` | I24 | Gols entre os minutos 61-75 (o acréscimo fica na última faixa do tempo). | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta", "gol_contra"}, fato_evento[minuto] >= 61, fato_evento[minuto] <= 75) + 0` |
| `Gols 76-90+` | I24 | Gols entre os minutos 76-90+ (o acréscimo fica na última faixa do tempo). | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta", "gol_contra"}, fato_evento[minuto] >= 76, fato_evento[minuto] <= 999) + 0` |

## 03 Público e renda

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Público total` | I10 | Ingressos vendidos (boletim financeiro). | `SUM(fato_partida[publico_boletim])` |
| `Público médio` | I11 | Público médio por jogo. | `DIVIDE([Público total], [Jogos])` |
| `Maior público` | I12 | Maior público de um jogo. | `MAX(fato_partida[publico_boletim])` |
| `Menor público` | I13 | Menor público de um jogo. | `MIN(fato_partida[publico_boletim])` |
| `Público pagante` | I14 | Pessoas que pagaram ingresso. | `SUM(fato_partida[publico_pagante])` |
| `% de pagantes` | I15 | Parte do público que pagou. | `DIVIDE([Público pagante], [Público total])` |
| `Renda bruta` | I16 | Arrecadação de ingressos antes das despesas. | `SUM(fato_partida[renda_bruta])` |
| `Renda líquida` | I17 | Renda bruta menos as despesas do jogo (pode ser negativa). | `SUM(fato_partida[renda_liquida])` |
| `Ticket médio` | I18 | Renda bruta dividida pelo público pagante. | `DIVIDE([Renda bruta], [Público pagante])` |
| `Jogos com renda líquida negativa` | I19 | Jogos em que as despesas passaram da arrecadação. | `COUNTROWS(FILTER(fato_partida, fato_partida[renda_liquida] < 0)) + 0` |

## 04 Disciplina

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Amarelos` | I20 | Regra da FPF: todas as advertências (atletas e comissão) menos os segundos amarelos. | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "amarelo") - CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "segundo_amarelo") + 0` |
| `Vermelhos` | I21 | Regra da FPF: vermelhos diretos mais as expulsões por segundo amarelo. | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "vermelho") + CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] = "segundo_amarelo") + 0` |
| `Cartões por jogo` | I22 | Amarelos mais vermelhos por jogo. | `DIVIDE([Amarelos] + [Vermelhos], [Jogos])` |

## 05 Clube

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Jogos do clube` | I01 | Jogos do clube selecionado, como mandante ou visitante. | `CALCULATE(COUNTROWS(fato_partida), USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube])) + CALCULATE(COUNTROWS(fato_partida), USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube]))` |
| `Gols pró` | I27 | Gols que o clube fez. | `CALCULATE(SUM(fato_partida[gols_mandante]), USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube])) + CALCULATE(SUM(fato_partida[gols_visitante]), USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube]))` |
| `Gols contra` | I28 | Gols que o clube levou. | `CALCULATE(SUM(fato_partida[gols_visitante]), USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube])) + CALCULATE(SUM(fato_partida[gols_mandante]), USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube]))` |
| `Pontos` | (apoio) | Pontos do clube nos jogos do contexto (3 por vitória, 1 por empate no tempo regulamentar). | `CALCULATE(SUMX(fato_partida, SWITCH(TRUE(), fato_partida[gols_mandante] > fato_partida[gols_visitante], 3, fato_partida[gols_mandante] = fato_partida[gols_visitante], 1, 0)), USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube])) + CALCULATE(SUMX(fato_partida, SWITCH(TRUE(), fato_partida[gols_visitante] > fato_partida[gols_mandante], 3, fato_partida[gols_mandante] = fato_partida[gols_visitante], 1, 0)), USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube]))` |
| `Pontos 1ª fase` | I29 | Pontos do clube na primeira fase. | `CALCULATE([Pontos], dim_fase[nome_fase] = "PRIMEIRA FASE")` |
| `Aproveitamento 1ª fase` | I30 | Pontos conquistados sobre os disputados na primeira fase. | `DIVIDE([Pontos 1ª fase], 3 * CALCULATE([Jogos do clube], dim_fase[nome_fase] = "PRIMEIRA FASE"))` |
| `Público médio como mandante` | I32 | Público médio dos jogos em que o clube foi mandante. | `CALCULATE(AVERAGE(fato_partida[publico_boletim]), USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube]))` |

## 06 Classificação (Art. 16)

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Vitórias 1ª fase` | (apoio) | Vitórias do clube na primeira fase. | `CALCULATE(COUNTROWS(FILTER(fato_partida, fato_partida[gols_mandante] > fato_partida[gols_visitante])), USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube]), dim_fase[nome_fase] = "PRIMEIRA FASE") + CALCULATE(COUNTROWS(FILTER(fato_partida, fato_partida[gols_visitante] > fato_partida[gols_mandante])), USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube]), dim_fase[nome_fase] = "PRIMEIRA FASE") + 0` |
| `Gols pró 1ª fase` | (apoio) | Gols marcados na primeira fase. | `CALCULATE([Gols pró], dim_fase[nome_fase] = "PRIMEIRA FASE")` |
| `Saldo 1ª fase` | (apoio) | Saldo de gols na primeira fase. | `[Gols pró 1ª fase] - CALCULATE([Gols contra], dim_fase[nome_fase] = "PRIMEIRA FASE")` |
| `Amarelos 1ª fase` | (apoio) | Amarelos do clube na primeira fase (regra da FPF). | `CALCULATE([Amarelos], dim_fase[nome_fase] = "PRIMEIRA FASE")` |
| `Vermelhos 1ª fase` | (apoio) | Vermelhos do clube na primeira fase (regra da FPF). | `CALCULATE([Vermelhos], dim_fase[nome_fase] = "PRIMEIRA FASE")` |
| `Chave Art. 16` | (apoio) | Número que ordena a primeira fase pelo Art. 16: pontos, vitórias, saldo, gols marcados, menos vermelhos, menos amarelos (cada critério numa casa própria; maior é melhor). | `[Pontos 1ª fase] * 10^12 + [Vitórias 1ª fase] * 10^10 + ([Saldo 1ª fase] + 100) * 10^7 + [Gols pró 1ª fase] * 10^5 + (99 - [Vermelhos 1ª fase]) * 10^3 + (999 - [Amarelos 1ª fase])` |
| `Posição 1ª fase` | I31 | Posição do clube na primeira fase pelo desempate do Art. 16. | `RANKX(ALL(dim_clube), [Chave Art. 16], , DESC, SKIP)` |

## 07 Artilharia

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Gols do atleta` | I33 | Gols do atleta pelo próprio clube (gol de pênalti e de falta contam; gol contra não). | `CALCULATE(COUNTROWS(fato_evento), fato_evento[tipo_evento] IN {"gol", "gol_penalti", "gol_falta"}) + 0` |

## 08 Qualidade dos dados

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Regras executadas` | I34 | Regras de conferência que rodaram. | `COUNTROWS(resultado_regra)` |
| `Regras sem ocorrência` | I35 | Regras em que as fontes concordam por completo. | `COUNTROWS(FILTER(resultado_regra, resultado_regra[resultado] = "ok")) + 0` |
| `Inconsistências abertas` | I36 | Divergências ainda sem solução. | `CALCULATE(COUNTROWS(fato_inconsistencia), fato_inconsistencia[status] = "aberta") + 0` |
| `Inconsistências explicadas` | I37 | Divergências com causa conhecida e decisão registrada (explicadas, aceitas ou corrigidas). | `CALCULATE(COUNTROWS(fato_inconsistencia), fato_inconsistencia[status] IN {"explicada", "aceita", "corrigida"}) + 0` |

## 09 Financeiro

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Despesas` | I38 | Despesas dos jogos: soma das rubricas dos blocos B1, B2 e B3 do boletim. Com um grupo de despesa ou um bloco filtrado, só o que é dele. | `SUM(fato_despesa[valor])` |
| `% despesas sobre renda bruta` | I39 | Quanto da arrecadação foi gasto em despesas. | `DIVIDE([Despesas], [Renda bruta])` |
| `Despesa por ingresso` | I40 | Despesa média por ingresso vendido. | `DIVIDE([Despesas], [Público total])` |
| `Ingressos em setor de visitante` | I41 | Ingressos vendidos em setores cujo nome cita visitante (estimativa pelo nome do setor). | `CALCULATE(SUM(fato_ingresso[ingressos]), fato_ingresso[setor_visitante] = 1) + 0` |
| `% torcida visitante` | I42 | Parte do público que está em setor de visitante. | `DIVIDE([Ingressos em setor de visitante], [Público total])` |
| `Deduções` | I43 | Descontos que o boletim aplica sobre a parte de cada clube na divisão da renda líquida (INSS e outras). | `SUM(fato_rateio[deducao_inss]) + SUM(fato_rateio[deducao_outras])` |
| `Líquido a receber` | I44 | O que o clube recebe da renda líquida depois das deduções (em 2026 o mandante fica com 100% e o visitante com 0%). | `SUM(fato_rateio[liquido])` |
| `Ingressos vendidos` | I45 | Ingressos vendidos, somando as linhas do boletim; com uma categoria filtrada, os dela. | `SUM(fato_ingresso[ingressos])` |
| `Arrecadação dos ingressos` | I46 | Dinheiro arrecadado pelas linhas de ingresso; com uma categoria filtrada, o dela. | `SUM(fato_ingresso[arrecadacao])` |
| `Preço médio por ingresso` | I47 | Quanto cada ingresso rendeu, em média (a gratuidade por lei não tem preço: zero). | `DIVIDE([Arrecadação dos ingressos], [Ingressos vendidos])` |
| `% dos ingressos` | I48 | Parte dos ingressos vendidos que é da categoria filtrada. | `DIVIDE([Ingressos vendidos], CALCULATE([Ingressos vendidos], ALL(fato_ingresso[categoria])))` |
| `% da arrecadação` | I49 | Parte da arrecadação que é da categoria filtrada. | `DIVIDE([Arrecadação dos ingressos], CALCULATE([Arrecadação dos ingressos], ALL(fato_ingresso[categoria])))` |
| `% das despesas` | I50 | Parte das despesas que é do grupo de despesa ou do bloco filtrado. | `DIVIDE([Despesas], CALCULATE([Despesas], ALL(fato_despesa[grupo]), ALL(fato_despesa[bloco_codigo])))` |

## 09 Financeiro / Clube

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Renda bruta como mandante` | I51 | Arrecadação dos jogos em que o clube foi mandante (a renda do jogo é do mandante). | `CALCULATE([Renda bruta], USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube]))` |
| `Renda líquida como mandante` | I52 | Renda líquida dos jogos em que o clube foi mandante (pode ser negativa). | `CALCULATE([Renda líquida], USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube]))` |
| `Torcida visitante recebida` | I53 | Ingressos em setor de visitante vendidos nos jogos em que o clube foi mandante (a torcida adversária no estádio dele). | `CALCULATE([Ingressos em setor de visitante], USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube]))` |
| `Torcida visitante levada` | I54 | Ingressos em setor de visitante vendidos nos jogos em que o clube foi visitante (a torcida que ele levou). | `CALCULATE([Ingressos em setor de visitante], USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube]))` |

## 10 Elenco

| Medida | Indicador | O que calcula | DAX |
|---|---|---|---|
| `Atletas em campo` | I55 | Atletas-jogo em que o atleta entrou em campo (titular ou reserva que entrou). | `COUNTROWS(FILTER(fato_escalacao, fato_escalacao[jogou] = 1)) + 0` |
| `Titulares` | I56 | Titulares escalados (11 por time em cada jogo). | `COUNTROWS(FILTER(fato_escalacao, fato_escalacao[situacao] = "titular")) + 0` |
| `Reservas que entraram` | I57 | Reservas que entraram em campo. | `COUNTROWS(FILTER(fato_escalacao, fato_escalacao[situacao] = "reserva" && fato_escalacao[jogou] = 1)) + 0` |
| `Substituições` | I58 | Substituições (regulares e por concussão). | `COUNTROWS(fato_substituicao) + 0` |
| `Gols de reservas` | I59 | Gols (de jogo, pênalti ou falta) feitos por quem entrou do banco. | `CALCULATE(SUM(fato_escalacao[gols]), fato_escalacao[situacao] = "reserva") + 0` |
