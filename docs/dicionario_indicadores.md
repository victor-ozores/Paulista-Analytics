# Dicionário de indicadores

Para que serve: dizer, em português simples, **o que cada número do dashboard significa, como é calculado e de onde vem**. Cada medida DAX reproduz o valor de referência abaixo, que o Python calcula e grava em `data/processed/ref_indicadores.csv` (script `scripts/indicadores.py`, chamado por `scripts/05_validar.py`). Colunas das tabelas: `docs/contrato_dados.md`.

Valores desta página: Paulistão A1 2026. Esta página explica a **definição** de cada indicador; não é a fonte dos números (a fonte é o arquivo de referência gerado por `python scripts/05_validar.py`).

## Regras que valem para todos os indicadores

- **Fonte que vale:** placar, público, renda, árbitros e cartões vêm das fontes **oficiais da FPF** (tabela de jogos, súmula e boletim financeiro). A ESPN entra só nas cobranças da disputa de pênaltis, nas estatísticas do jogo (posse, finalizações etc.) e como segunda opinião.
- **Jogo** é uma partida da A1 2026: 72 (64 da primeira fase, 4 quartas, 2 semifinais, 2 da final).
- **Resultado do jogo** é o do tempo regulamentar (90 minutos). Pênaltis decidem quem avança, mas **não** viram gol, nem vitória no placar: o jogo decidido nos pênaltis (Corinthians x Portuguesa, quartas) conta como empate.
- **Gol** é o que está no placar: inclui pênalti convertido durante o jogo, gol de falta e **gol contra** (que vale para o adversário de quem fez). Cobranças da disputa de pênaltis não são gols.
- **Público** é o número de ingressos vendidos do **boletim financeiro**, igual à ESPN nos 72 jogos. **Pagante** é a parte do público que pagou (o resto são gratuidades e cortesias).
- **Mandante e visitante** são os da tabela oficial.

## Indicadores

Colunas: **Escopos** diz onde o indicador existe (G = geral, F = por fase, C = por clube, M = faixa de minuto, A = artilheiro, Q = qualidade, Cg = por categoria de ingresso, D = por grupo de despesa, B = por bloco do boletim). I01 a I37 são os indicadores da competição; **I38 a I59 são os do financeiro detalhado e do elenco**.

