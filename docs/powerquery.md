# Power Query: como o Power BI carrega os dados

Gerado por `scripts/08_gerar_powerquery.py` (não editar à mão: rode o script de novo). As consultas ficam em `powerbi/PaulistaAnalytics.SemanticModel/definition/tables/`.

## Princípio

O Power Query é **fino**: carrega cada CSV de `data/processed/` e define os tipos. Limpeza, conferência e regras de negócio não estão aqui: estão em Python (ETL, regras de conferência e testes) e no DAX. Assim cada regra existe em um lugar só.

## Parâmetro

`CaminhoDados` (texto) = pasta dos CSV. Valor: a pasta `data/processed` do projeto (ajuste ao caminho da sua máquina em Página Inicial > Transformar dados > Gerenciar parâmetros).

## Padrão de cada consulta

1. `Origem`: `Csv.Document(File.Contents(CaminhoDados & "\tabela.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv])` (separador ponto e vírgula, UTF-8, aspas CSV).
2. `Cabecalho`: a primeira linha vira o nome das colunas.
3. `Vazios`: texto vazio (`""`) vira nulo. Sem isso o Power BI trata `""` como valor preenchido e `ISBLANK` falha.
4. `Tipos`: tipos explícitos com a cultura **en-US**. Isso é obrigatório: os números usam ponto decimal (`28580.00`) e, lidos em português, virariam 2.858.000. Por isso a detecção automática de tipos não é usada.
5. `DatasHoras` (só onde há data e hora): `DateTime.FromText` com o formato exato do CSV.

Os tipos vêm do próprio conteúdo dos CSV, com ajustes manuais no script (`FORCAR`): todo dinheiro como decimal fixo (`renda_bruta`, `despesas_total` e `renda_liquida` da partida; `preco` e `arrecadacao` de `fato_ingresso`; `valor` de `fato_despesa`; `valor`, `deducao_inss`, `deducao_outras` e `liquido` de `fato_rateio`), para as somas fecharem no centavo; `dim_estadio.capacidade` como inteiro (hoje vazia); `fato_partida.publicada_em` como data e hora no formato `dd/MM/yyyy HH:mm`.

## Escudos

`dim_clube` ganha a coluna `escudo_base64`: o conteúdo de cada PNG reduzido (`data/processed/escudos/`) em base64, para a interface montar `data:image/png;base64,...` sem depender de URL externa.

## Tabelas

| Tabela | Linhas | Colunas |
|---|---|---|
| `dim_competicao` | 1 | 11 |
| `dim_fase` | 4 | 6 |
| `dim_clube` | 16 | 14 (+1 escudo_base64) |
| `dim_clube_alias` | 56 | 4 |
| `dim_estadio` | 16 | 7 |
| `dim_arbitro` | 80 | 6 |
| `dim_calendario` | 365 | 10 |
| `dim_atleta` | 505 | 7 |
| `fato_partida` | 72 | 39 |
| `fato_evento` | 600 | 16 |
| `fato_estatistica_time` | 144 | 18 |
| `fato_escalacao` | 3292 | 20 |
| `fato_substituicao` | 706 | 14 |
| `fato_comissao` | 1066 | 6 |
| `fato_ingresso` | 2388 | 10 |
| `fato_despesa` | 1482 | 8 |
| `fato_rateio` | 144 | 9 |
| `fato_classificacao_oficial` | 30 | 18 |
| `ref_classificacao_primeira_fase` | 16 | 14 |
| `aux_config` | 13 | 2 |
| `fato_inconsistencia` | 46 | 14 |
| `resultado_regra` | 45 | 11 |
| `ref_indicadores` | 586 | 7 |

## Consultas (M) e tipos

### dim_competicao

