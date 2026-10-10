"""Confere a carga do Power BI contra o ETL, coluna por coluna.

Para cada coluna das 23 tabelas de dados, a consulta DAX devolve a quantidade de valores preenchidos e uma soma: a soma
dos números, a soma dos tamanhos dos textos ou o número serial das datas. O mesmo cálculo é refeito aqui, em Python, a
partir dos CSV de data/processed. Se uma tabela do modelo aberto estiver velha (ou uma coluna vier com outro tipo ou
outro texto), a linha dela diverge.

Uso:
  python scripts/15_conferir_carga_powerbi.py --query [INICIO FIM]   imprime a consulta DAX; rode no modelo aberto (MCP ou
                                                                     consulta DAX do Desktop), em lotes de uns 90 itens
                                                                     (por exemplo 0 90, 90 181 e 181 272)
  python scripts/15_conferir_carga_powerbi.py --comparar CSV [CSV]   compara os resultados com os CSV de data/processed

Antes de conferir, atualize o modelo aberto (botão Atualizar ou scripts/atualizar_modelo_aberto.ps1).
"""
import csv
import datetime
import importlib.util
import sys

from comum import RAIZ

PROC = RAIZ / "data" / "processed"
BASE_SERIAL = datetime.datetime(1899, 12, 30)
NUMERICOS = ("int64", "decimal", "double")


def modulo_powerquery():
    spec = importlib.util.spec_from_file_location("pq08", RAIZ / "scripts" / "08_gerar_powerquery.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def colunas():
    pq = modulo_powerquery()
    saida = []
    for t in pq.TABELAS:
        saida += [(t, nome, tipo) for nome, tipo, *_ in pq.tabela_pronta(t)["colunas"]]
        if t == "dim_clube":
            saida.append((t, "escudo_base64", "string"))
    return saida


def expressao_soma(t, c, tipo):
    if tipo in NUMERICOS:
        return f"SUM({t}[{c}])"
    if tipo == "string":
        return f"SUMX({t}, LEN({t}[{c}]))"
    return f"SUMX({t}, CONVERT({t}[{c}], DOUBLE))"


def consulta(inicio=None, fim=None):
    linhas = [f'ROW("t","{t}","c","{c}","n",COUNTA({t}[{c}]),"s",{expressao_soma(t, c, tp)})' for t, c, tp in colunas()]
    if inicio is not None:
        linhas = linhas[inicio:fim]
    return "EVALUATE\nUNION(\n" + ",\n".join(linhas) + "\n)"


def serial(texto, tipo):
    if tipo == "date":
        d = datetime.datetime.strptime(texto[:10], "%Y-%m-%d")
    elif tipo == "datetime":
        d = datetime.datetime.strptime(texto.replace("T", " ")[:16], "%Y-%m-%d %H:%M")
    else:
        d = datetime.datetime.strptime(texto, "%d/%m/%Y %H:%M")
    return (d - BASE_SERIAL).total_seconds() / 86400


def esperado():
    """{(tabela, coluna): (quantidade, soma, tipo)} calculado dos CSV do ETL; o escudo em base64 nasce no Power Query e fica de fora."""
    por_tabela = {}
    for t, c, tipo in colunas():
        if c != "escudo_base64":
            por_tabela.setdefault(t, []).append((c, tipo))
    saida = {}
    for t, cols in por_tabela.items():
        with open(PROC / f"{t}.csv", encoding="utf-8", newline="") as f:
            linhas = list(csv.DictReader(f, delimiter=";"))
        for c, tipo in cols:
            valores = [l[c] for l in linhas if l.get(c) not in (None, "")]
            if tipo == "int64":
                soma = sum(int(v) for v in valores)
            elif tipo in ("decimal", "double"):
                soma = sum(float(v) for v in valores)
            elif tipo == "string":
                soma = sum(len(v) for v in valores)
            else:
                soma = sum(serial(v, tipo) for v in valores)
            saida[(t, c)] = (len(valores), soma, tipo)
    return saida


def numero(texto):
    texto = texto.strip().strip('"')
    if texto == "":
        return None
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    return float(texto)


def tolerancia(soma, tipo):
    if tipo == "decimal":
        return 0.005
    if tipo in ("double", "datetime", "datetime_ptbr"):
        return 1e-6 * max(1.0, abs(soma))
    return 0.0


def comparar(arquivos):
    achados = {}
    for arquivo in arquivos:
        with open(arquivo, encoding="utf-8-sig", newline="") as f:
            leitor = csv.reader(f)
            next(leitor)
            for l in leitor:
                achados[(l[0], l[1])] = (numero(l[2]) or 0, numero(l[3]) or 0.0)
    esp = esperado()
    iguais, diferentes, faltam = 0, [], []
    for chave, (n, soma, tipo) in esp.items():
        if chave not in achados:
            faltam.append(chave)
        elif achados[chave][0] == n and abs(achados[chave][1] - soma) <= tolerancia(soma, tipo):
            iguais += 1
        else:
            diferentes.append((chave, (n, soma), achados[chave]))
    return {"colunas": len(esp), "iguais": iguais, "diferentes": diferentes, "sem_resultado": faltam}


def principal():
    if "--query" in sys.argv:
        i = sys.argv.index("--query")
        resto = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
        print(consulta(int(resto[0]), int(resto[1])) if len(resto) >= 2 else consulta())
        return 0
    if "--comparar" in sys.argv:
        r = comparar([a for a in sys.argv[sys.argv.index("--comparar") + 1:] if not a.startswith("--")])
        print(f"{r['colunas']} colunas esperadas | iguais: {r['iguais']} | diferentes: {len(r['diferentes'])} | sem resultado: {len(r['sem_resultado'])}")
        for (t, c), esp, ach in r["diferentes"][:30]:
            print(f"  DIFERE {t}.{c}: ETL (valores, soma) = {esp} x modelo = {ach}")
        for t, c in r["sem_resultado"][:30]:
            print(f"  SEM RESULTADO {t}.{c}")
        return 0 if not r["diferentes"] and not r["sem_resultado"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(principal())
