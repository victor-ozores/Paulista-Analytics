"""Gera no projeto PBIP as consultas do Power Query (uma por tabela) e o parâmetro do caminho.

Para cada CSV de data/processed/ escreve `powerbi/PaulistaAnalytics.SemanticModel/definition/tables/<tabela>.tmdl`
com as colunas tipadas e a consulta em M (`Csv.Document`, separador ";", UTF-8, tipos explícitos, cultura
en-US porque os números e datas dos CSV usam ponto decimal e formato ISO). Escreve também o parâmetro
`CaminhoDados` (`expressions.tmdl`), registra tudo em `model.tmdl` e gera `docs/powerquery.md`.

O Power Query é fino de propósito: só carrega e tipa. Limpeza e validação ficam em Python.
A tabela `dim_clube` ganha a coluna `escudo_base64` (lida dos PNGs reduzidos), para a interface embutir os escudos.

Por padrão só escreve as tabelas cujo arquivo ainda não existe em `tables/` (o Power BI Desktop, ao salvar, reescreve os arquivos
que já existem; sobrescrevê-los apagaria o que ele guardou). Com `--tudo` reescreve todas. A descrição de cada tabela vem de
`DESCRICAO_TABELAS` em `scripts/09_gerar_relacionamentos.py` e entra no arquivo como comentário `///`.

Feche o projeto no Power BI Desktop (sem salvar) antes de rodar e reabra depois.

Uso: python scripts/08_gerar_powerquery.py [--caminho C:\\pasta\\com\\os\\csv] [--tudo]
"""
import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path

from comum import RAIZ, ler_csv

PROC = RAIZ / "data" / "processed"
MODELO = RAIZ / "powerbi" / "PaulistaAnalytics.SemanticModel" / "definition"
DOC = RAIZ / "docs" / "powerquery.md"
NS = uuid.UUID("5f0c1e1a-7e57-4c0a-9a55-0a1a6b1e0002")
TABELAS = ["dim_competicao", "dim_fase", "dim_clube", "dim_clube_alias", "dim_estadio", "dim_arbitro", "dim_calendario", "dim_atleta", "fato_partida", "fato_evento", "fato_estatistica_time",
           "fato_escalacao", "fato_substituicao", "fato_comissao", "fato_ingresso", "fato_despesa", "fato_rateio",
           "fato_classificacao_oficial", "ref_classificacao_primeira_fase", "aux_config", "fato_inconsistencia", "resultado_regra", "ref_indicadores"]
TECNICAS = ["_Medidas", "aux_dashboard"]
FORCAR = {("dim_estadio", "capacidade"): "int64", ("fato_partida", "renda_bruta"): "decimal", ("fato_partida", "despesas_total"): "decimal", ("fato_partida", "renda_liquida"): "decimal",
          ("fato_partida", "publicada_em"): "datetime_ptbr",
          ("fato_ingresso", "preco"): "decimal", ("fato_ingresso", "arrecadacao"): "decimal", ("fato_despesa", "valor"): "decimal",
          ("fato_rateio", "valor"): "decimal", ("fato_rateio", "deducao_inss"): "decimal", ("fato_rateio", "deducao_outras"): "decimal", ("fato_rateio", "liquido"): "decimal"}
ESCUDO = ("dim_clube", "escudo_base64")
INT, FLT, DATA, DT = re.compile(r"^-?(0|[1-9]\d*)$"), re.compile(r"^-?\d+\.\d+$"), re.compile(r"^\d{4}-\d{2}-\d{2}$"), re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
M_TIPO = {"int64": "Int64.Type", "double": "type number", "decimal": "Currency.Type", "string": "type text", "date": "type date"}
TMDL_TIPO = {"int64": "int64", "double": "double", "decimal": "decimal", "string": "string", "date": "dateTime", "datetime": "dateTime", "datetime_ptbr": "dateTime"}
FORMATO = {"int64": "0", "double": "#,0.00", "decimal": "#,0.00", "date": "dd/mm/yyyy", "datetime": "dd/mm/yyyy hh:mm", "datetime_ptbr": "dd/mm/yyyy hh:mm"}


def guid(*partes):
    return str(uuid.uuid5(NS, "|".join(partes)))


def inferir(tabela, coluna, valores):
    if (tabela, coluna) in FORCAR:
        return FORCAR[(tabela, coluna)]
    v = [x for x in valores if x != ""]
    if not v:
        return "string"
    if all(INT.match(x) for x in v):
        return "int64"
    if all(INT.match(x) or FLT.match(x) for x in v):
        return "double"
    if all(DATA.match(x) for x in v):
        return "date"
    if all(DT.match(x) for x in v):
        return "datetime"
    return "string"


def formato_datahora(valores):
    return "yyyy-MM-dd'T'HH:mm:ss" if all(len(x) == 19 for x in valores if x != "") else "yyyy-MM-dd'T'HH:mm"


