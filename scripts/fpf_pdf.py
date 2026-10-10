import re
import statistics
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

FUNCOES = r"(?:Auxiliar Técnico|Técnico|Preparador Físico|Médico|Massagista|Treinador de goleiro|Supervisor|Diretor|Roupeiro|Fisioterapeuta|Analista|Auxiliar|Delegado)"
TEMPO = r"(?:\d{1,3}:\d{2}|\+ ?\d+)"
PERIODO = r"(?:1T|2T|INT|AJ|PJ)"
ATLETA = re.compile(r"(\d{1,3})\s+(.+?)\s+([TR])\s+([PA])\s+(\d+/\d{2})")
ROTULO_FUNCAO = re.compile(FUNCOES)


def texto_pdf(arq, cache=True, layout=False):
    arq = Path(arq)
    txt = arq.parent.parent / ("txt_layout" if layout else "txt") / f"{arq.parent.name}_{arq.stem}.txt"
    if cache and txt.exists():
        return txt.read_text(encoding="utf-8")
    modo = {"extraction_mode": "layout"} if layout else {}
    t = "\n".join((p.extract_text(**modo) or "") for p in PdfReader(arq).pages)
    if cache:
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(t, encoding="utf-8")
    return t


def minuto(tempo, periodo):
    if tempo.startswith("+"):
        return (45 if periodo == "1T" else 90), int(tempo.replace("+", "").strip())
    return int(tempo.split(":")[0]), 0


def secao(t, ini, fim):
    i = t.find(ini)
    if i < 0:
        return ""
    j = t.find(fim, i + len(ini))
    return t[i + len(ini): j if j > 0 else None]


def separar_por_equipe(linhas, equipes):
    ordenadas = sorted(equipes, key=len, reverse=True)
    blocos = []
    for ln in linhas:
        ln = ln.rstrip()
        eq = next((e for e in ordenadas if ln.startswith(e + " ")), None)
        if eq:
            blocos.append([eq, ln[len(eq) + 1:], []])
        elif blocos and ln and not ln.startswith("Federação Paulista") and not re.match(r"^\d+ Página", ln) and not ln.startswith(" AJ =") and not ln.startswith(" NR ="):
            blocos[-1][2].append(ln)
    return blocos


def pessoa(resto):
    m = re.match(rf"^(?P<funcao>{FUNCOES}) - (?P<nome>.+)$", resto)
    if m:
        return None, m.group("funcao"), m.group("nome").strip()
    m = re.match(r"^(?P<num>\d+) (?P<nome>.+)$", resto)
    if m:
        return int(m.group("num")), "Atleta", m.group("nome").strip()
    return None, "Atleta", resto.strip()


