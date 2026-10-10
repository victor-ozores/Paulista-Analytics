"""Tela de versus (duelo de clubes): dados reais, fora do Power BI.

Gera prototype/versus/index.html (abre direto no navegador) e sandbox.html (mesma página dentro de um
iframe com sandbox, como o visual HTML Content) a partir de prototype/versus/fragmento.html, trocando
`__DADOS__` pelos dados de data/processed/. O fragmento é a fonte; os outros dois são gerados.

Os números do protótipo vêm das tabelas e do gabarito (ref_indicadores.csv); o script confere o que
repete o gabarito e para se algo não bater. Nas medidas do Power BI esses números virão do DAX.

Uso: python scripts/11_montar_versus.py
"""
import base64
import colorsys
import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from comum import RAIZ, ler_csv
from disciplina import categorias_em_ordem, classificar_motivo, ler_regras_motivo
from nomes import curto_por_pessoa, nome_de_comissao

PROC = RAIZ / "data" / "processed"
SAIDA = RAIZ / "prototype" / "versus"
FASE_COD = {"PRIMEIRA FASE": 1, "QUARTAS DE FINAL": 2, "SEMIFINAL": 3, "FINAL": 4}
FASE_ALCANCADA = {1: "1ª fase", 2: "Quartas de final", 3: "Semifinal"}
TIPO = {"gol": "g", "gol_penalti": "p", "gol_falta": "f", "gol_contra": "c", "amarelo": "a", "segundo_amarelo": "s", "vermelho": "v"}
PERIODO = {"1T": 1, "2T": 2}
ACO_ESCUDO = "#2b3340"
ACO_CLARO = "#c9d1dc"
COR_MANUAL = {"Corinthians": (ACO_ESCUDO, "#ffffff")}


def curto(nome):
    for pre in ("Grêmio ", "Red Bull "):
        if nome.startswith(pre):
            nome = nome[len(pre):]
    for suf in (" SAF", " FC"):
        if nome.endswith(suf):
            nome = nome[: -len(suf)]
    return nome


