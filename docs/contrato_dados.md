# Contrato de dados

As 20 tabelas do tratamento são geradas por `scripts/04_tratar.py` a partir dos CSV de `data/processed/fpf/` (que `scripts/03b_ler_fpf_pdf.py` grava depois de ler os PDFs oficiais) e dos arquivos de referência de `data/referencia/`; as 3 de qualidade (log de conferência, resultado das regras e indicadores de referência) saem de `scripts/05_validar.py`. A saída fica em `data/processed/` (não versionada; recriável). Validado para a A1 2026 por verificação de integridade no próprio tratamento e por `tests/test_tratar.py`, `tests/test_escalacao.py`, `tests/test_financeiro.py` e `tests/test_validar.py`. No modelo do Power BI as 23 tabelas de dados (20 do tratamento mais 3 de qualidade) são carregadas por consultas do Power Query e a carga foi conferida coluna a coluna contra o tratamento (271 de 271 colunas iguais).

Convenções: snake_case; CSV UTF-8 sem BOM, separador `;`, fim de linha LF, ponto decimal, vazio = ausente; datas `AAAA-MM-DD`; data e hora `AAAA-MM-DDTHH:MM`. Chave de clube = código oficial da FPF (`id_clube`). Chave de partida = `id_jogo` da FPF (`id_partida`). Estádios e pessoas da arbitragem usam chave de texto estável (`slug` do nome), que não muda quando a lista cresce.

## Esquema estrela

```
dim_competicao 1─N dim_fase 1─N fato_partida N─1 dim_calendario (data_jogo)
dim_clube 1─N fato_partida (mandante e visitante: as DUAS inativas no Power BI; ver docs/modelo_powerbi.md)
dim_estadio 1─N fato_partida       dim_arbitro 1─N fato_partida (7 papéis; só id_arbitro ativa)
fato_partida 1─N fato_evento       fato_partida 1─N fato_estatistica_time
fato_partida 1─N fato_escalacao    dim_clube 1─N fato_escalacao      dim_atleta 1─N fato_escalacao
fato_partida 1─N fato_substituicao dim_clube 1─N fato_substituicao   dim_atleta 1─N fato_substituicao (2 papéis: saiu e entrou)
fato_partida 1─N fato_comissao     dim_clube 1─N fato_comissao       dim_clube 1─N dim_atleta
fato_partida 1─N fato_ingresso     fato_partida 1─N fato_despesa     fato_partida 1─N fato_rateio      dim_clube 1─N fato_rateio
dim_clube 1─N fato_evento (id_clube; id_clube_creditado é 2ª relação)    dim_clube 1─N fato_estatistica_time
dim_clube 1─N dim_clube_alias      fato_classificacao_oficial N─1 dim_clube, dim_fase
ref_classificacao_primeira_fase N─1 dim_clube     aux_config (independente)
fato_inconsistencia N─1 dim_clube, fato_partida (ambos opcionais)   resultado_regra 1─N fato_inconsistencia (codigo)
ref_indicadores (independente; gabarito dos números, sem relação no modelo)
```

## Tabelas (23)