def ler_sumula(t, equipes):
    d = {}
    m = re.search(r"Jogo: (\d+) / (\d{4})", t)
    d["numero"] = int(m.group(1)) if m else None
    m = re.search(r"Rodada: (\d+)", t)
    d["rodada"] = int(m.group(1)) if m else None
    m = re.search(r"Data: (\S+) Horário: (\S+) Estádio: (.+?) / (.+)", t)
    d["data"], d["horario"], d["estadio"], d["municipio"] = (m.group(i).strip() for i in range(1, 5)) if m else (None,) * 4
    for chave, rot in (("arbitro", "Árbitro"), ("assistente1", "Árbitro Assistente 1"), ("assistente2", "Árbitro Assistente 2"), ("quarto_arbitro", "Quarto Árbitro"), ("var", "VAR"), ("avar1", "AVAR1"), ("avar2", "AVAR2")):
        m = re.search(rf"^{rot}: (.+)$", t, re.M)
        d[chave] = m.group(1).strip() if m else None
    for tag, rot in (("1t", "1º Tempo"), ("2t", "2º Tempo")):
        m = re.search(rf"Início {rot}: (\d{{2}}:\d{{2}}) Atraso: (Não Houve|\d+ min)", t)
        d[f"inicio_{tag}"] = m.group(1) if m else None
        d[f"atraso_{tag}_min"] = (0 if m and m.group(2) == "Não Houve" else int(re.sub(r"\D", "", m.group(2)))) if m else None
        m = re.search(rf"Término {rot}: (\d{{2}}:\d{{2}}) Acréscimo: (Não Houve|\d+ min)", t)
        d[f"termino_{tag}"] = m.group(1) if m else None
        d[f"acrescimo_{tag}_min"] = (0 if m and m.group(2) == "Não Houve" else int(re.sub(r"\D", "", m.group(2)))) if m else None
    m = re.search(r"Resultado do 1º Tempo: (\d+) X (\d+) Resultado Final: (\d+) X (\d+)(?: Resultado Pênalti: (\d+) X (\d+))?", t)
    d["placar_1t"] = (int(m.group(1)), int(m.group(2))) if m else None
    d["placar_final"] = (int(m.group(3)), int(m.group(4))) if m else None
    d["penaltis"] = (int(m.group(5)), int(m.group(6))) if m and m.group(5) is not None else None
    m = re.search(r"Publicação da Súmula: (\S+ \S+)", t)
    d["publicada_em"] = m.group(1) if m else None

    gols = []
    for eq, resto, _ in separar_por_equipe(secao(t, "\nGols\n", "Federação Paulista").splitlines(), equipes):
        m = re.match(rf"^(?P<num>\d+) (?P<nome>.+?) (?P<tipo>NR|PN|CT|FT) (?P<tempo>{TEMPO}) (?P<per>1T|2T)$", resto)
        if not m:
            raise ValueError(f"gol não reconhecido: {eq} {resto}")
        mi, ac = minuto(m.group("tempo"), m.group("per"))
        gols.append({"equipe": eq, "numero": int(m.group("num")), "jogador": m.group("nome").strip(), "tipo": m.group("tipo"), "minuto": mi, "acrescimo": ac, "periodo": m.group("per")})
    d["gols"] = gols

    adv = []
    sec = secao(t, "\nAdvertências\n", "\nExpulsões\n")
    for eq, resto, extra in separar_por_equipe(sec.splitlines(), equipes):
        m = re.match(rf"^(?P<quem>.+?)(?: (?P<tempo>{TEMPO}))?(?: - | )(?P<per>{PERIODO})$", resto)
        if not m:
            raise ValueError(f"advertência não reconhecida: {eq} {resto}")
        num, funcao, nome = pessoa(m.group("quem"))
        mi, ac = minuto(m.group("tempo"), m.group("per")) if (m.group("per") in ("1T", "2T") and m.group("tempo")) else (None, 0)
        adv.append({"equipe": eq, "numero": num, "funcao": funcao, "pessoa": nome, "minuto": mi, "acrescimo": ac, "periodo": m.group("per"), "motivo": " ".join(x.replace("Motivo:", "").strip() for x in extra)})
    d["advertencias"] = adv

    exp = []
    sec = secao(t, "\nExpulsões\n", "Motivo de atraso")
    linhas = [x for x in sec.splitlines()]
    i = 0
    while i < len(linhas):
        m = re.match(rf"^(?:(?P<tempo>{TEMPO}|-) )?(?P<per>{PERIODO}) (?P<resto>.+)$", linhas[i].strip())
        if m:
            resto = m.group("resto")
            eq = next((e for e in sorted(equipes, key=len, reverse=True) if resto.endswith(" " + e)), None)
            if not eq:
                raise ValueError(f"expulsão sem equipe: {resto}")
            num, funcao, nome = pessoa(resto[: -len(eq) - 1])
            tipo, motivo, k = None, [], i + 1
            while k < len(linhas) and not re.match(rf"^(?:(?:{TEMPO}|-) )?{PERIODO} ", linhas[k].strip()) and not linhas[k].startswith("Federação Paulista") and not re.match(r"^\d+ Página", linhas[k]):
                mt = re.match(r"^(2º Cartão Amarelo|Cartão Vermelho|Cartão Amarelo)\s*(?:Motivo:)?\s*(.*)$", linhas[k].strip())
                if mt and tipo is None:
                    tipo = mt.group(1)
                    if mt.group(2):
                        motivo.append(mt.group(2))
                else:
                    motivo.append(linhas[k].replace("Motivo:", "").strip())
                k += 1
            mi, ac = minuto(m.group("tempo"), m.group("per")) if (m.group("per") in ("1T", "2T") and m.group("tempo") and m.group("tempo") != "-") else (None, 0)
            exp.append({"equipe": eq, "numero": num, "funcao": funcao, "pessoa": nome, "tipo": tipo, "minuto": mi, "acrescimo": ac, "periodo": m.group("per"), "motivo": " ".join(motivo).strip()})
            i = k
        else:
            i += 1
    d["expulsoes"] = exp
    return d


