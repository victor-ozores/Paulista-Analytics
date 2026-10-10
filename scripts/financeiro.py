import re
import unicodedata
from decimal import Decimal

from comum import REF, ler_csv

ARQ_CATEGORIAS = REF / "ingresso_categorias.csv"
ARQ_GRUPOS = REF / "despesa_grupos.csv"
CONDICOES = ("preco_zero", "texto", "resto")
SEM_GRUPO = "Sem grupo"
PADRAO_SETOR_VISITANTE = re.compile(r"visitante")
BLOCOS = {"B1": "Aluguéis e seguros", "B2": "Taxas e impostos", "B3": "Despesas operacionais"}
COLUNAS_INGRESSO = ["id_ingresso", "id_partida", "ordem", "localidade", "categoria", "ordem_categoria", "setor_visitante", "ingressos", "preco", "arrecadacao"]
COLUNAS_DESPESA = ["id_despesa", "id_partida", "bloco_codigo", "bloco", "ordem", "rubrica", "grupo", "valor"]
COLUNAS_RATEIO = ["id_rateio", "id_partida", "id_clube", "lado", "percentual", "valor", "deducao_inss", "deducao_outras", "liquido"]


def texto_simples(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def ler_regras_ingresso(arq=ARQ_CATEGORIAS):
    regras = []
    for i, l in enumerate(ler_csv(arq), start=2):
        cond = l["condicao"]
        if cond not in CONDICOES:
            raise ValueError(f"{arq.name} linha {i}: condição '{cond}' desconhecida (use {', '.join(CONDICOES)})")
        if cond == "texto" and not l["expressao"]:
            raise ValueError(f"{arq.name} linha {i}: regra de texto sem expressão")
        if cond != "texto" and l["expressao"]:
            raise ValueError(f"{arq.name} linha {i}: a condição {cond} não usa expressão")
        regras.append({"ordem_regra": int(l["ordem_regra"]), "categoria": l["categoria"], "ordem_exibicao": int(l["ordem_exibicao"]), "condicao": cond, "expressao": l["expressao"], "explicacao": l["explicacao"], "padrao": re.compile(l["expressao"]) if cond == "texto" else None})
    regras.sort(key=lambda r: r["ordem_regra"])
    if not regras or [r["condicao"] for r in regras].count("resto") != 1 or regras[-1]["condicao"] != "resto":
        raise ValueError(f"{arq.name}: a última regra (e só ela) deve ser a condição resto")
    for campo in ("ordem_regra", "categoria", "ordem_exibicao"):
        if len({r[campo] for r in regras}) != len(regras):
            raise ValueError(f"{arq.name}: {campo} repetido")
    return regras


def classificar_ingresso(localidade, preco, regras):
    texto = texto_simples(localidade)
    for r in regras:
        if r["condicao"] == "preco_zero" and preco == 0:
            return r
        if r["condicao"] == "texto" and r["padrao"].search(texto):
            return r
        if r["condicao"] == "resto":
            return r


def setor_visitante(localidade):
    return 1 if PADRAO_SETOR_VISITANTE.search(texto_simples(localidade)) else 0


def ler_grupos_despesa(arq=ARQ_GRUPOS):
    grupos = {}
    for i, l in enumerate(ler_csv(arq), start=2):
        if l["bloco"] not in BLOCOS:
            raise ValueError(f"{arq.name} linha {i}: bloco '{l['bloco']}' desconhecido (use B1, B2 ou B3)")
        if not l["rubrica"] or not l["grupo"]:
            raise ValueError(f"{arq.name} linha {i}: rubrica ou grupo vazio")
        if l["rubrica"] in grupos:
            raise ValueError(f"{arq.name} linha {i}: rubrica repetida: {l['rubrica']}")
        grupos[l["rubrica"]] = l["grupo"]
    return grupos


def dinheiro_csv(v):
    return f"{Decimal(v):.2f}"


def montar_financeiro(ing_raw, desp_raw, rat_raw, jogos, regras, grupos):
    ingressos, despesas, rateio = [], [], []
    for r in ing_raw:
        j, ordem, preco = jogos[int(r["numero_jogo"])], int(r["ordem"]), Decimal(r["preco"])
        regra = classificar_ingresso(r["localidade"], preco, regras)
        ingressos.append({"id_ingresso": f'{j["id_partida"]}-{ordem:02d}', "id_partida": j["id_partida"], "ordem": ordem, "localidade": r["localidade"], "categoria": regra["categoria"], "ordem_categoria": regra["ordem_exibicao"], "setor_visitante": setor_visitante(r["localidade"]), "ingressos": int(r["vendidos"]), "preco": dinheiro_csv(preco), "arrecadacao": dinheiro_csv(r["arrecadacao"])})
    for r in desp_raw:
        if Decimal(r["valor"]) == 0:
            continue
        j, ordem = jogos[int(r["numero_jogo"])], int(r["ordem"])
        despesas.append({"id_despesa": f'{j["id_partida"]}-{r["bloco"]}-{ordem:02d}', "id_partida": j["id_partida"], "bloco_codigo": r["bloco"], "bloco": BLOCOS[r["bloco"]], "ordem": ordem, "rubrica": r["rubrica"], "grupo": grupos.get(r["rubrica"], SEM_GRUPO), "valor": dinheiro_csv(r["valor"])})
    for r in rat_raw:
        n = int(r["numero_jogo"])
        j = jogos[n]
        mandante, visitante = j["jogo"].split(" x ")
        if r["clube"] == mandante:
            lado, idc = "mandante", j["id_mandante"]
        elif r["clube"] == visitante:
            lado, idc = "visitante", j["id_visitante"]
        else:
            raise ValueError(f"divisão da renda do jogo {n}: '{r['clube']}' não é um dos clubes do boletim ({j['jogo']})")
        rateio.append({"id_rateio": f'{j["id_partida"]}-{idc}', "id_partida": j["id_partida"], "id_clube": idc, "lado": lado, "percentual": dinheiro_csv(r["percentual"]), "valor": dinheiro_csv(r["valor"]), "deducao_inss": dinheiro_csv(r["deducao_inss"]), "deducao_outras": dinheiro_csv(r["deducao_outras"]), "liquido": dinheiro_csv(r["liquido"])})
    return ingressos, despesas, rateio