| Tabela | Linhas (A1 2026) | Grão |
|---|---|---|
| `dim_competicao` | 1 | campeonato e ano |
| `dim_fase` | 4 | fase |
| `dim_clube` | 16 | clube |
| `dim_clube_alias` | 56 | nome alternativo de clube |
| `dim_estadio` | 16 | estádio |
| `dim_arbitro` | 80 | pessoa da arbitragem (árbitro, assistentes, quarto árbitro, VAR e AVAR) |
| `dim_calendario` | 365 | dia do ano |
| `fato_partida` | 72 | jogo |
| `fato_evento` | 600 | gol, cartão ou cobrança da disputa de pênaltis |
| `fato_estatistica_time` | 144 | time em um jogo |
| `dim_atleta` | 505 | atleta (pelo nome completo da súmula) |
| `fato_escalacao` | 3.292 | atleta relacionado em um jogo (titular ou reserva, use ou não) |
| `fato_substituicao` | 706 | substituição em um jogo (regular ou por concussão) |
| `fato_comissao` | 1.066 | pessoa da comissão técnica de um clube em um jogo (cargo sem nome na súmula não entra) |
| `fato_ingresso` | 2.388 | linha da tabela de ingressos do boletim financeiro (um setor e tipo de ingresso em um jogo) |
| `fato_despesa` | 1.482 | rubrica de despesa de um jogo (valor diferente de zero) |
| `fato_rateio` | 144 | clube na divisão da renda líquida de um jogo (dois por jogo) |
| `fato_classificacao_oficial` | 30 | clube em uma fase (tabela oficial da FPF) |
| `ref_classificacao_primeira_fase` | 16 | clube (classificação calculada em Python pelo Art. 16; gabarito do DAX) |
| `aux_config` | 13 | parâmetro |
| `fato_inconsistencia` | 46 | ocorrência de divergência encontrada por uma regra |
| `resultado_regra` | 45 | regra de conferência |
| `ref_indicadores` | 586 | valor de referência de um indicador em um escopo |

## Colunas

**dim_competicao:** `id_competicao` (PK, `PAULISTA-A1-2026`), `id_campeonato_fpf` (73), `id_categoria_fpf` (39), `exercicio`, `nome` (Paulistão Casas Bahia), `serie`, `categoria`, `data_inicio`, `data_fim`, `total_jogos`, `atualizado_fpf_em`.

**dim_fase:** `id_fase` (PK; 7756, 7757, 7758, 7759), `id_competicao`, `nome_fase`, `ordem`, `tipo` (`pontos_corridos` na 1ª; `mata_mata` nas demais), `jogos`.

**dim_clube:** `id_clube` (PK), `nome_popular`, `nome_oficial`, `sigla` (da ESPN; 3 a 4 letras, única), `cor_hex` (cor da ESPN, ou a alternativa quando a principal é quase preta), `cor_espn`, `cor_alternativa_espn`, `id_espn`, `url_escudo`, `arquivo_escudo` (`escudos/{id}.png`, relativo a `data/processed/`), `escudo_largura`, `escudo_altura`, `escudo_bytes`, `tem_escudo`. As cores e siglas vêm da ESPN (não oficiais).

**dim_clube_alias:** `alias`, `alias_normalizado`, `id_clube`, `fonte` (FPF, ESPN, Wikipédia). Resolve nomes diferentes entre fontes (ex.: "Primavera SAF", "Primavera SP", "Primavera").

**dim_estadio:** `id_estadio` (PK, slug do nome da FPF), `nome_fpf`, `nome_espn`, `municipio`, `capacidade` (**vazia: sem fonte verificada**), `fonte_capacidade`, `jogos`.

**dim_arbitro:** `id_arbitro` (PK, slug do nome na súmula), `nome`, `jogos_arbitro`, `jogos_assistente`, `jogos_quarto_arbitro`, `jogos_var`.

**dim_calendario:** `data` (PK), `ano`, `mes`, `nome_mes`, `dia`, `dia_semana` (1 = segunda), `nome_dia_semana`, `semana_iso`, `trimestre`, `dia_de_jogo`. Cobre o ano inteiro da competição.