1 linhas. Tipos: `id_competicao` string, `id_campeonato_fpf` int64, `id_categoria_fpf` int64, `exercicio` int64, `nome` string, `serie` string, `categoria` string, `data_inicio` date, `data_fim` date, `total_jogos` int64, `atualizado_fpf_em` datetime

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_competicao.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_competicao", type text}, {"id_campeonato_fpf", Int64.Type}, {"id_categoria_fpf", Int64.Type}, {"exercicio", Int64.Type}, {"nome", type text}, {"serie", type text}, {"categoria", type text}, {"data_inicio", type date}, {"data_fim", type date}, {"total_jogos", Int64.Type}}, "en-US"),
    DatasHoras = Table.TransformColumns(Tipos, {{"atualizado_fpf_em", each if _ = null then null else DateTime.FromText(_, [Format = "yyyy-MM-dd'T'HH:mm:ss", Culture = "en-US"]), type datetime}})
in
    DatasHoras
```

### dim_fase

4 linhas. Tipos: `id_fase` int64, `id_competicao` string, `nome_fase` string, `ordem` int64, `tipo` string, `jogos` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_fase.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_fase", Int64.Type}, {"id_competicao", type text}, {"nome_fase", type text}, {"ordem", Int64.Type}, {"tipo", type text}, {"jogos", Int64.Type}}, "en-US")
in
    Tipos
```

### dim_clube

16 linhas. Tipos: `id_clube` int64, `nome_popular` string, `nome_oficial` string, `sigla` string, `cor_hex` string, `cor_espn` string, `cor_alternativa_espn` string, `id_espn` int64, `url_escudo` string, `arquivo_escudo` string, `escudo_largura` int64, `escudo_altura` int64, `escudo_bytes` int64, `tem_escudo` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_clube.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_clube", Int64.Type}, {"nome_popular", type text}, {"nome_oficial", type text}, {"sigla", type text}, {"cor_hex", type text}, {"cor_espn", type text}, {"cor_alternativa_espn", type text}, {"id_espn", Int64.Type}, {"url_escudo", type text}, {"arquivo_escudo", type text}, {"escudo_largura", Int64.Type}, {"escudo_altura", Int64.Type}, {"escudo_bytes", Int64.Type}, {"tem_escudo", Int64.Type}}, "en-US"),
    Escudos = Table.AddColumn(Tipos, "escudo_base64", each Binary.ToText(File.Contents(CaminhoDados & "\" & Text.Replace([arquivo_escudo], "/", "\")), BinaryEncoding.Base64), type text)
in
    Escudos
```

### dim_clube_alias

56 linhas. Tipos: `alias` string, `alias_normalizado` string, `id_clube` int64, `fonte` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_clube_alias.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"alias", type text}, {"alias_normalizado", type text}, {"id_clube", Int64.Type}, {"fonte", type text}}, "en-US")
in
    Tipos
```

### dim_estadio

16 linhas. Tipos: `id_estadio` string, `nome_fpf` string, `nome_espn` string, `municipio` string, `capacidade` int64, `fonte_capacidade` string, `jogos` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_estadio.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_estadio", type text}, {"nome_fpf", type text}, {"nome_espn", type text}, {"municipio", type text}, {"capacidade", Int64.Type}, {"fonte_capacidade", type text}, {"jogos", Int64.Type}}, "en-US")
in
    Tipos
```

### dim_arbitro

80 linhas. Tipos: `id_arbitro` string, `nome` string, `jogos_arbitro` int64, `jogos_assistente` int64, `jogos_quarto_arbitro` int64, `jogos_var` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_arbitro.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_arbitro", type text}, {"nome", type text}, {"jogos_arbitro", Int64.Type}, {"jogos_assistente", Int64.Type}, {"jogos_quarto_arbitro", Int64.Type}, {"jogos_var", Int64.Type}}, "en-US")
in
    Tipos
```

### dim_calendario

365 linhas. Tipos: `data` date, `ano` int64, `mes` int64, `nome_mes` string, `dia` int64, `dia_semana` int64, `nome_dia_semana` string, `semana_iso` int64, `trimestre` int64, `dia_de_jogo` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_calendario.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"data", type date}, {"ano", Int64.Type}, {"mes", Int64.Type}, {"nome_mes", type text}, {"dia", Int64.Type}, {"dia_semana", Int64.Type}, {"nome_dia_semana", type text}, {"semana_iso", Int64.Type}, {"trimestre", Int64.Type}, {"dia_de_jogo", Int64.Type}}, "en-US")
in
    Tipos