def ler_escalacao(t, equipes):
    linhas = secao(t, "Relação de Jogadores", "T = Titular").splitlines()
    cab = next((l for l in linhas if "Nome Completo" in l), None)
    k1 = cab.find("Nº") if cab else -1
    k2 = cab.find("Nº", k1 + 1) if k1 >= 0 else -1
    if k2 < 0:
        raise ValueError("cabeçalho da relação de jogadores não encontrado")
    limite = (k1 + k2) / 2
    atletas = []
    for ln in linhas:
        achados = list(ATLETA.finditer(ln))
        if len(achados) > 2:
            raise ValueError(f"linha com mais de dois atletas: {ln.strip()}")
        lados = [0, 1] if len(achados) == 2 else [0 if m.start(1) < limite else 1 for m in achados]
        for lado, m in zip(lados, achados):
            atletas.append({"equipe": equipes[lado], "numero": int(m.group(1)), "nome": m.group(2).strip(), "situacao": m.group(3), "vinculo": m.group(4), "registro": m.group(5)})
    return atletas


def ler_comissao(t, equipes):
    achados = []
    for ln in secao(t, "Comissão Técnica", "Substituições").splitlines():
        marcas = list(ROTULO_FUNCAO.finditer(ln))
        if len(marcas) > 2:
            raise ValueError(f"linha da comissão com mais de duas funções: {ln.strip()}")
        achados.append([(m.start(), m.group(0), ln[m.end(): marcas[k + 1].start() if k + 1 < len(marcas) else len(ln)].strip()) for k, m in enumerate(marcas)])
    pares = [a for a in achados if len(a) == 2]
    limite = (statistics.median(a[0][0] for a in pares) + statistics.median(a[1][0] for a in pares)) / 2 if pares else 50
    pessoas = []
    for a in achados:
        lados = [0, 1] if len(a) == 2 else [0 if x[0] < limite else 1 for x in a]
        for lado, (_, funcao, nome) in zip(lados, a):
            pessoas.append({"equipe": equipes[lado], "funcao": funcao, "nome": nome or None, "nome_truncado": 1 if nome.endswith("...") else 0})
    return pessoas


def ler_substituicoes(t, equipes):
    nomes = "|".join(re.escape(e) for e in sorted(equipes, key=len, reverse=True))
    linha = re.compile(rf"^\s*(?P<equipe>{nomes})\s+(?P<ns>\d+)\s+(?P<sai>.+?)\s+(?P<ne>\d+)\s+(?P<entra>.+?)\s+(?P<tempo>\d{{1,3}}:\d{{2}}|\+ ?\d+|-)\s+(?P<per>1T|2T|INT)\s*$")
    ignorar = re.compile(r"^(Equipe\s+Nº\s+Saiu.*|NÃO HOUVE SUBSTITUIÇÕES|Federação Paulista.*|\d+\s+Página.*)$")
    linhas = t.splitlines()
    marcas = {}
    for i, l in enumerate(linhas):
        if l.strip() in ("Substituições", "Substituições por concussão", "Gols"):
            marcas.setdefault(l.strip(), i)
    if len(marcas) < 3:
        raise ValueError("blocos de substituições não encontrados")
    subs = []
    for bloco, ini, fim in (("regular", marcas["Substituições"], marcas["Substituições por concussão"]), ("concussao", marcas["Substituições por concussão"], marcas["Gols"])):
        atual = None
        for ln in linhas[ini + 1: fim]:
            txt = ln.strip()
            m = linha.match(ln)
            if m:
                tempo, per = m.group("tempo"), m.group("per")
                mi, ac = (None, 0) if tempo == "-" else minuto(tempo, per)
                atual = {"equipe": m.group("equipe"), "numero_saiu": int(m.group("ns")), "nome_saiu": m.group("sai").strip(), "numero_entrou": int(m.group("ne")), "nome_entrou": m.group("entra").strip(), "tempo": tempo, "periodo": per, "minuto": mi, "acrescimo": ac, "bloco": bloco, "motivo": ""}
                subs.append(atual)
            elif not txt or ignorar.match(txt):
                continue
            elif atual is not None and bloco == "concussao":
                atual["motivo"] = f'{atual["motivo"]} {txt.replace("Motivo:", "").strip()}'.strip()
            else:
                raise ValueError(f"substituição não reconhecida: {txt}")
    return subs


