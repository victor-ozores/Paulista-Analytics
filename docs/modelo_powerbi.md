# Modelo do Power BI: relacionamentos

Gerado por `scripts/09_gerar_relacionamentos.py` (não editar à mão: mude a lista `R` do script e rode de novo). As tabelas vêm de `docs/powerquery.md`; o desenho segue `docs/contrato_dados.md`.

## Desenho (estrela)

```
dim_competicao 1─N dim_fase 1─N fato_partida N─1 dim_calendario (data_jogo)
                                      │ N─1 dim_estadio   N─1 dim_arbitro (árbitro principal)
                                      ├─1─N fato_evento N─1 dim_clube (clube da pessoa)
                                      ├─1─N fato_estatistica_time N─1 dim_clube
                                      ├─1─N fato_escalacao N─1 dim_clube, N─1 dim_atleta
                                      ├─1─N fato_substituicao N─1 dim_clube, N─1 dim_atleta (quem entrou)
                                      ├─1─N fato_comissao N─1 dim_clube
                                      ├─1─N fato_ingresso | fato_despesa (só o jogo)
                                      ├─1─N fato_rateio N─1 dim_clube
                                      └─1─N fato_inconsistencia N─1 dim_clube, N─1 resultado_regra
dim_clube 1─N dim_clube_alias | fato_classificacao_oficial (também N─1 dim_fase) | ref_classificacao_primeira_fase
aux_config e ref_indicadores: sem relacionamento (consulta direta)
```

Todas as relações são muitos-para-um, filtro em uma direção (do lado um para o lado muitos).

## Relacionamentos ativos (28)

| De (muitos) | Para (um) | Para quê |
|---|---|---|
| `dim_fase[id_competicao]` | `dim_competicao[id_competicao]` | a fase pertence à competição |
| `fato_partida[id_fase]` | `dim_fase[id_fase]` | o jogo pertence a uma fase |
| `fato_partida[data_jogo]` | `dim_calendario[data]` | a data do jogo no calendário |
| `fato_partida[id_estadio]` | `dim_estadio[id_estadio]` | o estádio do jogo |
| `fato_partida[id_arbitro]` | `dim_arbitro[id_arbitro]` | o árbitro principal do jogo |
| `fato_evento[id_partida]` | `fato_partida[id_partida]` | o evento (gol, cartão) pertence a um jogo |
| `fato_evento[id_clube]` | `dim_clube[id_clube]` | o clube da pessoa do evento (quem fez o gol, quem recebeu o cartão) |
| `fato_estatistica_time[id_partida]` | `fato_partida[id_partida]` | a estatística do time pertence a um jogo |
| `fato_estatistica_time[id_clube]` | `dim_clube[id_clube]` | o clube da estatística |
| `dim_clube_alias[id_clube]` | `dim_clube[id_clube]` | nomes alternativos do clube |
| `fato_classificacao_oficial[id_clube]` | `dim_clube[id_clube]` | o clube da linha da tabela oficial |
| `fato_classificacao_oficial[id_fase]` | `dim_fase[id_fase]` | a fase da tabela oficial |
| `ref_classificacao_primeira_fase[id_clube]` | `dim_clube[id_clube]` | gabarito da classificação calculada em Python |
| `fato_inconsistencia[id_clube]` | `dim_clube[id_clube]` | clube da ocorrência (quando há) |
| `fato_inconsistencia[id_partida]` | `fato_partida[id_partida]` | jogo da ocorrência (quando há) |
| `fato_inconsistencia[codigo_regra]` | `resultado_regra[codigo]` | a regra que gerou a ocorrência |
| `fato_escalacao[id_partida]` | `fato_partida[id_partida]` | a linha da relação de jogadores pertence a um jogo |
| `fato_escalacao[id_clube]` | `dim_clube[id_clube]` | o clube da relação de jogadores |
| `fato_escalacao[id_atleta]` | `dim_atleta[id_atleta]` | o atleta relacionado |
| `fato_substituicao[id_partida]` | `fato_partida[id_partida]` | a substituição pertence a um jogo |
| `fato_substituicao[id_clube]` | `dim_clube[id_clube]` | o clube que fez a substituição |
| `fato_substituicao[id_atleta_entrou]` | `dim_atleta[id_atleta]` | o atleta que entrou (ativa: um atleta só tem um caminho ativo até a substituição) |
| `fato_comissao[id_partida]` | `fato_partida[id_partida]` | a comissão técnica pertence a um jogo |
| `fato_comissao[id_clube]` | `dim_clube[id_clube]` | o clube da comissão técnica |
| `fato_ingresso[id_partida]` | `fato_partida[id_partida]` | a linha de ingresso do boletim pertence a um jogo |
| `fato_despesa[id_partida]` | `fato_partida[id_partida]` | a rubrica de despesa do boletim pertence a um jogo |
| `fato_rateio[id_partida]` | `fato_partida[id_partida]` | a divisão da renda líquida é de um jogo |
| `fato_rateio[id_clube]` | `dim_clube[id_clube]` | o clube que recebe (ou não) a parte da renda líquida |