```

### dim_atleta

505 linhas. Tipos: `id_atleta` string, `nome` string, `nome_truncado` int64, `apelido` string, `nome_curto` string, `id_clube` int64, `registros` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\dim_atleta.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_atleta", type text}, {"nome", type text}, {"nome_truncado", Int64.Type}, {"apelido", type text}, {"nome_curto", type text}, {"id_clube", Int64.Type}, {"registros", type text}}, "en-US")
in
    Tipos
```

### fato_partida

72 linhas. Tipos: `id_partida` int64, `numero_jogo` int64, `id_competicao` string, `id_fase` int64, `rodada` int64, `grupo` string, `data_jogo` date, `hora_programada` string, `data_hora_programada` datetime, `id_clube_mandante` int64, `id_clube_visitante` int64, `gols_mandante` int64, `gols_visitante` int64, `penaltis_mandante` int64, `penaltis_visitante` int64, `id_estadio` string, `publico_boletim` int64, `publico_pagante` int64, `renda_bruta` decimal, `despesas_total` decimal, `renda_liquida` decimal, `publico_espn` int64, `id_arbitro` string, `id_assistente1` string, `id_assistente2` string, `id_quarto_arbitro` string, `id_var` string, `id_avar1` string, `id_avar2` string, `inicio_1t` string, `termino_1t` string, `atraso_1t_min` int64, `acrescimo_1t_min` int64, `inicio_2t` string, `termino_2t` string, `atraso_2t_min` int64, `acrescimo_2t_min` int64, `publicada_em` datetime_ptbr, `id_evento_espn` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_partida.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_partida", Int64.Type}, {"numero_jogo", Int64.Type}, {"id_competicao", type text}, {"id_fase", Int64.Type}, {"rodada", Int64.Type}, {"grupo", type text}, {"data_jogo", type date}, {"hora_programada", type text}, {"id_clube_mandante", Int64.Type}, {"id_clube_visitante", Int64.Type}, {"gols_mandante", Int64.Type}, {"gols_visitante", Int64.Type}, {"penaltis_mandante", Int64.Type}, {"penaltis_visitante", Int64.Type}, {"id_estadio", type text}, {"publico_boletim", Int64.Type}, {"publico_pagante", Int64.Type}, {"renda_bruta", Currency.Type}, {"despesas_total", Currency.Type}, {"renda_liquida", Currency.Type}, {"publico_espn", Int64.Type}, {"id_arbitro", type text}, {"id_assistente1", type text}, {"id_assistente2", type text}, {"id_quarto_arbitro", type text}, {"id_var", type text}, {"id_avar1", type text}, {"id_avar2", type text}, {"inicio_1t", type text}, {"termino_1t", type text}, {"atraso_1t_min", Int64.Type}, {"acrescimo_1t_min", Int64.Type}, {"inicio_2t", type text}, {"termino_2t", type text}, {"atraso_2t_min", Int64.Type}, {"acrescimo_2t_min", Int64.Type}, {"id_evento_espn", Int64.Type}}, "en-US"),
    DatasHoras = Table.TransformColumns(Tipos, {{"data_hora_programada", each if _ = null then null else DateTime.FromText(_, [Format = "yyyy-MM-dd'T'HH:mm", Culture = "en-US"]), type datetime}, {"publicada_em", each if _ = null then null else DateTime.FromText(_, [Format = "dd/MM/yyyy HH:mm", Culture = "pt-BR"]), type datetime}})