def hexa(rgb):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def cores_escudo(arq):
    """Cor principal e secundária tiradas do escudo oficial (pixels saturados, sem branco nem preto)."""
    img = Image.open(arq).convert("RGBA")
    caixas = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    opacos = 0
    for r, g, b, a in img.getdata():
        if a < 200:
            continue
        opacos += 1
        mx, mn = max(r, g, b), min(r, g, b)
        if mx < 60 or mn > 215 or (mx - mn) / mx < 0.35:
            continue
        c = caixas[(r // 32, g // 32, b // 32)]
        c[0] += 1
        c[1] += r
        c[2] += g
        c[3] += b
    saturados = sum(c[0] for c in caixas.values())
    if not caixas or saturados < 0.04 * opacos:
        return ACO_ESCUDO, ACO_CLARO
    medias = sorted(((c[0], (c[1] / c[0], c[2] / c[0], c[3] / c[0])) for c in caixas.values()), key=lambda x: -x[0])
    principal = medias[0][1]
    hp = colorsys.rgb_to_hsv(*(v / 255 for v in principal))[0]
    segunda = None
    for n, rgb in medias[1:]:
        h = colorsys.rgb_to_hsv(*(v / 255 for v in rgb))[0]
        dh = min(abs(h - hp), 1 - abs(h - hp))
        if dh > 0.07 and n >= 0.15 * medias[0][0]:
            segunda = rgb
            break
    if segunda is None:
        segunda = tuple(v + (255 - v) * 0.55 for v in principal)
    return hexa(principal), hexa(segunda)


def montar_dados():
    clubes = ler_csv(PROC / "dim_clube.csv")
    partidas = sorted(ler_csv(PROC / "fato_partida.csv"), key=lambda p: (p["data_hora_programada"], int(p["numero_jogo"])))
    eventos = ler_csv(PROC / "fato_evento.csv")
    fases = {f["id_fase"]: f["nome_fase"] for f in ler_csv(PROC / "dim_fase.csv")}
    estadios = {e["id_estadio"]: e for e in ler_csv(PROC / "dim_estadio.csv")}
    arbitros = {a["id_arbitro"]: a["nome"] for a in ler_csv(PROC / "dim_arbitro.csv")}
    ref = ler_csv(PROC / "ref_indicadores.csv")
    cls = {l["id_clube"]: l for l in ler_csv(PROC / "ref_classificacao_primeira_fase.csv")}
    regras = ler_csv(PROC / "resultado_regra.csv")
    log = ler_csv(PROC / "fato_inconsistencia.csv")
    geral = {l["id_indicador"]: l["valor"] for l in ref if l["escopo"] == "geral"}

    por_ind = defaultdict(dict)
    for l in ref:
        if l["escopo"] == "clube":
            por_ind[l["id_indicador"]][l["id_clube"]] = float(l["valor"]) if l["valor"] != "" else None
    curtos_pessoa = curto_por_pessoa(eventos, ler_csv(PROC / "fato_escalacao.csv"), ler_csv(PROC / "dim_atleta.csv"))

    def nome_pessoa(pessoa):
        return curtos_pessoa[pessoa] if pessoa in curtos_pessoa else nome_de_comissao(pessoa)

    artilheiros = defaultdict(list)
    for l in ref:
        if l["escopo"] == "artilheiro":
            artilheiros[l["id_clube"]].append((nome_pessoa(l["chave"]), int(float(l["valor"])), l["chave"]))

    regras_motivo = ler_regras_motivo()
    exibicao = categorias_em_ordem(regras_motivo)
    motivos = [r["categoria"] for r in exibicao]
    indice_motivo = {r["categoria"]: i for i, r in enumerate(exibicao)}

    def motivo_id(texto):
        if not texto:
            return -1
        return indice_motivo[classificar_motivo(texto, regras_motivo)["categoria"]]

    ev_jogo = defaultdict(list)
    for e in eventos:
        if e["tipo_evento"] not in TIPO:
            continue
        ev_jogo[e["id_partida"]].append(e)

    jogos, jogos_clube = [], defaultdict(list)
    forma = defaultdict(list)
    stats = defaultdict(lambda: dict(j=0, v=0, e=0, d=0, gp=0, gc=0))
    casa = defaultdict(Counter)
    for p in partidas:
        gm, gv = int(p["gols_mandante"]), int(p["gols_visitante"])
        m, v = p["id_clube_mandante"], p["id_clube_visitante"]
        casa[m][p["id_estadio"]] += 1
        for c, gf, gs in ((m, gm, gv), (v, gv, gm)):
            s = stats[c]
            s["j"] += 1
            s["gp"] += gf
            s["gc"] += gs
            r = "V" if gf > gs else ("E" if gf == gs else "D")
            s["v" if r == "V" else "e" if r == "E" else "d"] += 1
            decidido_penaltis = p["penaltis_mandante"] != "" and gf == gs
            if decidido_penaltis:
                ganhou = (int(p["penaltis_mandante"]) > int(p["penaltis_visitante"])) == (c == m)
                forma[c].append(["V" if ganhou else "D", 1, p["id_partida"]])
            else:
                forma[c].append([r, 0, p["id_partida"]])
        evs = []
        for e in sorted(ev_jogo[p["id_partida"]], key=lambda e: e["id_evento"]):
            alvo = e["id_clube_creditado"] if e["tipo_evento"].startswith("gol") else e["id_clube"]
            lado = 0 if alvo == m else 1
            minuto = int(e["minuto"]) if e["minuto"] != "" else None
            evs.append([TIPO[e["tipo_evento"]], lado, PERIODO.get(e["periodo"], 3), minuto, int(e["acrescimo"] or 0), nome_pessoa(e["pessoa"]), e["numero_camisa"], motivo_id(e["motivo"])])
        est = estadios[p["id_estadio"]]
        j = {
            "i": p["id_partida"], "n": int(p["numero_jogo"]), "f": FASE_COD[fases[p["id_fase"]]], "r": int(p["rodada"]),
            "d": p["data_jogo"], "h": p["hora_programada"], "m": m, "v": v, "gm": gm, "gv": gv,
            "pm": int(p["penaltis_mandante"]) if p["penaltis_mandante"] != "" else None,
            "pv": int(p["penaltis_visitante"]) if p["penaltis_visitante"] != "" else None,
            "e": est["nome_fpf"], "c": est["municipio"], "pu": int(p["publico_boletim"]), "rl": float(p["renda_liquida"]),
            "ar": arbitros.get(p["id_arbitro"], ""), "ev": evs,
        }
        jogos.append(j)

    alcance = {c["id_clube"]: 1 for c in clubes}
    for j in jogos:
        for c in (j["m"], j["v"]):
            alcance[c] = max(alcance[c], j["f"])
    final = [j for j in jogos if j["f"] == 4]
    pontos_final = Counter()
    for j in final:
        pontos_final[j["m"]] += 3 if j["gm"] > j["gv"] else (1 if j["gm"] == j["gv"] else 0)
        pontos_final[j["v"]] += 3 if j["gv"] > j["gm"] else (1 if j["gm"] == j["gv"] else 0)
    ordem = sorted(pontos_final, key=lambda c: -pontos_final[c])
    campeao = ordem[0] if len(ordem) == 2 and pontos_final[ordem[0]] > pontos_final[ordem[1]] else None
    if campeao is None and final:
        ult = final[-1]
        pens = (ult["pm"], ult["pv"])
        campeao = ult["m"] if pens[0] is not None and pens[0] > pens[1] else ult["v"] if pens[0] is not None else None
    vice = next((c for c in pontos_final if c != campeao), None)

    saida = []
    for c in sorted(clubes, key=lambda c: c["nome_popular"]):
        idc = c["id_clube"]
        s = stats[idc]
        if s["j"] != por_ind["I01"][idc] or s["gp"] != por_ind["I27"][idc] or s["gc"] != por_ind["I28"][idc]:
            raise SystemExit(f"{c['nome_popular']}: jogos ou gols diferentes do gabarito")
        am, ve = por_ind["I20"][idc], por_ind["I21"][idc]
        escudo = PROC / c["arquivo_escudo"]
        principal, secundaria = COR_MANUAL.get(c["nome_popular"]) or cores_escudo(escudo)
        logo = "data:image/png;base64," + base64.b64encode(escudo.read_bytes()).decode("ascii")
        if idc == campeao:
            fase_alc = "Campeão"
        elif idc == vice:
            fase_alc = "Vice-campeão"
        else:
            fase_alc = FASE_ALCANCADA[alcance[idc]]
        est_casa, jogos_na_casa = casa[idc].most_common(1)[0]
        top = sorted(artilheiros[idc], key=lambda x: (-x[1], x[2]))[:3]
        k = cls[idc]
        if int(k["pontos"]) != int(por_ind["I29"][idc]) or int(k["posicao"]) != int(por_ind["I31"][idc]):
            raise SystemExit(f"{c['nome_popular']}: classificação da 1ª fase diferente do gabarito")
        saida.append({
            "id": idc, "nome": c["nome_popular"], "oficial": c["nome_oficial"], "curto": curto(c["nome_popular"]), "sigla": c["sigla"], "cor": principal, "cor2": secundaria,
            "j1": int(k["jogos"]), "v1": int(k["vitorias"]), "e1": int(k["empates"]), "d1": int(k["derrotas"]), "gp1": int(k["gols_pro"]), "gc1": int(k["gols_contra"]),
            "sg1": int(k["saldo"]), "am1": int(k["amarelos"]), "ve1": int(k["vermelhos"]), "jm": sum(casa[idc].values()), "casan": jogos_na_casa,
            "logo": logo, "pos1": int(por_ind["I31"][idc]), "pts1": int(por_ind["I29"][idc]), "aprov": round(por_ind["I30"][idc], 2),
            "j": s["j"], "v": s["v"], "e": s["e"], "d": s["d"], "gp": s["gp"], "gc": s["gc"], "sg": s["gp"] - s["gc"],
            "am": int(am), "ve": int(ve), "cpj": round((am + ve) / s["j"], 2), "pubm": round(por_ind["I32"][idc]),
            "fase": fase_alc, "art": top, "forma": forma[idc], "casa": estadios[est_casa]["nome_fpf"], "cidade": estadios[est_casa]["municipio"],
        })
    resultados = Counter(r["resultado"] for r in regras)
    meta = {
        "jogos": int(geral["I01"]), "gols": int(geral["I02"]), "publico": int(geral["I10"]), "campeao": campeao,
        "regras": len(regras), "ok": resultados["ok"], "expl": resultados["explicada"], "aber": resultados["aberta"], "info": resultados["info"],
        "ocorr": len(log), "ocorr_abertas": sum(1 for x in log if x["status"] == "aberta"),
    }
    return {"meta": meta, "mot": motivos, "clubes": saida, "jogos": jogos}


def dados_json(dados=None):
    dados = dados or montar_dados()
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def main():
    dados = montar_dados()
    texto = dados_json(dados)
    fragmento = (SAIDA / "fragmento.html").read_text(encoding="utf-8").replace("__DADOS__", texto)
    pagina = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Versus - Paulista Analytics</title>"
        "<style>html,body{margin:0;height:100%;background:#05070a}</style></head><body>"
        + fragmento
        + "</body></html>"
    )
    (SAIDA / "index.html").write_text(pagina, encoding="utf-8", newline="\n")
    sandbox = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Versus no sandbox</title>'
        "<style>html,body{margin:0;height:100%;background:#222}iframe{border:0;width:100%;height:100%}</style></head><body>"
        '<iframe sandbox="allow-scripts" srcdoc="' + html.escape(pagina, quote=True) + '"></iframe></body></html>'
    )
    (SAIDA / "sandbox.html").write_text(sandbox, encoding="utf-8", newline="\n")
    print(f"clubes: {len(dados['clubes'])} | jogos: {len(dados['jogos'])}")
    print(f"dados (JSON): {len(texto):,} caracteres | fragmento com dados: {len(fragmento):,} caracteres")
    for c in dados["clubes"]:
        print(f"{c['curto']:<14} {c['sigla']:<5} {c['cor']} {c['cor2']}  pos {c['pos1']:>2}  {c['fase']:<17} forma {''.join(f[0] for f in c['forma'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