def dinheiro(s):
    return Decimal(s.replace("R$", "").replace(".", "").replace(",", ".").strip())


def ler_boletim(t):
    d = {}
    m = re.search(r"BOLETIM FINANCEIRO (\d+)/(\d{4})", t)
    d["numero"] = int(m.group(1)) if m else None
    m = re.search(r"Data: (\d{2}/\d{2}/\d{4}) (\d{2}:\d{2}) Jogo: (.+?)\s*ESTÁDIO", t)
    d["data"], d["horario"], d["jogo"] = (m.group(1), m.group(2), m.group(3)) if m else (None,) * 3
    m = re.findall(r"^TOTAIS (\d+) (\d+) (\d+)$", t, re.M)
    if len(m) != 1:
        raise ValueError("linha TOTAIS não encontrada exatamente uma vez")
    d["ingressos_a_venda"], d["ingressos_devolvidos"], d["publico"] = (int(x) for x in m[0])

    linhas = t.splitlines()
    pares, bruta = [], None
    for ln in linhas:
        v = re.findall(r"R\$ ?-?[\d.]+,\d{2,3}", ln)
        if len(v) == 2 and ln.strip() == "".join(v):
            pares.append((dinheiro(v[0]), dinheiro(v[1])))
        elif len(v) == 1 and ln.strip() == v[0] and bruta is None and len(pares) > 0 and "BOLETIM" not in ln:
            bruta = dinheiro(v[0])
            break
    d["renda_bruta"] = bruta
    d["receita_confere"] = bruta is not None and sum(a for _, a in pares) == bruta

    todos = []
    for ln in linhas:
        v = re.findall(r"R\$ ?-?[\d.]+,\d{2,3}", ln)
        if len(v) == 2 and ln.strip() == "".join(v):
            continue
        todos.extend(dinheiro(x) for x in v)
    achado = None
    if bruta is not None:
        for i, x in enumerate(todos):
            if x <= 0 or x == bruta:
                continue
            for y in todos[i + 1:]:
                if x + y == bruta and todos.count(y) >= 2:
                    achado = (x, y)
                    break
            if achado:
                break
    d["despesas_total"], d["renda_liquida"] = achado if achado else (None, None)
    d["renda_confere"] = achado is not None

    d["publico_pagante"] = None
    inteiros = [(a / p_) for p_, a in pares if p_ > 0]
    if pares and all(x == int(x) for x in inteiros):
        pag = int(sum(inteiros))
        if 0 <= pag <= d["publico"]:
            d["publico_pagante"] = pag
    return d


VALOR = r"(-?[\d.]+,\d{2,3}|-)"
LINHA_INGRESSO = re.compile(r"^(?P<localidade>\S.*?)\s+(?P<a_venda>\d+)\s+(?P<devolvidos>\d+)\s+(?P<vendidos>\d+)\s+R\$\s*(?P<preco>-?[\d.]+,\d{2})\s+R\$\s*(?P<arrecadacao>-?[\d.]+,\d{2})$")
LINHA_TOTAIS = re.compile(r"^TOTAIS\s+(\d+)\s+(\d+)\s+(\d+)\s+R\$\s*(-?[\d.]+,\d{2})$")
LINHA_DESPESA = re.compile(rf"^(?P<rubrica>\S.*?)\s+R\$\s+(?P<valor>{VALOR})$")
LINHA_SUBTOTAL = re.compile(rf"^TOTAL (B[123])\s+R\$\s+(?P<valor>{VALOR})$")
LINHA_RATEIO = re.compile(rf"^(?P<clube>\S.*?) - \((?P<percentual>[\d.,]+)%\)\s+R\$\s*(?P<valor>{VALOR})\s+R\$\s*(?P<inss>{VALOR})\s+R\$\s*(?P<outras>{VALOR})\s+R\$\s*(?P<liquido>{VALOR})$")
LINHA_EM_BRANCO = re.compile(rf"^R\$\s*(?:{VALOR})(?:\s+R\$\s*{VALOR})?$")
BLOCOS_DESPESA = {"B1": "Aluguéis e seguros", "B2": "Taxas e impostos", "B3": "Despesas operacionais"}