in
    DatasHoras
```

### fato_evento

600 linhas. Tipos: `id_evento` string, `id_partida` int64, `id_clube` int64, `id_clube_creditado` int64, `tipo_evento` string, `funcao` string, `numero_camisa` int64, `pessoa` string, `apelido` string, `minuto` int64, `acrescimo` int64, `minuto_total` int64, `periodo` string, `motivo` string, `fonte` string, `id_correcao` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_evento.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_evento", type text}, {"id_partida", Int64.Type}, {"id_clube", Int64.Type}, {"id_clube_creditado", Int64.Type}, {"tipo_evento", type text}, {"funcao", type text}, {"numero_camisa", Int64.Type}, {"pessoa", type text}, {"apelido", type text}, {"minuto", Int64.Type}, {"acrescimo", Int64.Type}, {"minuto_total", Int64.Type}, {"periodo", type text}, {"motivo", type text}, {"fonte", type text}, {"id_correcao", type text}}, "en-US")
in
    Tipos
```

### fato_estatistica_time

144 linhas. Tipos: `id_partida` int64, `id_clube` int64, `posse_pct` double, `finalizacoes` int64, `finalizacoes_no_alvo` int64, `finalizacoes_bloqueadas` int64, `faltas` int64, `escanteios` int64, `impedimentos` int64, `passes` int64, `passes_certos` int64, `cruzamentos` int64, `cruzamentos_certos` int64, `desarmes` int64, `desarmes_certos` int64, `interceptacoes` int64, `cortes` int64, `defesas_goleiro` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_estatistica_time.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_partida", Int64.Type}, {"id_clube", Int64.Type}, {"posse_pct", type number}, {"finalizacoes", Int64.Type}, {"finalizacoes_no_alvo", Int64.Type}, {"finalizacoes_bloqueadas", Int64.Type}, {"faltas", Int64.Type}, {"escanteios", Int64.Type}, {"impedimentos", Int64.Type}, {"passes", Int64.Type}, {"passes_certos", Int64.Type}, {"cruzamentos", Int64.Type}, {"cruzamentos_certos", Int64.Type}, {"desarmes", Int64.Type}, {"desarmes_certos", Int64.Type}, {"interceptacoes", Int64.Type}, {"cortes", Int64.Type}, {"defesas_goleiro", Int64.Type}}, "en-US")
in
    Tipos
```

### fato_escalacao

3292 linhas. Tipos: `id_escalacao` string, `id_partida` int64, `id_clube` int64, `id_atleta` string, `numero_camisa` int64, `situacao` string, `vinculo` string, `registro` string, `jogou` int64, `periodo_entrada` string, `minuto_entrada` int64, `acrescimo_entrada` int64, `periodo_saida` string, `minuto_saida` int64, `acrescimo_saida` int64, `minutos_jogados` int64, `gols` int64, `gols_contra` int64, `amarelos` int64, `vermelhos` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_escalacao.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_escalacao", type text}, {"id_partida", Int64.Type}, {"id_clube", Int64.Type}, {"id_atleta", type text}, {"numero_camisa", Int64.Type}, {"situacao", type text}, {"vinculo", type text}, {"registro", type text}, {"jogou", Int64.Type}, {"periodo_entrada", type text}, {"minuto_entrada", Int64.Type}, {"acrescimo_entrada", Int64.Type}, {"periodo_saida", type text}, {"minuto_saida", Int64.Type}, {"acrescimo_saida", Int64.Type}, {"minutos_jogados", Int64.Type}, {"gols", Int64.Type}, {"gols_contra", Int64.Type}, {"amarelos", Int64.Type}, {"vermelhos", Int64.Type}}, "en-US")
in
    Tipos
```

### fato_substituicao

