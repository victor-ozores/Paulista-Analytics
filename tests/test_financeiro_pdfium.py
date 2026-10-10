"""Conferência independente do financeiro: outro leitor de PDF (PDFium, via pypdfium2) e outro analisador, escritos sem olhar o leitor do projeto
(scripts/fpf_pdf.py, que usa pypdf). Confere, nos 72 boletins, o que as tabelas fato_ingresso, fato_partida e fato_rateio dizem.
É opcional: se o pypdfium2 ou os PDFs não estiverem na máquina, o teste é pulado."""
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import ler_csv  # noqa: E402

PDFS = RAIZ / "data" / "raw" / "fpf_pdf" / "2026" / "boletim"
PROC = RAIZ / "data" / "processed"
pdfium = pytest.importorskip("pypdfium2", reason="pypdfium2 não instalado (conferência opcional com outro leitor de PDF)")
precisa_dados = pytest.mark.skipif(not (PDFS / "1.pdf").exists() or not (PROC / "fato_ingresso.csv").exists(), reason="PDFs brutos ou tabelas ausentes")
DIN = r"-?[\d.]+,\d{2,3}"


def dec(s):
    return Decimal(s.replace(".", "").replace(",", "."))


def linhas_por_posicao(pagina, tol=4.5, folga=2.4):
    """Refaz as linhas do boletim pela posição de cada letra (a vírgula fica um pouco abaixo, por isso a tolerância de 4,5 pontos)."""
    tp = pagina.get_textpage()
    itens = []
    for i in range(tp.count_chars()):
        c = tp.get_text_range(i, 1)
        if c in ("\r", "\n", "\x00", "\ufffe") or c == "":
            continue
        esq, baixo, dir_, cima = tp.get_charbox(i)
        itens.append((c, esq, dir_, (baixo + cima) / 2))
    itens.sort(key=lambda x: -x[3])
    grupos = []
    for it in itens:
        if grupos and abs(grupos[-1][0] - it[3]) <= tol:
            grupos[-1][1].append(it)
        else:
            grupos.append([it[3], [it]])
    saida = []
    for _, g in grupos:
        g.sort(key=lambda x: x[1])
        texto, fim = "", None
        for c, esq, dir_, _ in g:
            if fim is not None and esq - fim > folga:
                texto += " "
            texto += c
            fim = dir_
        saida.append(" ".join(texto.split()))
    return saida


def ler(n):
    pdf = pdfium.PdfDocument(str(PDFS / f"{n}.pdf"))
    r = {"rotulos": [], "pares": [], "totais": None, "bruta": None, "despesas": None, "liquida": None, "rateio": []}
    for pagina in pdf:
        inicio = True
        for ln in pagina.get_textpage().get_text_range().splitlines():
            if inicio and re.fullmatch(rf"R\$ {DIN}(?: R\$ {DIN})?", ln):
                v = [dec(x) for x in re.findall(DIN, ln)]
                if len(v) == 2:
                    r["pares"].append(tuple(v))
                elif r["bruta"] is None:
                    r["bruta"] = v[0]
                continue
            inicio = False
            m = re.fullmatch(r"TOTAIS (\d+) (\d+) (\d+)", ln)
            if m:
                r["totais"] = tuple(int(x) for x in m.groups())
                continue
            m = re.fullmatch(r"(.+?) (\d+) (\d+) (\d+)", ln)
            if m and not ln.startswith(("Data:", "Jogo:", "LOCALIDADES")):
                r["rotulos"].append((m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))))
        for ln in linhas_por_posicao(pagina):
            m = re.match(rf"TOTAL DAS DESPESAS .*?R\$ ({DIN})$", ln)
            if m:
                r["despesas"] = dec(m.group(1))
            m = re.match(rf"RENDA L.QUIDA \(RECEITA.*?R\$ ({DIN})$", ln)
            if m:
                r["liquida"] = dec(m.group(1))
            m = re.match(rf"(.+?) - \(([\d,.]+)%\) R\$ ({DIN}) R\$ ({DIN}) R\$ ({DIN}) R\$ ({DIN})$", ln)
            if m:
                r["rateio"].append(tuple(dec(m.group(i)) for i in (3, 4, 5, 6)))
    return r