## Relacionamentos inativos (11)

| De (muitos) | Para (um) | Para quê |
|---|---|---|
| `fato_partida[id_clube_mandante]` | `dim_clube[id_clube]` | clube mandante (inativa: ver ambiguidade) |
| `fato_partida[id_clube_visitante]` | `dim_clube[id_clube]` | clube visitante (inativa: ver ambiguidade) |
| `fato_partida[id_assistente1]` | `dim_arbitro[id_arbitro]` | assistente 1 |
| `fato_partida[id_assistente2]` | `dim_arbitro[id_arbitro]` | assistente 2 |
| `fato_partida[id_quarto_arbitro]` | `dim_arbitro[id_arbitro]` | quarto árbitro |
| `fato_partida[id_var]` | `dim_arbitro[id_arbitro]` | árbitro de vídeo (VAR) |
| `fato_partida[id_avar1]` | `dim_arbitro[id_arbitro]` | assistente de vídeo 1 (AVAR) |
| `fato_partida[id_avar2]` | `dim_arbitro[id_arbitro]` | assistente de vídeo 2 (AVAR) |
| `fato_evento[id_clube_creditado]` | `dim_clube[id_clube]` | clube que recebe o gol no placar (difere do clube da pessoa só no gol contra) |
| `fato_substituicao[id_atleta_saiu]` | `dim_atleta[id_atleta]` | o atleta que saiu (inativa; entra nas medidas com USERELATIONSHIP) |
| `dim_atleta[id_clube]` | `dim_clube[id_clube]` | clube do atleta na temporada (inativa: o clube já chega à escalação direto, e dois caminhos ativos seriam ambíguos) |

## Por que o clube não se liga ativamente à partida

Se `fato_partida[id_clube_mandante]` fosse ativa, o filtro de um clube chegaria a `fato_evento` por **dois caminhos**: direto (`fato_evento[id_clube]`) e via partida. O Power BI não aceita caminhos ambíguos. A escolha foi manter o clube ligado direto aos fatos de grão clube (eventos, estatísticas, classificação, ocorrências) e deixar as relações com a partida inativas.
Isso combina com o futebol: "jogos do clube" é mandante **ou** visitante, então de qualquer forma precisa de duas contas. As medidas ativam a relação que querem com `USERELATIONSHIP`:

```dax
Jogos do clube =
    CALCULATE(COUNTROWS(fato_partida), USERELATIONSHIP(fato_partida[id_clube_mandante], dim_clube[id_clube]))
  + CALCULATE(COUNTROWS(fato_partida), USERELATIONSHIP(fato_partida[id_clube_visitante], dim_clube[id_clube]))
```

## Outros papéis repetidos

`dim_arbitro` é uma dimensão de pessoas que a partida usa em 7 papéis (árbitro, assistentes, quarto árbitro, VAR e AVAR). Só o árbitro principal é ativo; os outros 6 são inativos e entram por `USERELATIONSHIP`. `fato_evento[id_clube_creditado]` é inativa: difere de `id_clube` só no gol contra (o gol vale para o adversário de quem fez).

## Atletas, substituições e financeiro

- `dim_atleta[id_clube]` é **inativa**: o clube já chega a `fato_escalacao` direto (`fato_escalacao[id_clube]`); com a relação do atleta ativa haveria dois caminhos de `dim_clube` até a escalação (direto e pelo atleta).
- `fato_substituicao` tem **dois** papéis de atleta: `id_atleta_entrou` é ativa e `id_atleta_saiu` é inativa (`USERELATIONSHIP` quando a medida quiser quem saiu).
- `fato_ingresso` e `fato_despesa` ligam só ao jogo; as medidas de clube (como mandante ou visitante) usam `USERELATIONSHIP` na partida e o filtro segue da partida para os ingressos e as despesas. `fato_rateio` liga ao jogo e ao clube (o clube que recebe), como `fato_evento`.

## Linhas sem clube e o membro "(Em branco)" de `dim_clube`

`fato_inconsistencia` (8 das 46 linhas) e `ref_indicadores` (251 das 586) têm `id_clube` vazio: são ocorrências e indicadores gerais, que não pertencem a nenhum clube. Não há chave órfã (nenhum valor fora de `dim_clube`). No Power BI, porém, linhas sem chave aparecem sob o membro **"(Em branco)"** de `dim_clube`: uma consulta DAX que lista as medidas por clube mostra uma 17ª linha vazia (as medidas que terminam em `+ 0` a mantêm com valor 0). O dashboard em HTML não usa essas consultas; só importa a quem montar um visual novo por clube, que deve filtrar o membro em branco.

## Tabelas do modelo

A descrição de cada tabela também fica salva no próprio Power BI (aparece ao passar o mouse sobre a tabela no painel Campos). Texto em `DESCRICAO_TABELAS` deste script; a de `aux_dashboard` vem de `scripts/14_gerar_medida_dashboard.py`.