706 linhas. Tipos: `id_substituicao` string, `id_partida` int64, `id_clube` int64, `ordem` int64, `tipo` string, `id_atleta_saiu` string, `id_atleta_entrou` string, `numero_saiu` int64, `numero_entrou` int64, `periodo` string, `minuto` int64, `acrescimo` int64, `minuto_total` int64, `motivo` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_substituicao.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_substituicao", type text}, {"id_partida", Int64.Type}, {"id_clube", Int64.Type}, {"ordem", Int64.Type}, {"tipo", type text}, {"id_atleta_saiu", type text}, {"id_atleta_entrou", type text}, {"numero_saiu", Int64.Type}, {"numero_entrou", Int64.Type}, {"periodo", type text}, {"minuto", Int64.Type}, {"acrescimo", Int64.Type}, {"minuto_total", Int64.Type}, {"motivo", type text}}, "en-US")
in
    Tipos
```

### fato_comissao

1066 linhas. Tipos: `id_comissao` string, `id_partida` int64, `id_clube` int64, `funcao` string, `nome` string, `nome_truncado` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_comissao.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_comissao", type text}, {"id_partida", Int64.Type}, {"id_clube", Int64.Type}, {"funcao", type text}, {"nome", type text}, {"nome_truncado", Int64.Type}}, "en-US")
in
    Tipos
```

### fato_ingresso

2388 linhas. Tipos: `id_ingresso` string, `id_partida` int64, `ordem` int64, `localidade` string, `categoria` string, `ordem_categoria` int64, `setor_visitante` int64, `ingressos` int64, `preco` decimal, `arrecadacao` decimal

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_ingresso.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_ingresso", type text}, {"id_partida", Int64.Type}, {"ordem", Int64.Type}, {"localidade", type text}, {"categoria", type text}, {"ordem_categoria", Int64.Type}, {"setor_visitante", Int64.Type}, {"ingressos", Int64.Type}, {"preco", Currency.Type}, {"arrecadacao", Currency.Type}}, "en-US")
in
    Tipos
```

### fato_despesa

1482 linhas. Tipos: `id_despesa` string, `id_partida` int64, `bloco_codigo` string, `bloco` string, `ordem` int64, `rubrica` string, `grupo` string, `valor` decimal

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_despesa.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_despesa", type text}, {"id_partida", Int64.Type}, {"bloco_codigo", type text}, {"bloco", type text}, {"ordem", Int64.Type}, {"rubrica", type text}, {"grupo", type text}, {"valor", Currency.Type}}, "en-US")
in
    Tipos
```

### fato_rateio

144 linhas. Tipos: `id_rateio` string, `id_partida` int64, `id_clube` int64, `lado` string, `percentual` double, `valor` decimal, `deducao_inss` decimal, `deducao_outras` decimal, `liquido` decimal

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_rateio.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_rateio", type text}, {"id_partida", Int64.Type}, {"id_clube", Int64.Type}, {"lado", type text}, {"percentual", type number}, {"valor", Currency.Type}, {"deducao_inss", Currency.Type}, {"deducao_outras", Currency.Type}, {"liquido", Currency.Type}}, "en-US")
in
    Tipos
```

### fato_classificacao_oficial

30 linhas. Tipos: `id_fase` int64, `fase` string, `grupo` string, `posicao` int64, `id_clube` int64, `pontos` int64, `jogos` int64, `vitorias` int64, `empates` int64, `derrotas` int64, `gols_pro` int64, `gols_contra` int64, `saldo` int64, `vp` int64, `dp` int64, `amarelos` int64, `vermelhos` int64, `atualizado_em` datetime

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_classificacao_oficial.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_fase", Int64.Type}, {"fase", type text}, {"grupo", type text}, {"posicao", Int64.Type}, {"id_clube", Int64.Type}, {"pontos", Int64.Type}, {"jogos", Int64.Type}, {"vitorias", Int64.Type}, {"empates", Int64.Type}, {"derrotas", Int64.Type}, {"gols_pro", Int64.Type}, {"gols_contra", Int64.Type}, {"saldo", Int64.Type}, {"vp", Int64.Type}, {"dp", Int64.Type}, {"amarelos", Int64.Type}, {"vermelhos", Int64.Type}}, "en-US"),
    DatasHoras = Table.TransformColumns(Tipos, {{"atualizado_em", each if _ = null then null else DateTime.FromText(_, [Format = "yyyy-MM-dd'T'HH:mm:ss", Culture = "en-US"]), type datetime}})
in
    DatasHoras
```

