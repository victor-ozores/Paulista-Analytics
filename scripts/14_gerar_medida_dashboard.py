"""Coloca o dashboard (barra de navegação e todas as telas) no Power BI como a medida `html_dashboard`.

A página vem de scripts/13_montar_app.py em partes: o código (com uma marca `__DADOS_XXX__` para cada tela) e o pacote de dados de cada tela.
Cada parte é dividida em pedaços de até 8.000 caracteres, uma medida oculta por pedaço, na tabela calculada `aux_dashboard`.
`html_dashboard_codigo` e uma medida `html_dashboard_dados_*` por tela juntam os pedaços e `html_dashboard` troca as marcas pelos dados. É o
texto que vai em Valores do visual HTML Content. Para uma tela nova, acrescente a linha dela em `PACOTES` (e em `TELAS` de 13_montar_app.py).

Escreve `tables/aux_dashboard.tmdl`, registra a tabela em `model.tmdl` (e tira a `aux_versus`, que era só da tela de versus), liga o visual a
`html_dashboard` e apaga `tables/aux_versus.tmdl`. Os dados vêm do Python (conferidos pelos testes), não de medidas DAX.

Feche o projeto no Power BI Desktop antes de gravar (o script recusa se ele estiver aberto) e reabra depois.

Uso: python scripts/14_gerar_medida_dashboard.py [--teste] [--query] [--esperado] [--descricoes] [--forcar] [--tamanho 8000]
  --teste       confere tudo em memória (remontagem idêntica, JSON e JavaScript válidos) e não grava nada
  --descricoes  imprime as descrições da tabela e das medidas (MCP: table_operations e measure_operations Update) para aplicar no modelo aberto
  --query       imprime a consulta DAX que mede cada pedaço no modelo aberto (tamanho e soma ponderada)
  --esperado    imprime os mesmos valores calculados aqui, para comparar com o resultado da consulta
"""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from comum import RAIZ

MODELO = RAIZ / "powerbi" / "PaulistaAnalytics.SemanticModel" / "definition"
TABELA = MODELO / "tables" / "aux_dashboard.tmdl"
TABELA_ANTIGA = MODELO / "tables" / "aux_versus.tmdl"
VISUAL = RAIZ / "powerbi" / "PaulistaAnalytics.Report" / "definition" / "pages" / "7c7269fdd5373189ce13" / "visuals" / "ef732fa54b9444f06233" / "visual.json"
MARCA = "~~NL~~"
NS = uuid.UUID("5f0c1e1a-7e57-4c0a-9a55-0a1a6b1e0004")
NOME_TABELA, NOME_MEDIDA = "aux_dashboard", "html_dashboard"
ANTIGAS = ("aux_versus", "html_versus")
PACOTES = [
    ("vg", "dvg", "dados_vg", "da tela Visão geral", "JSON com os 72 jogos em resumo (placar, público, renda e cartões), os artilheiros e o campeão"),
    ("vs", "dvs", "dados_vs", "da tela de versus", "JSON com jogos, eventos, clubes e números de conferência"),
    ("gl", "dgl", "dados_gl", "da tela Gols e artilharia", "JSON com os 72 jogos e os 168 gols, um por um (jogo, minuto, tipo, clube e atleta)"),
    ("ds", "dds", "dados_ds", "da tela Disciplina e arbitragem", "JSON com os 72 jogos (árbitro, acréscimos e gols de pênalti) e os 413 cartões, um por um (jogo, minuto, tipo, clube, atleta e categoria do motivo)"),
    ("jg", "djg", "dados_jg", "da tela Jogos", "JSON com os 72 jogos (data, estádio, arbitragem, público e renda), as escalações, as trocas, os gols e cartões de cada jogo e as estatísticas dos times (ESPN, não oficial)"),
    ("fin", "dfn", "dados_fin", "da tela Público e renda", "JSON com os 72 jogos agregados em centavos: categorias de ingresso, grupos de despesa, blocos, rubricas e divisão da renda"),
    ("clas", "dcl", "dados_clas", "da tela Classificação e chave", "JSON com a tabela da 1ª fase, as posições rodada a rodada, os jogos do mata-mata e os desempates"),
    ("conf", "dco", "dados_conf", "da tela Conferência e fontes", "JSON com as regras de conferência, as ocorrências, as fontes, as camadas de conferência e a correção documentada"),
]
PREFIXOS = ["cod"] + [p[1] for p in PACOTES]


def marca_de(chave):
    return f"__DADOS_{chave.upper()}__"