| ID | Nome | O que significa | Como calcula | De onde vem | Escopos | Valor geral (A1 2026) |
|---|---|---|---|---|---|---|
| I01 | `jogos` | Quantos jogos | Contagem de linhas de `fato_partida`. Por clube: jogos em que ele aparece como mandante ou visitante | `fato_partida` | G F C | 72 |
| I02 | `gols` | Total de gols do campeonato | Soma de `gols_mandante` + `gols_visitante` | `fato_partida` | G F | 168 |
| I03 | `gols_por_jogo` | Média de gols por jogo | I02 ÷ I01 | `fato_partida` | G F | 2,3333 |
| I04 | `vitorias_mandante` | Jogos em que o mandante fez mais gols | Contagem com `gols_mandante` > `gols_visitante` | `fato_partida` | G F | 34 |
| I05 | `empates` | Jogos empatados no tempo regulamentar | Contagem com gols iguais | `fato_partida` | G F | 17 |
| I06 | `vitorias_visitante` | Jogos em que o visitante fez mais gols | Contagem com `gols_visitante` > `gols_mandante` | `fato_partida` | G F | 21 |
| I07 | `pct_vitorias_mandante` | % de jogos ganhos pelo mandante | I04 ÷ I01 × 100 | `fato_partida` | G F | 47,2222 % |
| I08 | `pct_empates` | % de jogos empatados | I05 ÷ I01 × 100 | `fato_partida` | G F | 23,6111 % |
| I09 | `pct_vitorias_visitante` | % de jogos ganhos pelo visitante | I06 ÷ I01 × 100 | `fato_partida` | G F | 29,1667 % |
| I10 | `publico_total` | Soma do público dos jogos | Soma de `publico_boletim` | `fato_partida` (boletim) | G F | 784.369 |
| I11 | `publico_medio` | Público médio por jogo | I10 ÷ I01 | `fato_partida` | G F | 10.894,0139 |
| I12 | `publico_maximo` | Maior público de um jogo | Máximo de `publico_boletim` | `fato_partida` | G F | 49.605 |
| I13 | `publico_minimo` | Menor público de um jogo | Mínimo de `publico_boletim` | `fato_partida` | G F | 1.055 |
| I14 | `publico_pagante` | Pessoas que pagaram ingresso | Soma de `publico_pagante` | `fato_partida` (boletim) | G F | 761.489 |
| I15 | `pct_pagantes` | Que parte do público pagou | I14 ÷ I10 × 100 | `fato_partida` | G F | 97,083 % |
| I16 | `renda_bruta` | Arrecadação de ingressos antes das despesas | Soma de `renda_bruta` | `fato_partida` (boletim) | G F | R$ 44.730.003,80 |
| I17 | `renda_liquida` | O que sobra depois das despesas do jogo. **Pode ser negativa** | Soma de `renda_liquida` (renda bruta − despesas) | `fato_partida` (boletim) | G F | R$ 24.325.256,66 |
| I18 | `ticket_medio` | Quanto cada pagante pagou, em média | I16 ÷ I14 | `fato_partida` | G F | R$ 58,74 |
| I19 | `jogos_renda_liquida_negativa` | Jogos em que as despesas passaram da arrecadação | Contagem com `renda_liquida` < 0 | `fato_partida` | G F | 15 |
| I20 | `amarelos` | Cartões amarelos pela regra da FPF | Advertências (atletas e comissão técnica) **menos** os segundos amarelos | `fato_evento` | G F C | 385 |
| I21 | `vermelhos` | Cartões vermelhos pela regra da FPF | Vermelhos diretos **mais** as expulsões por segundo amarelo | `fato_evento` | G F C | 28 |
| I22 | `cartoes_por_jogo` | Cartões por jogo | (I20 + I21) ÷ I01 | `fato_evento`, `fato_partida` | G F | 5,7361 |
| I23 | `acrescimo_medio_min` | Minutos de acréscimo por jogo (1º + 2º tempo) | Média de `acrescimo_1t_min` + `acrescimo_2t_min` | `fato_partida` (súmula) | G F | 10,6111 |
| I24 | `gols_por_faixa_minuto` | Gols em cada faixa do jogo | Contagem de gols por `minuto`: 01-15, 16-30, 31-45, 46-60, 61-75, 76-90+ (o acréscimo fica na última faixa do tempo) | `fato_evento` | M | 22, 22, 24, 27, 26, 47 (soma 168) |
| I25 | `gols_de_penalti` | Gols de pênalti durante o jogo | Contagem de `tipo_evento` = `gol_penalti` | `fato_evento` | G F | 13 |
| I26 | `jogos_sem_gols` | Jogos 0 x 0 | Contagem com placar 0 x 0 | `fato_partida` | G F | 3 |
| I27 | `gols_pro` | Gols que o clube fez | Soma dos gols do clube em todos os jogos (como mandante ou visitante) | `fato_partida` | C | (por clube) |
| I28 | `gols_contra` | Gols que o clube levou | Soma dos gols do adversário | `fato_partida` | C | (por clube) |
| I29 | `pontos_primeira_fase` | Pontos na primeira fase | 3 por vitória, 1 por empate | `fato_partida` | C | (por clube) |
| I30 | `aproveitamento_primeira_fase` | % dos pontos disputados que o clube conquistou | I29 ÷ (3 × jogos da primeira fase) × 100 | `fato_partida` | C | (por clube) |
| I31 | `posicao_primeira_fase` | Posição na tabela da primeira fase, com desempate do Art. 16 | Pontos, vitórias, saldo, gols marcados, menos vermelhos, menos amarelos | `ref_classificacao_primeira_fase` | C | 1 a 16 |
| I32 | `publico_medio_como_mandante` | Público médio dos jogos em que o clube foi mandante | Média de `publico_boletim` dos jogos do clube como mandante | `fato_partida` | C | (por clube) |
| I33 | `gols_artilheiro` | Gols do jogador pelo próprio clube | Contagem de `gol`, `gol_penalti` e `gol_falta` por pessoa. **Gol contra não conta** | `fato_evento` | A | Robson dos Santos Fernandes, 7 |
| I34 | `regras_executadas` | Quantas regras de conferência rodaram | Contagem de linhas de `resultado_regra` | `resultado_regra` | Q | 34 |
| I35 | `regras_sem_ocorrencia` | Regras em que as fontes concordam por completo | Contagem de regras com resultado `ok` | `resultado_regra` | Q | 25 |
| I36 | `inconsistencias_abertas` | Divergências ainda sem solução | Contagem de `fato_inconsistencia` com status `aberta` | `fato_inconsistencia` | Q | 2 |
| I37 | `inconsistencias_explicadas` | Divergências com causa conhecida e regra definida | Contagem com status `explicada`, `aceita` ou `corrigida` | `fato_inconsistencia` | Q | 43 |
| I38 | `despesas` | Despesas dos jogos, somando os três blocos do boletim (aluguéis e seguros, taxas e impostos, despesas operacionais). Por grupo de despesa ou por bloco, só o que é daquele grupo ou bloco | Geral e por fase: soma de `despesas_total` (conferida contra a soma das rubricas de `fato_despesa`, regra A43). Por grupo ou bloco: soma das rubricas | `fato_partida`, `fato_despesa` | G F D B | R$ 20.404.747,14 |
| I39 | `pct_despesas_renda_bruta` | Quanto da arrecadação foi gasto em despesas | I38 ÷ I16 × 100 | `fato_partida` | G F | 45,6176 % |
| I40 | `despesa_por_ingresso` | Despesa média por ingresso vendido | I38 ÷ I10 | `fato_partida` | G F | R$ 26,01 |
| I41 | `ingressos_setor_visitante` | Ingressos vendidos em setores cujo nome cita visitante (torcida visitante). **É uma estimativa pelo nome do setor** | Soma de `ingressos` das linhas de `fato_ingresso` com `setor_visitante` = 1 | `fato_ingresso` | G F | 69.685 |
| I42 | `pct_torcida_visitante` | Parte do público que está em setor de visitante | I41 ÷ I10 × 100 | `fato_ingresso`, `fato_partida` | G F | 8,8842 % |
| I43 | `deducoes` | Descontos que o boletim aplica sobre a parte de cada clube na divisão da renda líquida (INSS e outras deduções) | Soma de `deducao_inss` + `deducao_outras` | `fato_rateio` | G F | R$ 153.535,40 |
| I44 | `liquido_a_receber` | O que o clube recebe da renda líquida depois das deduções (em 2026 o mandante fica com 100% e o visitante com 0%) | Soma de `liquido`. Por clube: as linhas do clube, em casa ou fora | `fato_rateio` | G F C | R$ 24.171.721,26 |
| I45 | `ingressos_vendidos` | Ingressos vendidos de uma categoria (inteira, meia-entrada, sócio-torcedor, cadeira e camarote, gratuidade por lei, outros). **A categoria é classificação do projeto, não oficial** | Soma de `ingressos` das linhas da categoria | `fato_ingresso` | Cg | (por categoria) |
| I46 | `arrecadacao_ingressos` | Dinheiro que a categoria arrecadou | Soma de `arrecadacao` das linhas da categoria | `fato_ingresso` | Cg | (por categoria) |
| I47 | `preco_medio_ingresso` | Quanto cada ingresso da categoria rendeu, em média (a gratuidade por lei não tem preço: zero) | I46 ÷ I45 | `fato_ingresso` | Cg | (por categoria) |
| I48 | `pct_ingressos` | Parte dos ingressos vendidos que é da categoria | I45 ÷ total de ingressos × 100 | `fato_ingresso` | Cg | (por categoria) |
| I49 | `pct_arrecadacao` | Parte da arrecadação que é da categoria | I46 ÷ total arrecadado × 100 | `fato_ingresso` | Cg | (por categoria) |
| I50 | `pct_despesas` | Parte das despesas que é de um grupo (agrupamento do projeto, não oficial) ou de um bloco do boletim | Despesa do grupo ou do bloco ÷ despesa total × 100 | `fato_despesa` | D B | (por grupo ou bloco) |
| I51 | `renda_bruta_como_mandante` | Arrecadação dos jogos em que o clube foi mandante (a renda do jogo é do mandante) | Soma de `renda_bruta` dos jogos do clube como mandante | `fato_partida` | C | (por clube) |
| I52 | `renda_liquida_como_mandante` | Renda líquida dos jogos em que o clube foi mandante (pode ser negativa) | Soma de `renda_liquida` dos jogos do clube como mandante | `fato_partida` | C | (por clube) |
| I53 | `torcida_visitante_recebida` | Ingressos em setor de visitante vendidos nos jogos em que o clube foi mandante (a torcida adversária no estádio dele) | Soma de `ingressos` com `setor_visitante` = 1 nos jogos do clube em casa | `fato_ingresso` | C | (por clube) |
| I54 | `torcida_visitante_levada` | Ingressos em setor de visitante vendidos nos jogos em que o clube foi visitante (a torcida que ele levou) | Soma de `ingressos` com `setor_visitante` = 1 nos jogos do clube fora | `fato_ingresso` | C | (por clube) |
| I55 | `atletas_em_campo` | Atletas-jogo em que o atleta entrou em campo (titular ou reserva que entrou) | Contagem de linhas de `fato_escalacao` com `jogou` = 1 | `fato_escalacao` | G F | 2.290 |
| I56 | `titulares` | Titulares escalados (11 por time em cada jogo) | Contagem com `situacao` = titular | `fato_escalacao` | G F | 1.584 |
| I57 | `reservas_que_entraram` | Reservas que entraram em campo | Contagem com `situacao` = reserva e `jogou` = 1 | `fato_escalacao` | G F | 706 |
| I58 | `substituicoes` | Substituições (regulares e por concussão) | Contagem de linhas de `fato_substituicao` | `fato_substituicao` | G F | 706 |
| I59 | `gols_de_reservas` | Gols (de jogo, pênalti ou falta) feitos por quem entrou do banco | Soma de `gols` dos atletas com `situacao` = reserva | `fato_escalacao` | G F | 34 |