def consulta_m(tabela, colunas):
    """colunas: lista de (nome, tipo, exemplos). Devolve o M da consulta."""
    por_tipo = [(n, t) for n, t, _ in colunas if t in M_TIPO]
    tipos = ", ".join(f'{{"{n}", {M_TIPO[t]}}}' for n, t in por_tipo)
    L = ["let",
         f'    Origem = Csv.Document(File.Contents(CaminhoDados & "\\{tabela}.csv"), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
         "    Cabecalho = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),",
         '    Vazios = Table.ReplaceValue(Cabecalho, "", null, Replacer.ReplaceValue, Table.ColumnNames(Cabecalho)),',
         f'    Tipos = Table.TransformColumnTypes(Vazios, {{{tipos}}}, "en-US")']
    ultimo = "Tipos"
    datas = [(n, t, ex) for n, t, ex in colunas if t in ("datetime", "datetime_ptbr")]
    if datas:
        trans = []
        for n, t, ex in datas:
            fmt, cult = ("dd/MM/yyyy HH:mm", "pt-BR") if t == "datetime_ptbr" else (formato_datahora(ex), "en-US")
            trans.append(f'{{"{n}", each if _ = null then null else DateTime.FromText(_, [Format = "{fmt}", Culture = "{cult}"]), type datetime}}')
        L[-1] += ","
        L.append(f"    DatasHoras = Table.TransformColumns(Tipos, {{{', '.join(trans)}}})")
        ultimo = "DatasHoras"
    if tabela == ESCUDO[0]:
        L[-1] += ","
        L.append(f'    Escudos = Table.AddColumn({ultimo}, "{ESCUDO[1]}", each Binary.ToText(File.Contents(CaminhoDados & "\\" & Text.Replace([arquivo_escudo], "/", "\\")), BinaryEncoding.Base64), type text)')
        ultimo = "Escudos"
    L += ["in", f"    {ultimo}"]
    return "\n".join(L)


def relativo(caminho):
    try:
        return caminho.relative_to(RAIZ)
    except ValueError:
        return caminho