**fato_partida:** `id_partida` (PK), `numero_jogo` (usado nos endereços dos PDFs), `id_competicao`, `id_fase`, `rodada`, `grupo`, `data_jogo`, `hora_programada`, `data_hora_programada` (FPF, horário de Brasília), `id_clube_mandante`, `id_clube_visitante`, `gols_mandante`, `gols_visitante` (tempo regulamentar), `penaltis_mandante`, `penaltis_visitante` (só em jogo decidido nos pênaltis; vêm da linha "Resultado Pênalti" da súmula), `id_estadio`, `publico_boletim` (ingressos vendidos), `publico_pagante`, `renda_bruta`, `despesas_total`, `renda_liquida` (pode ser negativa), `publico_espn` (conferência), `id_arbitro`, `id_assistente1`, `id_assistente2`, `id_quarto_arbitro`, `id_var`, `id_avar1`, `id_avar2`, `inicio_1t`, `termino_1t`, `atraso_1t_min`, `acrescimo_1t_min`, `inicio_2t`, `termino_2t`, `atraso_2t_min`, `acrescimo_2t_min`, `publicada_em` (súmula), `id_evento_espn`.

**fato_evento:** `id_evento` (PK, `{id_partida}-{nn}`, em ordem cronológica), `id_partida`, `id_clube` (clube da pessoa), `id_clube_creditado` (clube que recebe o gol no placar; **difere de `id_clube` só no gol contra**), `tipo_evento` (`gol`, `gol_penalti`, `gol_falta`, `gol_contra`, `amarelo`, `segundo_amarelo`, `vermelho`, `penalti_disputa`), `funcao` (`Atleta`, `Técnico`, `Auxiliar Técnico`, ...), `numero_camisa`, `pessoa`, `apelido`, `minuto` (vazio em evento antes do jogo, no intervalo ou depois do jogo), `acrescimo`, `minuto_total`, `periodo` (`1T`, `2T`, `AJ`, `INT`, `PJ`, `PEN`), `motivo`, `fonte` (`SUMULA`; `ESPN` só na disputa de pênaltis), `id_correcao` (vazio; preenchido quando o valor foi corrigido por uma linha de `data/referencia/correcoes_dados.csv`, hoje só C01: minuto do 3º gol do jogo 15, de 60 para 76).
Regras: a súmula é a fonte. **Cobranças da disputa de pênaltis não são gols** (`tipo_evento = penalti_disputa`; as 15 cobranças convertidas são da ESPN, o placar da disputa é da súmula). Contagem oficial de cartões: amarelos = `amarelo` menos `segundo_amarelo`; vermelhos = `vermelho` mais `segundo_amarelo`.

**fato_estatistica_time** (ESPN, resumo da partida): `id_partida`, `id_clube`, `posse_pct`, `finalizacoes`, `finalizacoes_no_alvo`, `finalizacoes_bloqueadas`, `faltas`, `escanteios`, `impedimentos`, `passes`, `passes_certos`, `cruzamentos`, `cruzamentos_certos`, `desarmes`, `desarmes_certos`, `interceptacoes`, `cortes`, `defesas_goleiro`. **Cartões da ESPN foram deixados de fora de propósito** (incompletos).

**dim_atleta** (súmula): `id_atleta` (PK, `slug` do nome completo como a súmula escreve), `nome` (cortado em 33 caracteres pela FPF), `nome_truncado` (1 se o nome tem 33 ou mais caracteres e pode estar cortado), `apelido` (nome entre parênteses na linha de gols da súmula, vazio para quem nunca fez gol), `nome_curto` (apelido ou primeiro nome mais último sobrenome; aproximação), `id_clube` (clube do atleta na temporada; se houvesse mais de um, o de mais jogos), `registros` (números de registro da FPF vistos, separados por `; `; 9 atletas têm dois).