@precisa_dados
def test_os_72_boletins_lidos_por_outro_leitor_de_pdf_batem_com_as_tabelas():
    L = lambda nome: ler_csv(PROC / f"{nome}.csv")
    partidas = {int(p["numero_jogo"]): p for p in L("fato_partida")}
    ingressos, rateio = {}, {}
    for i in L("fato_ingresso"):
        ingressos.setdefault(i["id_partida"], []).append(i)
    for x in L("fato_rateio"):
        rateio.setdefault(x["id_partida"], []).append(x)
    falhas, soma = [], {"publico": 0, "pagantes": 0, "gratuitos": 0, "visitante": 0, "bruta": Decimal(0), "despesas": Decimal(0), "liquida": Decimal(0), "receber": Decimal(0), "linhas": 0}
    for n in range(1, 73):
        p = partidas[n]
        idp = p["id_partida"]
        x = ler(n)
        tab = ingressos[idp]
        nl = len(x["rotulos"])
        pares = x["pares"][:nl]
        vendidos = sum(r[3] for r in x["rotulos"])
        gratis = sum(r[3] for r, pr in zip(x["rotulos"], pares) if pr[0] == 0)
        pagos = sum(r[3] for r, pr in zip(x["rotulos"], pares) if pr[0] > 0)
        visitante = sum(r[3] for r in x["rotulos"] if "visitante" in r[0].lower())
        div = x["rateio"]
        certo = {
            "linhas": nl == len(tab) and len(x["pares"]) >= nl,
            "público": x["totais"] is not None and vendidos == x["totais"][2] == int(p["publico_boletim"]),
            "pagantes": pagos == int(p["publico_pagante"]),
            "gratuitos": gratis == sum(int(i["ingressos"]) for i in tab if i["categoria"] == "Gratuidade por lei"),
            "torcida visitante": visitante == sum(int(i["ingressos"]) for i in tab if i["setor_visitante"] == "1"),
            "preço x vendidos": all(pr[0] * r[3] == pr[1] for r, pr in zip(x["rotulos"], pares)),
            "renda bruta": x["bruta"] == sum(pr[1] for pr in x["pares"]) == Decimal(p["renda_bruta"]),
            "despesas": x["despesas"] == Decimal(p["despesas_total"]),
            "renda líquida": x["liquida"] == Decimal(p["renda_liquida"]) and x["bruta"] is not None and x["despesas"] is not None and x["liquida"] == x["bruta"] - x["despesas"],
            "divisão da renda": len(div) == 2 and sum(r[3] for r in div) == sum(Decimal(r["liquido"]) for r in rateio[idp]) and sum(r[1] + r[2] for r in div) == sum(Decimal(r["deducao_inss"]) + Decimal(r["deducao_outras"]) for r in rateio[idp]),
        }
        if not all(certo.values()):
            falhas.append((n, [k for k, v in certo.items() if not v]))
            continue
        soma["publico"] += vendidos
        soma["pagantes"] += pagos
        soma["gratuitos"] += gratis
        soma["visitante"] += visitante
        soma["bruta"] += x["bruta"]
        soma["despesas"] += x["despesas"]
        soma["liquida"] += x["liquida"]
        soma["receber"] += sum(r[3] for r in div)
        soma["linhas"] += nl
    assert falhas == []
    assert soma == {"publico": 784369, "pagantes": 761489, "gratuitos": 22880, "visitante": 69685, "bruta": Decimal("44730003.80"), "despesas": Decimal("20404747.14"), "liquida": Decimal("24325256.66"), "receber": Decimal("24171721.26"), "linhas": 2388}