### ref_classificacao_primeira_fase

16 linhas. Tipos: `posicao` int64, `id_clube` int64, `jogos` int64, `vitorias` int64, `empates` int64, `derrotas` int64, `gols_pro` int64, `gols_contra` int64, `saldo` int64, `pontos` int64, `aproveitamento` double, `amarelos` int64, `vermelhos` int64, `empate_total` int64

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\ref_classificacao_primeira_fase.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"posicao", Int64.Type}, {"id_clube", Int64.Type}, {"jogos", Int64.Type}, {"vitorias", Int64.Type}, {"empates", Int64.Type}, {"derrotas", Int64.Type}, {"gols_pro", Int64.Type}, {"gols_contra", Int64.Type}, {"saldo", Int64.Type}, {"pontos", Int64.Type}, {"aproveitamento", type number}, {"amarelos", Int64.Type}, {"vermelhos", Int64.Type}, {"empate_total", Int64.Type}}, "en-US")
in
    Tipos
```

### aux_config

13 linhas. Tipos: `chave` string, `valor` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\aux_config.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"chave", type text}, {"valor", type text}}, "en-US")
in
    Tipos
```

### fato_inconsistencia

46 linhas. Tipos: `id_inconsistencia` string, `codigo_regra` string, `titulo_regra` string, `id_partida` int64, `numero_jogo` int64, `id_clube` int64, `fonte_a` string, `valor_a` string, `fonte_b` string, `valor_b` string, `detalhe` string, `severidade` string, `status` string, `explicacao` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\fato_inconsistencia.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_inconsistencia", type text}, {"codigo_regra", type text}, {"titulo_regra", type text}, {"id_partida", Int64.Type}, {"numero_jogo", Int64.Type}, {"id_clube", Int64.Type}, {"fonte_a", type text}, {"valor_a", type text}, {"fonte_b", type text}, {"valor_b", type text}, {"detalhe", type text}, {"severidade", type text}, {"status", type text}, {"explicacao", type text}}, "en-US")
in
    Tipos
```

### resultado_regra

45 linhas. Tipos: `codigo` string, `titulo` string, `severidade` string, `verificados` int64, `ocorrencias` int64, `abertas` int64, `explicadas` int64, `corrigidas` int64, `aceitas` int64, `resultado` string, `resumo` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\resultado_regra.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"codigo", type text}, {"titulo", type text}, {"severidade", type text}, {"verificados", Int64.Type}, {"ocorrencias", Int64.Type}, {"abertas", Int64.Type}, {"explicadas", Int64.Type}, {"corrigidas", Int64.Type}, {"aceitas", Int64.Type}, {"resultado", type text}, {"resumo", type text}}, "en-US")
in
    Tipos
```

### ref_indicadores

586 linhas. Tipos: `id_indicador` string, `indicador` string, `escopo` string, `chave` string, `id_clube` int64, `valor` double, `unidade` string

```m
let
    Origem = Csv.Document(File.Contents(CaminhoDados & "\ref_indicadores.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),
    Tipos = Table.TransformColumnTypes(Vazios, {{"id_indicador", type text}, {"indicador", type text}, {"escopo", type text}, {"chave", type text}, {"id_clube", Int64.Type}, {"valor", type number}, {"unidade", type text}}, "en-US")
in
    Tipos
```