def modulo13():
    spec = importlib.util.spec_from_file_location("app13", RAIZ / "scripts" / "13_montar_app.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("app13", m)
    spec.loader.exec_module(m)
    return m


def guid(nome):
    return str(uuid.uuid5(NS, nome))


def dividir(texto, tamanho):
    return [texto[i:i + tamanho] for i in range(0, len(texto), tamanho)]


def literal(trecho):
    return '"' + trecho.replace('"', '""') + '"'


def nomes(prefixo, n):
    return [f"{NOME_MEDIDA}_{prefixo}_{i:02d}" for i in range(1, n + 1)]


def todos_os_nomes(nm):
    return [n for pre in PREFIXOS for n in nm[pre]]


def junta_nomes():
    return [f"{NOME_MEDIDA}_codigo"] + [f"{NOME_MEDIDA}_{p[2]}" for p in PACOTES]


def descricao_tabela(nm):
    partes = ", ".join(f"{nome} em {len(nm[pre])}" for _, pre, _, nome, _ in PACOTES)
    return (f"Tabela técnica do dashboard: guarda as medidas que montam o HTML do visual HTML Content (código em {len(nm['cod'])} pedaços e dados {partes}, de até 8.000 caracteres cada). "
            "Sem dados de negócio. Gerada por scripts/14_gerar_medida_dashboard.py; não editar à mão.")


def descricoes_medidas(nm):
    d = {}
    for i, n in enumerate(nm["cod"], 1):
        d[n] = f"Pedaço {i} de {len(nm['cod'])} do código do dashboard (barra de navegação e as telas: HTML, CSS e JavaScript); as quebras de linha viram {MARCA}. Oculta; gerada por scripts/14_gerar_medida_dashboard.py, não editar à mão."
    for _, pre, suf, nome, conteudo in PACOTES:
        for i, n in enumerate(nm[pre], 1):
            d[n] = f"Pedaço {i} de {len(nm[pre])} dos dados {nome} ({conteudo}). Oculta; gerada por scripts/14_gerar_medida_dashboard.py, não editar à mão."
        d[f"{NOME_MEDIDA}_{suf}"] = f"Junta {'o pedaço' if len(nm[pre]) == 1 else str(len(nm[pre])) + ' pedaços'} de dados {nome} (JSON). Oculta."
    d[f"{NOME_MEDIDA}_codigo"] = f"Junta os {len(nm['cod'])} pedaços de código e devolve as quebras de linha. Oculta."
    marcas = ", ".join(marca_de(p[0]) for p in PACOTES[:-1]) + " e " + marca_de(PACOTES[-1][0])
    d[NOME_MEDIDA] = (f"Página completa do dashboard: o código com {marcas} trocados pelos {len(PACOTES)} pacotes de dados. É a medida ligada ao visual HTML Content "
                      "(campo Valores). Conferida contra o Python pedaço a pedaço (tamanho e soma), com --query e --esperado.")
    return d


def montar_tmdl(pedacos):
    """pedacos: {prefixo: [texto, ...]} com 'cod' e o prefixo de cada tela em PACOTES. Devolve (tmdl, {prefixo: [nomes das medidas]})."""
    nm = {pre: nomes(pre, len(pedacos[pre])) for pre in PREFIXOS}
    desc = descricoes_medidas(nm)
    L = [f"/// {descricao_tabela(nm)}", f"table {NOME_TABELA}", f"\tlineageTag: {guid('tabela')}", ""]
    for pre in PREFIXOS:
        for nome, p in zip(nm[pre], pedacos[pre]):
            L += [f"\t/// {desc[nome]}", f"\tmeasure {nome} = {literal(p)}", "\t\tisHidden", f"\t\tlineageTag: {guid(nome)}", ""]
    junta = lambda ns: " & ".join(f"[{n}]" for n in ns)
    cod_m = f"{NOME_MEDIDA}_codigo"
    L += [f"\t/// {desc[cod_m]}", f'\tmeasure {cod_m} = SUBSTITUTE({junta(nm["cod"])}, "{MARCA}", UNICHAR(10))', "\t\tisHidden", f"\t\tlineageTag: {guid('codigo')}", ""]
    expr = f"[{cod_m}]"
    for chave, pre, suf, _, _ in PACOTES:
        m = f"{NOME_MEDIDA}_{suf}"
        L += [f"\t/// {desc[m]}", f"\tmeasure {m} = {junta(nm[pre])}", "\t\tisHidden", f"\t\tlineageTag: {guid(suf)}", ""]
        expr = f'SUBSTITUTE({expr}, "{marca_de(chave)}", [{m}])'
    L += [f"\t/// {desc[NOME_MEDIDA]}", f"\tmeasure {NOME_MEDIDA} = {expr}", f"\t\tlineageTag: {guid(NOME_MEDIDA)}", "",
          "\tcolumn Value", "\t\tdataType: int64", "\t\tisHidden", "\t\tisNameInferred", f"\t\tlineageTag: {guid('coluna')}", "\t\tsummarizeBy: none", "\t\tsourceColumn: [Value]", "",
          f"\tpartition {NOME_TABELA} = calculated", "\t\tmode: import", "\t\tsource = {1}", ""]
    return "\n".join(L), nm


def pedacos_do_tmdl(tmdl, prefixo):
    achados = re.findall(rf'^\tmeasure {NOME_MEDIDA}_{prefixo}_\d\d = "(.*)"$', tmdl, re.M)
    return [a.replace('""', '"') for a in achados]


def remontar(tmdl):
    """Lê de volta o TMDL como o Power BI leria e devolve a página que `html_dashboard` produz."""
    pagina = "".join(pedacos_do_tmdl(tmdl, "cod")).replace(MARCA, "\n")
    for chave, pre, _, _, _ in PACOTES:
        pagina = pagina.replace(marca_de(chave), "".join(pedacos_do_tmdl(tmdl, pre)))
    return pagina


def soma(texto):
    return sum(i * ord(c) for i, c in enumerate(texto, 1))


def checar_js(pagina):
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", pagina, re.S)
    if not scripts:
        raise SystemExit("sem <script> na página")
    with tempfile.TemporaryDirectory() as d:
        for k, js in enumerate(scripts):
            arq = Path(d) / f"s{k}.js"
            arq.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"JavaScript com erro de sintaxe: {r.stderr[:400]}")
    return len(scripts)