**fato_escalacao** (súmula, "Relação de Jogadores"): `id_escalacao` (PK, `{id_partida}-{id_clube}-{camisa}`), `id_partida`, `id_clube`, `id_atleta`, `numero_camisa` (muda de jogo para jogo), `situacao` (`titular`, `reserva`), `vinculo` (`profissional`, `amador`), `registro`, `jogou` (1 para os 11 titulares e para o reserva que entrou), `periodo_entrada` / `minuto_entrada` / `acrescimo_entrada` (titular: `1T`, 0, 0; reserva: o da substituição, `INT` sem minuto no intervalo; vazio se não entrou), `periodo_saida` / `minuto_saida` / `acrescimo_saida` (só se foi substituído; vazio se ficou até o fim ou até a expulsão), `minutos_jogados` (convenção: de 0 a 90, sem acréscimos, até a expulsão), `gols` (de jogo, pênalti ou falta), `gols_contra`, `amarelos` e `vermelhos` (regra da FPF: amarelos = advertências menos segundos amarelos; vermelhos = diretos mais segundos amarelos). Gols e cartões são ligados ao atleta por `(partida, clube, camisa)`.
Regras: `sum(gols) + gols_contra do adversário` fecha o placar em 144 de 144 equipes-jogo; a soma de `minutos_jogados` de uma equipe-jogo é 990 menos os minutos perdidos por expulsão.

**fato_substituicao** (súmula, "Substituições" e "Substituições por concussão"): `id_substituicao` (PK, `{id_partida}-{id_clube}-{nn}`, `nn` = ordem no tempo dentro do time), `id_partida`, `id_clube`, `ordem`, `tipo` (`regular`; `concussao` = bloco de concussão da súmula, que traz também a substituição adicional do adversário), `id_atleta_saiu`, `id_atleta_entrou` (vazios se a camisa não consta na relação, o que a regra A36 aponta), `numero_saiu`, `numero_entrou`, `periodo` (`1T`, `INT`, `2T`), `minuto` (vazio no intervalo), `acrescimo` (45+n e 90+n entram como minuto 45 ou 90 com acréscimo n), `minuto_total`, `motivo` (texto livre, só no bloco de concussão).

**fato_comissao** (súmula, "Comissão Técnica"): `id_comissao` (PK, `{id_partida}-{id_clube}-{nn}`), `id_partida`, `id_clube`, `funcao` (`Técnico`, `Auxiliar Técnico`, `Médico`, `Massagista`, `Preparador Físico`, `Treinador de goleiro`), `nome` (a FPF corta nomes longos e põe `...`), `nome_truncado`. O técnico do Palmeiras no jogo 60 vem sem nome na súmula (regra A40, aceita). Cartões da comissão continuam em `fato_evento`.

**fato_ingresso** (boletim financeiro, tabela "Localidades"): `id_ingresso` (PK, `{id_partida}-{nn}`, `nn` = ordem da linha no boletim), `id_partida`, `ordem`, `localidade` (rótulo como o boletim escreve, "SETOR - tipo de ingresso"; 855 rótulos distintos em 2026), `categoria` (`Inteira`, `Meia-entrada`, `Sócio-torcedor`, `Cadeira e camarote`, `Gratuidade por lei`, `Outros`; sai das regras de `data/referencia/ingresso_categorias.csv`, vale a primeira que casar), `ordem_categoria` (1 a 6, só para ordenar), `setor_visitante` (1 se o rótulo cita visitante), `ingressos` (vendidos), `preco` (preço de cada ingresso), `arrecadacao`.
Regras: o boletim traz "à venda" sempre igual a "vendidos" e "devolvidos" sempre zero (2.388 de 2.388 linhas); por isso as duas colunas ficam só no arquivo bruto. Preço vezes ingressos dá a arrecadação em todas as linhas; `sum(ingressos)` é o `publico_boletim` e `sum(arrecadacao)` é a `renda_bruta` em 72 de 72 jogos (regra A42). Gratuidade é a linha de preço zero; as 257 trazem uma lei no rótulo (Lei estadual 18.159, menor de 2 anos, e leis municipais), o que a regra A45 confere.