def valor_boletim(s):
    return Decimal(0) if s.strip() == "-" else dinheiro(s)


def ler_boletim_detalhe(t):
    d = {"ingressos": [], "despesas": [], "retencoes": [], "subtotais": {}, "rateio": [], "totais": None, "total_despesas": None, "renda_liquida": None}
    estado, bloco = "antes", None
    for ln in t.splitlines():
        s = ln.strip()
        if not s:
            continue
        if estado == "antes":
            if s.startswith("LOCALIDADES"):
                estado = "ingressos"
            continue
        if estado == "ingressos":
            m = LINHA_INGRESSO.match(s)
            if m:
                d["ingressos"].append({"ordem": len(d["ingressos"]) + 1, "localidade": m.group("localidade"), "a_venda": int(m.group("a_venda")), "devolvidos": int(m.group("devolvidos")), "vendidos": int(m.group("vendidos")), "preco": dinheiro(m.group("preco")), "arrecadacao": dinheiro(m.group("arrecadacao"))})
            elif (m := LINHA_TOTAIS.match(s)):
                d["totais"] = {"a_venda": int(m.group(1)), "devolvidos": int(m.group(2)), "vendidos": int(m.group(3)), "arrecadacao": dinheiro(m.group(4))}
                estado = "despesas"
            elif not LINHA_EM_BRANCO.match(s):
                raise ValueError(f"linha de ingresso não reconhecida: {s}")
        elif estado == "despesas":
            m = re.match(r"^(B[123]) - ", s)
            if m:
                bloco = m.group(1)
            elif (m := LINHA_SUBTOTAL.match(s)):
                d["subtotais"][m.group(1)] = valor_boletim(m.group("valor"))
            elif s.startswith("TOTAL DAS DESPESAS"):
                d["total_despesas"] = valor_boletim(s.split("R$")[-1])
                estado = "retencoes"
            elif bloco and (m := LINHA_DESPESA.match(s)):
                d["despesas"].append({"bloco": bloco, "ordem": sum(1 for x in d["despesas"] if x["bloco"] == bloco) + 1, "rubrica": m.group("rubrica"), "valor": valor_boletim(m.group("valor"))})
            elif not (bloco and LINHA_EM_BRANCO.match(s)):
                raise ValueError(f"linha de despesa não reconhecida: {s}")
        elif estado == "retencoes":
            if s.startswith("RENDA LÍQUIDA"):
                d["renda_liquida"] = valor_boletim(s.split("R$")[-1])
                estado = "rateio"
            elif (m := LINHA_DESPESA.match(s)):
                d["retencoes"].append({"rubrica": m.group("rubrica"), "valor": valor_boletim(m.group("valor"))})
            elif not LINHA_EM_BRANCO.match(s):
                raise ValueError(f"linha de retenção não reconhecida: {s}")
        elif estado == "rateio":
            m = LINHA_RATEIO.match(s)
            if m:
                d["rateio"].append({"ordem": len(d["rateio"]) + 1, "clube": m.group("clube"), "percentual": Decimal(m.group("percentual").replace(".", "").replace(",", ".")), "valor": valor_boletim(m.group("valor")), "deducao_inss": valor_boletim(m.group("inss")), "deducao_outras": valor_boletim(m.group("outras")), "liquido": valor_boletim(m.group("liquido"))})
            elif s.startswith("Assinado digitalmente"):
                break
    if estado != "rateio" or d["totais"] is None or d["total_despesas"] is None or d["renda_liquida"] is None or set(d["subtotais"]) != set(BLOCOS_DESPESA) or not d["rateio"]:
        raise ValueError(f"boletim incompleto (parou em '{estado}', subtotais {sorted(d['subtotais'])}, rateio {len(d['rateio'])} linhas)")
    return d