def desktop_aberto():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PBIDesktop.exe", "/NH"], capture_output=True, text=True)
    return "PBIDesktop.exe" in r.stdout


def registrar_no_modelo():
    """Garante `ref table aux_dashboard` depois da última tabela e tira a `aux_versus`. Devolve True se o arquivo mudou."""
    modelo = MODELO / "model.tmdl"
    s = modelo.read_text(encoding="utf-8")
    novo = re.sub(rf"^ref table {ANTIGAS[0]}\n", "", s, flags=re.M)
    if f"ref table {NOME_TABELA}" not in novo:
        linhas = novo.split("\n")
        ultima = max((i for i, l in enumerate(linhas) if l.startswith("ref table ")), default=None)
        if ultima is None:
            novo = novo.replace("ref cultureInfo", f"ref table {NOME_TABELA}\n\nref cultureInfo", 1)
        else:
            linhas.insert(ultima + 1, f"ref table {NOME_TABELA}")
            novo = "\n".join(linhas)
    if novo == s:
        return False
    modelo.write_text(novo, encoding="utf-8", newline="\n")
    return True


def visual_ligado():
    s = VISUAL.read_text(encoding="utf-8")
    return s.count(f'"Entity": "{NOME_TABELA}"') >= 1 and s.count(f'"Property": "{NOME_MEDIDA}"') >= 1 and ANTIGAS[0] not in s and ANTIGAS[1] not in s


def ligar_visual():
    """Aponta o visual para `html_dashboard` (as referências do campo Valores e do filtro). Devolve quantas trocas fez."""
    s = VISUAL.read_text(encoding="utf-8")
    trocas = 0
    for velho, novo in ((f'"Entity": "{ANTIGAS[0]}"', f'"Entity": "{NOME_TABELA}"'), (f'"Property": "{ANTIGAS[1]}"', f'"Property": "{NOME_MEDIDA}"'),
                        (f'"queryRef": "{ANTIGAS[0]}.{ANTIGAS[1]}"', f'"queryRef": "{NOME_TABELA}.{NOME_MEDIDA}"'), (f'"nativeQueryRef": "{ANTIGAS[1]}"', f'"nativeQueryRef": "{NOME_MEDIDA}"')):
        trocas += s.count(velho)
        s = s.replace(velho, novo)
    if trocas:
        VISUAL.write_text(s, encoding="utf-8", newline="\n")
    return trocas


def preparar(tamanho):
    app = modulo13()
    dados = app.montar_todos_os_dados()
    codigo = app.montar_codigo_app(dados["conf"]["meta"])
    for chave, *_ in PACOTES:
        if codigo.count(marca_de(chave)) != 1:
            raise SystemExit(f"o código precisa ter exatamente um {marca_de(chave)}")
    if MARCA in codigo or "\r" in codigo:
        raise SystemExit("o código contém a marca de quebra de linha ou \\r")
    textos = {chave: app.dados_json(dados[chave]) for chave, *_ in PACOTES}
    for chave, texto in textos.items():
        json.loads(texto.replace("<\\/", "</"))
        if MARCA in texto or "\n" in texto or "__DADOS_" in texto:
            raise SystemExit(f"os dados da tela '{chave}' contêm quebra de linha, a marca ou uma marca de dados")
    if any(ord(c) > 0xFFFF for c in codigo + "".join(textos.values())):
        raise SystemExit("há caractere fora do plano básico (UNICODE do DAX difere do Python)")
    pedacos = {"cod": dividir(codigo.replace("\n", MARCA), tamanho)}
    for chave, pre, *_ in PACOTES:
        pedacos[pre] = dividir(textos[chave], tamanho)
    tmdl, nm = montar_tmdl(pedacos)
    pagina = codigo
    for chave, *_ in PACOTES:
        pagina = pagina.replace(marca_de(chave), textos[chave])
    if remontar(tmdl) != pagina:
        raise SystemExit("o texto remontado não é idêntico à página")
    if pagina != app.montar_fragmentos(dados)["app"]:
        raise SystemExit("a página da medida não é idêntica à página do protótipo (13_montar_app.py)")
    return {"codigo": codigo, "textos": textos, "pedacos": pedacos, "tmdl": tmdl, "nomes": nm, "pagina": pagina}