**fato_despesa** (boletim, blocos B1, B2 e B3): `id_despesa` (PK, `{id_partida}-{bloco}-{nn}`), `id_partida`, `bloco_codigo` (`B1`, `B2`, `B3`), `bloco` (Aluguéis e seguros, Taxas e impostos, Despesas operacionais: os blocos do boletim), `ordem` (da linha dentro do bloco), `rubrica` (como o boletim escreve; 43 distintas em 2026), `grupo` (**agrupamento do projeto, não oficial**, 10 grupos; vem de `data/referencia/despesa_grupos.csv`; `Sem grupo` para rubrica nova, que a regra A45 aponta), `valor`. Só linhas diferentes de zero.
Regras: `sum(valor)` é a `despesas_total` do jogo e cada bloco fecha o `TOTAL B1/B2/B3` do boletim (regra A43). As linhas "11% INSS ..." que o boletim traz **depois** do total das despesas são retenções informadas e **não entram** na renda líquida (renda líquida = renda bruta menos despesas em 72 de 72; 10 jogos têm retenção diferente de zero): ficam no arquivo bruto `boletim_retencao.csv`, e a soma delas está em `boletim_partida.csv` (`retencao_inss_informada`). Em 6 jogos a rubrica "35% - RENDA BRUTA CLUBE VISITANTE" (bloco B2) é o repasse ao visitante.

**fato_rateio** (boletim, "Divisão da renda líquida"): `id_rateio` (PK, `{id_partida}-{id_clube}`), `id_partida`, `id_clube`, `lado` (`mandante`, `visitante`), `percentual`, `valor` (parte da renda líquida; negativa quando o jogo deu prejuízo), `deducao_inss`, `deducao_outras`, `liquido` (a receber: valor menos deduções).
Regras (A44): dois clubes por jogo, na ordem do boletim (mandante, visitante); percentuais somam 100; valores somam a renda líquida; líquido igual a valor menos deduções. Em 2026 o mandante fica com 100% e o visitante com 0% nos 72 jogos; 18 jogos têm dedução em "outras"; 15 jogos têm renda líquida negativa.

**Arquivos de referência do financeiro** (`data/referencia/`, versionados, revisáveis): `ingresso_categorias.csv` (`ordem_regra`, `categoria`, `ordem_exibicao`, `condicao` = `preco_zero`, `texto` ou `resto`, `expressao`, `explicacao`; as expressões valem sobre o rótulo sem acento e em minúsculas) e `despesa_grupos.csv` (`rubrica`, `bloco`, `grupo`; 43 linhas). Os dois entram nos `hash_*` de `aux_config`. Para mudar uma categoria ou um grupo basta editar o arquivo e rodar `04_tratar.py` e `05_validar.py`.

**Arquivo de referência dos motivos de cartão** (`data/referencia/motivos_cartao.csv`, versionado, revisável; usado só pela tela Disciplina e arbitragem, não pelo ETL): `ordem_regra`, `categoria`, `ordem_exibicao`, `condicao` = `texto` ou `resto`, `expressao` (vale sobre o motivo sem acento e em minúsculas), `explicacao` (a frase que vai na dica da tela). Vale a primeira regra que casar; a última (e só ela) é o `resto`. O texto livre do motivo não vai para a tela, só o grupo. Para mudar um grupo, edite o arquivo e rode `python scripts/13_montar_app.py` (ele para se mais de 5% dos cartões caírem em "Outros").

**fato_classificacao_oficial:** `id_fase`, `fase`, `grupo`, `posicao`, `id_clube`, `pontos`, `jogos`, `vitorias`, `empates`, `derrotas`, `gols_pro`, `gols_contra`, `saldo`, `vp`, `dp`, `amarelos`, `vermelhos`, `atualizado_em`. Cópia da tabela oficial; serve para **conferir** a classificação calculada no DAX.

**ref_classificacao_primeira_fase:** `posicao`, `id_clube`, `jogos`, `vitorias`, `empates`, `derrotas`, `gols_pro`, `gols_contra`, `saldo`, `pontos`, `aproveitamento`, `amarelos`, `vermelhos`, `empate_total` (1 se nem os critérios do Art. 16 desempatam). Gabarito em Python (`scripts/classificacao.py`) para validar as medidas DAX.