### Por fase (exemplo de I01, I02, I03, I11)

| Fase | Jogos | Gols | Gols por jogo | Público médio |
|---|---|---|---|---|
| Primeira fase | 64 | 148 | 2,3125 | 10.239,03 |
| Quartas de final | 4 | 12 | 3 | 12.937,75 |
| Semifinal | 2 | 4 | 2 | 20.308 |
| Final | 2 | 4 | 2 | 18.352 |

## Como ler `ref_indicadores.csv`

Colunas: `id_indicador`, `indicador`, `escopo` (`geral`, `fase`, `faixa_minuto`, `clube`, `artilheiro`, `qualidade`, `categoria`, `grupo_despesa`, `bloco`), `chave` (a fase, a faixa, o nome do clube ou da pessoa, a categoria de ingresso, o grupo de despesa ou o código do bloco B1, B2 ou B3), `id_clube` (quando o escopo é clube ou artilheiro), `valor`, `unidade`. Percentuais estão de 0 a 100; dinheiro em reais com 2 casas; médias com até 4 casas.

Conferir uma medida DAX: filtrar a linha pelo `id_indicador` e pelo escopo, e comparar. Tolerância: **igual** para contagens e dinheiro; diferença menor que 0,0001 para médias e percentuais.

## Cuidados e limitações (leia antes de mostrar um número)