def tabela_esperada(p):
    return [(n, len(t), soma(t)) for pre in PREFIXOS for n, t in zip(p["nomes"][pre], p["pedacos"][pre])]


def consulta(p):
    linhas = []
    for n in todos_os_nomes(p["nomes"]):
        linhas.append(f'ROW("Medida", "{n}", "Tamanho", LEN([{n}]), "Soma", SUMX(GENERATESERIES(1, LEN([{n}])), UNICODE(MID([{n}], [Value], 1)) * [Value]))')
    for n in junta_nomes() + [NOME_MEDIDA]:
        linhas.append(f'ROW("Medida", "{n}", "Tamanho", LEN([{n}]), "Soma", BLANK())')
    return "EVALUATE\nUNION(\n    " + ",\n    ".join(linhas) + "\n)"


def main():
    tamanho = int(sys.argv[sys.argv.index("--tamanho") + 1]) if "--tamanho" in sys.argv else 8000
    p = preparar(tamanho)
    scripts = checar_js(p["pagina"])
    if "--descricoes" in sys.argv:
        desc = descricoes_medidas(p["nomes"])
        print(json.dumps({"tabela": {"Name": NOME_TABELA, "Description": descricao_tabela(p["nomes"])}, "medidas": [{"Name": n, "TableName": NOME_TABELA, "Description": d} for n, d in desc.items()]}, ensure_ascii=False))
        return 0
    if "--query" in sys.argv:
        print(consulta(p))
        return 0
    if "--esperado" in sys.argv:
        print("Medida;Tamanho;Soma")
        for n, t, s in tabela_esperada(p):
            print(f"{n};{t};{s}")
        print(f"{NOME_MEDIDA}_codigo;{len(p['codigo'])};")
        for chave, _, suf, _, _ in PACOTES:
            print(f"{NOME_MEDIDA}_{suf};{len(p['textos'][chave])};")
        print(f"{NOME_MEDIDA};{len(p['pagina'])};")
        return 0
    partes = " | ".join(f"dados {nome[3:]}: {len(p['textos'][chave]):,} em {len(p['pedacos'][pre])}" for chave, pre, _, nome, _ in PACOTES)
    print(f"código: {len(p['codigo']):,} caracteres em {len(p['pedacos']['cod'])} pedaços | {partes} (pedaços de até {tamanho:,})")
    print(f"{NOME_MEDIDA}: {len(p['pagina']):,} caracteres | {len(todos_os_nomes(p['nomes'])) + len(PACOTES) + 2} medidas | remontagem idêntica: sim | idêntica à página do protótipo: sim | JSON válido: sim | JavaScript: {scripts} bloco(s) com sintaxe válida")
    if "--teste" in sys.argv:
        print("modo teste: nada foi gravado")
        return 0
    if desktop_aberto() and "--forcar" not in sys.argv:
        print("O Power BI Desktop está aberto: feche o projeto antes (ele sobrescreveria os arquivos ao salvar). Nada foi gravado.")
        return 1
    TABELA.write_text(p["tmdl"], encoding="utf-8", newline="\n")
    mudou = registrar_no_modelo()
    trocas = ligar_visual()
    antiga = TABELA_ANTIGA.exists()
    if antiga:
        TABELA_ANTIGA.unlink()
    print(f"escrito: {TABELA.relative_to(RAIZ)} ({TABELA.stat().st_size:,} bytes) | model.tmdl mudou: {mudou} | referências do visual trocadas: {trocas} | tabela antiga {ANTIGAS[0]} removida: {antiga}")
    print(f"visual ligado a {NOME_MEDIDA}: {'sim' if visual_ligado() else 'NÃO'}")
    if not visual_ligado():
        print(f"Atenção: o visual HTML Content não aponta para {NOME_TABELA}.{NOME_MEDIDA}. No Power BI, arraste a medida {NOME_MEDIDA} para o campo Valores do visual.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