| Tabela | O que guarda |
|---|---|
| `dim_competicao` | Competição: Paulistão A1 2026 (campeonato 73 e categoria 39 da FPF), com datas de início e fim e total de jogos. Fonte: FPF. |
| `dim_fase` | Fases do campeonato: 1ª fase em pontos corridos, quartas de final, semifinal e final. Fonte: FPF. |
| `dim_clube` | Clubes: nome, sigla, cores e o escudo oficial reduzido em base64 (escudo_base64). Escudo e nomes: FPF; sigla e cor provisórias: ESPN (não oficial). |
| `dim_clube_alias` | Nomes alternativos de cada clube nas fontes (FPF, ESPN, Wikipédia), usados para casar os registros entre fontes. |
| `dim_estadio` | Estádios, com município e número de jogos. Capacidade vazia: sem fonte verificada (regra A32 aberta). Fonte: FPF. |
| `dim_arbitro` | Pessoas da arbitragem (árbitro, assistentes, quarto árbitro, VAR e AVAR), com a quantidade de jogos em cada papel. Fonte: súmulas da FPF. |
| `dim_calendario` | Calendário de 2026, um dia por linha, com dia da semana, trimestre e se houve jogo no dia. |
| `fato_partida` | Um jogo por linha: placar, pênaltis, estádio, público e renda (boletim financeiro), arbitragem e horários (súmula). Chave: id_partida. Fonte: FPF, inclusive o placar da disputa de pênaltis do jogo 68. |
| `fato_evento` | Gols, cartões e cobranças da disputa de pênaltis, com minuto, camisa, pessoa e motivo do cartão. Gols e cartões vêm da súmula da FPF; as 15 cobranças da disputa, da ESPN (o placar da disputa é o da súmula). Tem uma correção documentada (C01). |
| `fato_estatistica_time` | Estatísticas de cada time em cada jogo: posse de bola, finalizações, faltas, escanteios e outras. Fonte: ESPN (não oficial). |
| `fato_classificacao_oficial` | Classificação oficial da FPF por fase. Serve para conferir a classificação calculada pelas medidas. |
| `ref_classificacao_primeira_fase` | Classificação da 1ª fase calculada em Python pelo Art. 16, uma linha por clube; gabarito das medidas de classificação. |
| `aux_config` | Parâmetros da carga: versão do pipeline, datas da coleta e da atualização da FPF e hashes dos arquivos de referência. |
| `fato_inconsistencia` | Log de conferência: uma linha por divergência achada pelas regras, com as duas fontes, o status (aberta, explicada, aceita ou corrigida) e a explicação. |
| `resultado_regra` | Resultado de cada regra de conferência: código, título, itens verificados, ocorrências e resultado (ok, explicada, aberta ou info). |
| `dim_atleta` | Atletas da súmula oficial: nome como a FPF escreve, apelido de quem fez gol, nome curto e clube na temporada. Chave: id_atleta (identificador do nome completo). Fonte: súmulas da FPF. |
| `fato_escalacao` | Relação de jogadores de cada time em cada jogo: titular ou reserva, se jogou, minutos, gols e cartões. Gols e cartões ligados ao atleta por jogo, clube e camisa. Fonte: súmulas da FPF. |
| `fato_substituicao` | Substituições de cada jogo (regulares e por concussão): quem saiu, quem entrou, período e minuto. Fonte: súmulas da FPF. |
| `fato_comissao` | Comissão técnica de cada clube em cada jogo: técnico, auxiliar, médico, massagista, preparador físico e treinador de goleiros. Cargo sem nome na súmula não entra. Fonte: súmulas da FPF. |
| `fato_ingresso` | Linhas da tabela de ingressos do boletim financeiro: setor e tipo de ingresso, quantidade, preço e arrecadação, com a categoria do projeto (classificação não oficial) e a marca de setor de visitante. Fonte: boletins da FPF. |
| `fato_despesa` | Rubricas de despesa de cada jogo nos blocos B1, B2 e B3 do boletim, com o grupo do projeto (agrupamento não oficial) e o valor. Fonte: boletins da FPF. |
| `fato_rateio` | Divisão da renda líquida de cada jogo (dois clubes por jogo): percentual, valor, deduções e líquido a receber. Em 2026 o mandante fica com 100%. Fonte: boletins da FPF. |
| `ref_indicadores` | Valores de referência calculados em Python (indicadores I01 a I59 por escopo). Servem de gabarito para conferir as medidas; não é tabela de análise. |
| `_Medidas` | Medidas DAX do dashboard, em pastas numeradas. Sem dados. Cada medida tem descrição; definições em docs/medidas_dax.md. |
| `aux_dashboard` | Tabela técnica do dashboard: guarda as medidas que montam o HTML do visual HTML Content (código e dados das quatro telas em pedaços de até 8.000 caracteres). Sem dados de negócio. |

## Conferências feitas na geração

- As colunas existem nos CSV e o lado "um" é único e sem vazio.
- Todo valor do lado "muitos" existe no lado "um" (sem órfãos), inclusive nas relações inativas.
- Nenhum par de tabelas tem dois caminhos ativos.