def descricoes():
    spec = importlib.util.spec_from_file_location("rel09", Path(__file__).resolve().parent / "09_gerar_relacionamentos.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DESCRICAO_TABELAS


def tmdl_tabela(tabela, colunas, m, descricao=None):
    L = ([f"/// {descricao}"] if descricao else []) + [f"table {tabela}", f"\tlineageTag: {guid(tabela)}", ""]
    for nome, tipo, _ in colunas:
        L += [f"\tcolumn {nome}", f"\t\tdataType: {TMDL_TIPO[tipo]}"]
        if tipo in FORMATO:
            L.append(f"\t\tformatString: {FORMATO[tipo]}")
        L += [f"\t\tlineageTag: {guid(tabela, nome)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {nome}"]
        if tipo == "date":
            L += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
        L.append("")
    L += [f"\tpartition {tabela} = m", "\t\tmode: import", "\t\tsource ="]
    L += ["\t\t\t\t" + linha for linha in m.split("\n")]
    L.append("")
    return "\n".join(L)


def tabela_pronta(tabela):
    linhas = ler_csv(PROC / f"{tabela}.csv")
    cabecalho = list(linhas[0])
    colunas = []
    for c in cabecalho:
        valores = [l[c] for l in linhas]
        colunas.append((c, inferir(tabela, c, valores), valores))
    m = consulta_m(tabela, colunas)
    cols_tmdl = list(colunas) + ([(ESCUDO[1], "string", [])] if tabela == ESCUDO[0] else [])
    return {"tabela": tabela, "linhas": len(linhas), "colunas": colunas, "m": m, "tmdl": tmdl_tabela(tabela, cols_tmdl, m, descricoes().get(tabela))}


def tmdl_parametro(caminho):
    return "\n".join([f'expression CaminhoDados = "{caminho}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
                      f"\tlineageTag: {guid('CaminhoDados')}", "", "\tannotation PBI_ResultType = Text", ""])


def atualizar_modelo(tabelas):
    arq = MODELO / "model.tmdl"
    s = arq.read_text(encoding="utf-8")
    s = re.sub(r"^ref (table|expression) .*\n\n?", "", s, flags=re.M)
    refs = "".join(f"ref table {t}\n" for t in sorted(set(tabelas)) + TECNICAS) + "ref expression CaminhoDados\n\n"
    s = s.replace("ref cultureInfo pt-BR", refs + "ref cultureInfo pt-BR")
    ordem = json.dumps(sorted(tabelas) + ["CaminhoDados"], ensure_ascii=False, separators=(",", ":"))
    s = re.sub(r"^annotation PBI_QueryOrder = .*$", lambda _: f"annotation PBI_QueryOrder = {ordem}", s, flags=re.M)
    arq.write_text(s, encoding="utf-8", newline="\n")


def documento(prontas, caminho):
    L = ["# Power Query: como o Power BI carrega os dados", "",
         "Gerado por `scripts/08_gerar_powerquery.py` (não editar à mão: rode o script de novo). As consultas ficam em `powerbi/PaulistaAnalytics.SemanticModel/definition/tables/`.", "",
         "## Princípio", "",
         "O Power Query é **fino**: carrega cada CSV de `data/processed/` e define os tipos. Limpeza, conferência e regras de negócio não estão aqui: estão em Python (ETL, regras de conferência e testes) e no DAX. Assim cada regra existe em um lugar só.", "",
         "## Parâmetro", "",
         f"`CaminhoDados` (texto) = pasta dos CSV. Valor: a pasta `data/processed` do projeto (ajuste ao caminho da sua máquina em Página Inicial > Transformar dados > Gerenciar parâmetros).", "",
         "## Padrão de cada consulta", "",
         "1. `Origem`: `Csv.Document(File.Contents(CaminhoDados & \"\\tabela.csv\"), [Delimiter = \";\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv])` (separador ponto e vírgula, UTF-8, aspas CSV).",
         "2. `Cabecalho`: a primeira linha vira o nome das colunas.",
         "3. `Vazios`: texto vazio (`\"\"`) vira nulo. Sem isso o Power BI trata `\"\"` como valor preenchido e `ISBLANK` falha.",
         "4. `Tipos`: tipos explícitos com a cultura **en-US**. Isso é obrigatório: os números usam ponto decimal (`28580.00`) e, lidos em português, virariam 2.858.000. Por isso a detecção automática de tipos não é usada.",
         "5. `DatasHoras` (só onde há data e hora): `DateTime.FromText` com o formato exato do CSV.", "",
         "Os tipos vêm do próprio conteúdo dos CSV, com ajustes manuais no script (`FORCAR`): todo dinheiro como decimal fixo (`renda_bruta`, `despesas_total` e `renda_liquida` da partida; `preco` e `arrecadacao` de `fato_ingresso`; `valor` de `fato_despesa`; `valor`, `deducao_inss`, `deducao_outras` e `liquido` de `fato_rateio`), para as somas fecharem no centavo; `dim_estadio.capacidade` como inteiro (hoje vazia); `fato_partida.publicada_em` como data e hora no formato `dd/MM/yyyy HH:mm`.", "",
         "## Escudos", "",
         "`dim_clube` ganha a coluna `escudo_base64`: o conteúdo de cada PNG reduzido (`data/processed/escudos/`) em base64, para a interface montar `data:image/png;base64,...` sem depender de URL externa.", "",
         "## Tabelas", "", "| Tabela | Linhas | Colunas |", "|---|---|---|"]
    for p in prontas:
        L.append(f"| `{p['tabela']}` | {p['linhas']} | {len(p['colunas'])}{' (+1 escudo_base64)' if p['tabela'] == ESCUDO[0] else ''} |")
    L += ["", "## Consultas (M) e tipos", ""]
    for p in prontas:
        L += [f"### {p['tabela']}", "", f"{p['linhas']} linhas. Tipos: " + ", ".join(f"`{n}` {t}" for n, t, _ in p["colunas"]), "", "```m", p["m"], "```", ""]
    return "\n".join(L)


def principal():
    caminho = sys.argv[sys.argv.index("--caminho") + 1] if "--caminho" in sys.argv else str(PROC)
    tudo = "--tudo" in sys.argv
    prontas = [tabela_pronta(t) for t in TABELAS]
    (MODELO / "tables").mkdir(parents=True, exist_ok=True)
    escritas, preservadas = [], []
    for p in prontas:
        arq = MODELO / "tables" / f"{p['tabela']}.tmdl"
        if arq.exists() and not tudo:
            preservadas.append(p["tabela"])
            continue
        arq.write_text(p["tmdl"], encoding="utf-8", newline="\n")
        escritas.append(p["tabela"])
    (MODELO / "expressions.tmdl").write_text(tmdl_parametro(caminho), encoding="utf-8", newline="\n")
    atualizar_modelo(TABELAS)
    DOC.write_text(documento(prontas, caminho), encoding="utf-8", newline="\n")
    total_cols = sum(len(p["colunas"]) for p in prontas)
    print(f"{len(prontas)} tabelas, {total_cols} colunas, parâmetro CaminhoDados = {caminho}")
    for p in prontas:
        print(f"  {p['tabela']:34s} {p['linhas']:4d} linhas {len(p['colunas']):3d} colunas  {'escrita' if p['tabela'] in escritas else 'preservada (já existia)'}")
    print(f"escritas: {len(escritas)} | preservadas: {len(preservadas)} | em {relativo(MODELO)} e {relativo(DOC)}")


if __name__ == "__main__":
    principal()