**aux_config:** `chave`, `valor` (versão do pipeline, temporada, datas de coleta e de atualização da FPF, hashes dos arquivos de referência, `gerado_em`).

**fato_inconsistencia** (log de conferência): `id_inconsistencia` (PK, `{codigo_regra}-{nnn}`, a numeração depende da ordem em que a regra encontra as ocorrências e pode mudar quando os dados mudam), `codigo_regra`, `titulo_regra`, `id_partida` e `numero_jogo` (vazios se a ocorrência não é de um jogo), `id_clube` (vazio se não é de um clube), `fonte_a`, `valor_a`, `fonte_b`, `valor_b` (o que cada fonte diz), `detalhe`, `severidade` (`alta`, `media`, `baixa`), `status` (`aberta`, `explicada`, `corrigida`, `aceita`) e `explicacao`. Status e explicação vêm de `data/referencia/inconsistencias_decisoes.csv`; sem decisão, a ocorrência é `aberta`. **Sem data por linha de propósito**: assim o arquivo é idêntico quando nada muda; o dia da execução está no cabeçalho do relatório de auditoria gerado por `scripts/05_validar.py`.

**resultado_regra:** `codigo`, `titulo`, `severidade`, `verificados` (quantos itens a regra olhou), `ocorrencias`, `abertas`, `explicadas`, `corrigidas`, `aceitas`, `resultado` (`ok`, `explicada`, `aberta`, `info`) e `resumo`.

**ref_indicadores:** `id_indicador` (I01 a I59), `indicador`, `escopo` (`geral`, `fase`, `faixa_minuto`, `clube`, `artilheiro`, `qualidade`, `categoria`, `grupo_despesa`, `bloco`), `chave`, `id_clube`, `valor`, `unidade`. Definições e fórmulas em `docs/dicionario_indicadores.md`. É o **gabarito** das medidas DAX; não entra no modelo do Power BI como tabela de análise.

## Escudos

`data/processed/escudos/{id_clube}.png`: PNG reduzido a no máximo 128 px e 96 cores (1,5 a 5 KB cada; 51 KB no total), feito a partir do escudo oficial da FPF baixado em `data/raw/escudos/`. Folha de conferência visual: `data/processed/escudos/conferir_escudos.html`. Escudo é marca do clube.

## Garantias verificadas a cada execução

Chaves únicas (inclusive as 4 tabelas de elenco e as 3 do financeiro; camisa repetida na relação de um time para o ETL); todas as chaves estrangeiras existem; para cada jogo, a soma dos ingressos é o público do boletim, a soma da arrecadação é a renda bruta e a soma das despesas é o total das despesas; 72 jogos, 16 clubes, 16 estádios, 4 fases; gols dos eventos creditados a cada clube iguais ao placar; total de 168 gols; público do boletim igual ao da ESPN (784.369); classificação calculada igual à oficial (posição e valores); cartões por clube e fase iguais aos da FPF (30 de 30). Se algo falhar, o script termina com erro e lista o problema. A validação acrescenta 45 regras de conferência entre fontes e entre tabelas, registradas em `fato_inconsistencia`; as regras A35 a A41 conferem a escalação (11 titulares, substituições, gols e cartões ligados à relação, técnico, registros) e A42 a A45 conferem o financeiro (ingressos, despesas, divisão da renda e classificação em categorias e grupos).

## Medidas que o dashboard usa (resumo)

Jogos, gols, gols por jogo, % mandante/empate/visitante, público total, médio e pagante, renda bruta, líquida e ticket médio, cartões por jogo (regra da FPF), acréscimos médios, classificação com desempate do Art. 16, aproveitamento (`pontos / (3 × jogos)`), posição por rodada, gols por faixa de minuto (sem disputa de pênaltis), % de conferência com a FPF.
