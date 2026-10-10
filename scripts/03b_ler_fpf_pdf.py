import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fpf_pdf import ler_boletim, ler_boletim_detalhe, ler_comissao, ler_escalacao, ler_substituicoes, ler_sumula, texto_pdf

RAIZ = Path(__file__).resolve().parent.parent
PDFS = RAIZ / "data" / "raw" / "fpf_pdf" / "2026"
SAIDA = RAIZ / "data" / "processed" / "fpf"
JOGOS = RAIZ / "data" / "referencia" / "fpf_a1_2026_jogos.csv"


def gravar(arq, linhas, colunas):
    SAIDA.mkdir(parents=True, exist_ok=True)
    with open(SAIDA / arq, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas, delimiter=";", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for l in linhas:
            w.writerow({k: ("" if l.get(k) is None else l.get(k)) for k in colunas})


def principal():
    with open(JOGOS, encoding="utf-8", newline="") as f:
        jogos = {int(l["numero"]): l for l in csv.DictReader(f, delimiter=";")}
    partidas, gols, cartoes, boletins, erros = [], [], [], [], []
    escalacao, substituicoes, comissao = [], [], []
    ingressos, despesas, retencoes, rateio = [], [], [], []
    for n, j in sorted(jogos.items()):
        equipes = [j["mandante"], j["visitante"]]
        try:
            t = texto_pdf(PDFS / "sumula" / f"{n}.pdf", layout=True)
            for a in ler_escalacao(t, equipes):
                escalacao.append({"numero_jogo": n, "fase": j["fase"], "lado": "mandante" if a["equipe"] == equipes[0] else "visitante", **a})
            for ordem, s in enumerate(ler_substituicoes(t, equipes), start=1):
                substituicoes.append({"numero_jogo": n, "fase": j["fase"], "ordem": ordem, **s})
            for p in ler_comissao(t, equipes):
                comissao.append({"numero_jogo": n, "fase": j["fase"], **p})
        except Exception as e:
            erros.append(f"escalação {n}: {e}")
        try:
            s = ler_sumula(texto_pdf(PDFS / "sumula" / f"{n}.pdf"), equipes)
            s["numero_jogo"] = n
            s["mandante"], s["visitante"] = equipes
            s["fase"] = j["fase"]
            s["gols_mandante"], s["gols_visitante"] = s["placar_final"] if s["placar_final"] else (None, None)
            s["penaltis_mandante"], s["penaltis_visitante"] = s["penaltis"] if s["penaltis"] else (None, None)
            partidas.append(s)
            for g in s["gols"]:
                gols.append({"numero_jogo": n, "fase": j["fase"], **g})
            for a in s["advertencias"]:
                cartoes.append({"numero_jogo": n, "fase": j["fase"], "cartao": "amarelo", **a})
            for e in s["expulsoes"]:
                cartoes.append({"numero_jogo": n, "fase": j["fase"], "cartao": "2o_amarelo" if e["tipo"] == "2º Cartão Amarelo" else "vermelho", **e})
        except Exception as e:
            erros.append(f"súmula {n}: {e}")
        try:
            b = ler_boletim(texto_pdf(PDFS / "boletim" / f"{n}.pdf"))
            det = ler_boletim_detalhe(texto_pdf(PDFS / "boletim" / f"{n}.pdf", layout=True))
            b["numero_jogo"] = n
            b["total_b1"], b["total_b2"], b["total_b3"] = (det["subtotais"][k] for k in ("B1", "B2", "B3"))
            b["retencao_inss_informada"] = sum(x["valor"] for x in det["retencoes"])
            boletins.append(b)
            ingressos += [{"numero_jogo": n, **x} for x in det["ingressos"]]
            despesas += [{"numero_jogo": n, **x} for x in det["despesas"]]
            retencoes += [{"numero_jogo": n, **x} for x in det["retencoes"]]
            rateio += [{"numero_jogo": n, **x} for x in det["rateio"]]
        except Exception as e:
            erros.append(f"boletim {n}: {e}")

    gravar("sumula_partida.csv", partidas, ["numero_jogo", "fase", "rodada", "data", "horario", "estadio", "municipio", "mandante", "visitante", "gols_mandante", "gols_visitante", "penaltis_mandante", "penaltis_visitante", "arbitro", "assistente1", "assistente2", "quarto_arbitro", "var", "avar1", "avar2", "inicio_1t", "atraso_1t_min", "termino_1t", "acrescimo_1t_min", "inicio_2t", "atraso_2t_min", "termino_2t", "acrescimo_2t_min", "publicada_em"])
    gravar("sumula_gol.csv", gols, ["numero_jogo", "fase", "equipe", "numero", "jogador", "tipo", "minuto", "acrescimo", "periodo"])
    gravar("sumula_cartao.csv", cartoes, ["numero_jogo", "fase", "equipe", "cartao", "funcao", "numero", "pessoa", "minuto", "acrescimo", "periodo", "motivo"])
    gravar("boletim_partida.csv", boletins, ["numero_jogo", "data", "horario", "jogo", "ingressos_a_venda", "ingressos_devolvidos", "publico", "publico_pagante", "renda_bruta", "despesas_total", "renda_liquida", "receita_confere", "renda_confere", "total_b1", "total_b2", "total_b3", "retencao_inss_informada"])
    gravar("boletim_ingresso.csv", ingressos, ["numero_jogo", "ordem", "localidade", "a_venda", "devolvidos", "vendidos", "preco", "arrecadacao"])
    gravar("boletim_despesa.csv", despesas, ["numero_jogo", "bloco", "ordem", "rubrica", "valor"])
    gravar("boletim_retencao.csv", retencoes, ["numero_jogo", "rubrica", "valor"])
    gravar("boletim_rateio.csv", rateio, ["numero_jogo", "ordem", "clube", "percentual", "valor", "deducao_inss", "deducao_outras", "liquido"])
    gravar("sumula_escalacao.csv", escalacao, ["numero_jogo", "fase", "lado", "equipe", "numero", "nome", "situacao", "vinculo", "registro"])
    gravar("sumula_substituicao.csv", substituicoes, ["numero_jogo", "fase", "ordem", "equipe", "bloco", "numero_saiu", "nome_saiu", "numero_entrou", "nome_entrou", "tempo", "periodo", "minuto", "acrescimo", "motivo"])
    gravar("sumula_comissao.csv", comissao, ["numero_jogo", "fase", "equipe", "funcao", "nome", "nome_truncado"])

    print(f"súmulas lidas: {len(partidas)} de {len(jogos)} | gols {len(gols)} | cartões {len(cartoes)} | boletins lidos: {len(boletins)} de {len(jogos)}")
    print(f"escalações: {len(escalacao)} atletas | substituições: {len(substituicoes)} | comissão técnica: {len(comissao)} funções")
    print(f"boletins em detalhe: {len(ingressos)} linhas de ingresso | {len(despesas)} de despesa | {len(retencoes)} retenções | {len(rateio)} linhas de divisão da renda")
    for e in erros:
        print("ERRO", e)
    print(f"saída: {SAIDA}")


if __name__ == "__main__":
    principal()