- **Gols e minutos:** o autor do gol e o minuto vêm da súmula, com uma correção documentada: no jogo 15 o 3º gol está aos 60' na súmula e aos 76' em outras fontes, e foi corrigido para 76' (C01), então ele conta na faixa 76-90+. Em um gol do jogo 8 o crédito difere entre as fontes (gol normal na súmula, gol contra na ESPN); vale a súmula. Com a correção, as faixas somam 22, 22, 24, 27, 26 e 47 (168 gols).
- **Jogo 47 (A33 aberta):** a súmula tem os horários de início e fim dos tempos zerados. Os acréscimos (3 e 7 minutos) estão preenchidos e entram em I23; nenhum indicador usa o relógio real do jogo. Se um dia houver "duração do jogo", excluir o jogo 47.
- **Taxa de ocupação do estádio não existe:** `dim_estadio.capacidade` está vazia (A32 aberta) por falta de fonte verificada. Não mostrar ocupação até haver fonte citada.
- **Estatísticas do jogo da ESPN** (posse, finalizações, faltas, escanteios, passes etc., em `fato_estatistica_time`) **não têm conferência oficial possível**. Podem aparecer no dashboard, rotuladas como "fonte: ESPN, não conferida". Os cartões da ESPN foram deixados de fora de propósito.
- **Cartões:** sempre a regra da FPF (I20 e I21). Por isso 385 e 28, e não os 383 e 24 da ESPN.
- **Disputa de pênaltis:** aparece em `fato_partida.penaltis_mandante` e `penaltis_visitante` (1 jogo: Corinthians 8 x 7 Portuguesa, nas quartas). O placar da disputa é o da súmula ("Resultado Pênalti") e quem venceu é confirmado pela FPF (colunas VP e DP, regra A15, que também compara com a contagem da ESPN); as cobranças uma a uma só vêm da ESPN. Não entra em gols, vitórias nem artilharia.
- **Categorias de ingresso e grupos de despesa (I38 por grupo, I45 a I50) são classificação do projeto, não oficial.** Saem de regras em `data/referencia/ingresso_categorias.csv` e `despesa_grupos.csv`; o boletim só traz os setores como cada estádio os escreve (855 rótulos) e os três blocos B1, B2 e B3 (estes, sim, oficiais). Se uma linha dos arquivos mudar, esses indicadores mudam.
- **Torcida visitante (I41, I42, I53, I54) é estimativa:** conta os ingressos de setores cujo nome cita "visitante"; nenhuma fonte traz a torcida visitante de outro jeito.
- **Despesa e retenções (I38):** as linhas "11% INSS ..." que o boletim traz depois do total das despesas não entram em I38 nem na renda líquida.
- **Elenco (I55 a I59)** vem só da súmula. "Atleta-jogo" é um atleta em um jogo (o mesmo atleta em 10 jogos conta 10). O gol de reserva conta gol de jogo, de pênalti e de falta, não o gol contra.

## Glossário

- **Súmula:** documento oficial do árbitro com gols, cartões, horários e arbitragem de cada jogo. Fonte oficial.
- **Boletim financeiro:** documento oficial com ingressos vendidos, público pagante, renda e despesas de cada jogo.
- **Advertência:** cartão amarelo mostrado a atleta ou a integrante da comissão técnica.
- **Segundo amarelo:** segundo cartão amarelo ao mesmo atleta no jogo, que o expulsa; conta como um vermelho (e o primeiro amarelo deixa de contar) na tabela da FPF.
- **Renda bruta e líquida:** arrecadação de ingressos, e o que sobra depois de descontadas as despesas do jogo.
- **Art. 16:** artigo do regulamento que fixa o desempate na primeira fase: vitórias, saldo, gols marcados, menos vermelhos, menos amarelos, sorteio.
- **VP e DP:** vitórias e derrotas nos pênaltis (colunas da tabela oficial).
- **Acréscimo:** minutos adicionados pelo árbitro ao final de cada tempo.
