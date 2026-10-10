import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal

from classificacao import contagem_cartoes, tabela_primeira_fase
from comum import FASE_ESPN, RAIZ, REF, carregar_espn, hora_fpf, hora_local, ler_csv, mapa_clubes, norm, parear, placar_disputa_espn
from correcoes import ler_correcoes
from financeiro import texto_simples

PROC = RAIZ / "data" / "processed"
ESPERADO_POR_RODADA = {**{r: 8 for r in range(1, 9)}, 9: 4, 10: 2, 11: 1, 12: 1}
ORDEM_PERIODO = {"AJ": 0, "1T": 1, "INT": 2, "2T": 3, "PJ": 4}
REGRAS = []


def regra(codigo, titulo, severidade="media", info=False):
    def deco(f):
        REGRAS.append({"codigo": codigo, "titulo": titulo, "severidade": severidade, "info": info, "funcao": f})
        return f

    return deco


class Contexto:
    def __init__(self):
        self.jogos = ler_csv(REF / "fpf_a1_2026_jogos.csv")
        self.class_fpf = ler_csv(REF / "fpf_a1_2026_classificacao.csv")
        self.t = {n: ler_csv(PROC / f"{n}.csv") for n in ("fato_partida", "fato_evento", "dim_clube", "dim_estadio", "fato_estatistica_time", "dim_atleta", "fato_escalacao", "fato_substituicao", "fato_comissao", "fato_ingresso", "fato_despesa", "fato_rateio")}
        self.sp = {int(r["numero_jogo"]): r for r in ler_csv(PROC / "fpf" / "sumula_partida.csv")}
        self.sg = ler_csv(PROC / "fpf" / "sumula_gol.csv")
        self.sc = ler_csv(PROC / "fpf" / "sumula_cartao.csv")
        self.se = ler_csv(PROC / "fpf" / "sumula_escalacao.csv")
        self.ss = ler_csv(PROC / "fpf" / "sumula_substituicao.csv")
        self.bo = {int(r["numero_jogo"]): r for r in ler_csv(PROC / "fpf" / "boletim_partida.csv")}
        self.bi = ler_csv(PROC / "fpf" / "boletim_ingresso.csv")
        self.bd = ler_csv(PROC / "fpf" / "boletim_despesa.csv")
        self.br = ler_csv(PROC / "fpf" / "boletim_rateio.csv")
        self.eventos, self.resumos = carregar_espn()
        self.fpf_nome, self.espn_time, self.mapa, self.sem_par = mapa_clubes(self.jogos, self.eventos)
        self.nome_para_id = {v: k for k, v in self.fpf_nome.items()}
        self.por_numero, self.erros_pareamento = parear(self.jogos, self.eventos, self.mapa)
        self.jogo = {int(j["numero"]): j for j in self.jogos}
        self.id_partida = {n: int(j["id_jogo"]) for n, j in self.jogo.items()}
        self.num_partida = {p["id_partida"]: int(p["numero_jogo"]) for p in self.t["fato_partida"]}
        self.ev_card, self.bx_card = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        self.esp_card_jogo = defaultdict(lambda: [0, 0])
        for n, eid in self.por_numero.items():
            e = self.eventos[eid]
            fase = FASE_ESPN[e["season"]["slug"]]
            comp = e["competitions"][0]
            ids = {x["team"]["id"] for x in comp["competitors"]}
            for d in comp.get("details", []):
                tid = d.get("team", {}).get("id")
                if tid in ids:
                    a, v = (1 if d.get("yellowCard") else 0), (1 if d.get("redCard") else 0)
                    self.ev_card[(fase, self.mapa[tid])][0] += a
                    self.ev_card[(fase, self.mapa[tid])][1] += v
                    self.esp_card_jogo[(n, self.mapa[tid])][0] += a
                    self.esp_card_jogo[(n, self.mapa[tid])][1] += v
            for t in self.resumos[eid].get("boxscore", {}).get("teams", []):
                est = {s["name"]: s.get("displayValue") for s in t.get("statistics", [])}
                self.bx_card[(fase, self.mapa[t["team"]["id"]])][0] += int(est.get("yellowCards") or 0)
                self.bx_card[(fase, self.mapa[t["team"]["id"]])][1] += int(est.get("redCards") or 0)
        self.sm_card_jogo = defaultdict(Counter)
        for c in self.sc:
            self.sm_card_jogo[(int(c["numero_jogo"]), self.nome_para_id[c["equipe"]])][c["cartao"]] += 1

    def oc(self, num=None, clube=None, fa="", va="", fb="", vb="", detalhe=""):
        return {"id_partida": self.id_partida.get(num) if num else None, "numero_jogo": num, "id_clube": clube, "fonte_a": fa, "valor_a": va, "fonte_b": fb, "valor_b": vb, "detalhe": detalhe}

    def nome(self, idc):
        return self.fpf_nome.get(idc, str(idc))


def placar_espn(e):
    comp = e["competitions"][0]["competitors"]
    return int(next(x for x in comp if x["homeAway"] == "home")["score"]), int(next(x for x in comp if x["homeAway"] == "away")["score"])


def gols_espn(e):
    comp = e["competitions"][0]
    casa = next(x for x in comp["competitors"] if x["homeAway"] == "home")["team"]["id"]
    g = [0, 0]
    for d in comp.get("details", []):
        if d.get("scoringPlay") and not d.get("shootout"):
            g[0 if d.get("team", {}).get("id") == casa else 1] += 1
    return tuple(g)


def minutos_gol_espn(e):
    r = []
    for d in e["competitions"][0].get("details", []):
        if d.get("scoringPlay") and not d.get("shootout"):
            m = re.match(r"^(\d+)'(?:\+(\d+)')?", d["clock"]["displayValue"])
            r.append(int(m.group(1)) + int(m.group(2) or 0))
    return sorted(r)


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


@regra("A01", "Quantidade de jogos (ESPN x FPF)", "alta")
def a01(c):
    e, f = len(c.eventos), len(c.jogos)
    return 1, ([c.oc(fa="ESPN", va=e, fb="FPF", vb=f)] if e != f else []), f"ESPN {e} | FPF {f}"


@regra("A02", "Jogos por fase (ESPN x FPF)", "alta")
def a02(c):
    fe = Counter(FASE_ESPN[e["season"]["slug"]] for e in c.eventos.values())
    ff = Counter(j["fase"] for j in c.jogos)
    return len(set(fe) | set(ff)), [c.oc(fa="ESPN", va=fe[f], fb="FPF", vb=ff[f], detalhe=f) for f in sorted(set(fe) | set(ff)) if fe[f] != ff[f]], f"ESPN {dict(fe)} | FPF {dict(ff)}"


@regra("A03", "Cada clube da ESPN casa com um único clube da FPF (nome normalizado)", "alta")
def a03(c):
    return len(c.espn_time), [c.oc(fa="ESPN", va=nome, fb="FPF", vb=f"{n} candidatos") for _, nome, n in c.sem_par], f"{len(c.mapa)} de {len(c.espn_time)} casados"


@regra("A04", "Cada jogo da ESPN casa com um único jogo da FPF (fase, mandante, visitante)", "alta")
def a04(c):
    return len(c.eventos), [c.oc(fa="ESPN", va=x, fb="FPF", vb="sem par único") for x in c.erros_pareamento], f"{len(c.por_numero)} casados"


@regra("A05", "Placar igual jogo a jogo (ESPN x FPF)", "alta")
def a05(c):
    o = []
    for n, eid in c.por_numero.items():
        pe, j = placar_espn(c.eventos[eid]), c.jogo[n]
        pf = (int(j["gols_mandante"]), int(j["gols_visitante"]))
        if pe != pf:
            o.append(c.oc(n, fa="ESPN", va=f"{pe[0]} x {pe[1]}", fb="FPF", vb=f"{pf[0]} x {pf[1]}", detalhe=f"{j['mandante']} x {j['visitante']}"))
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} iguais"


@regra("A06", "Data e horário programados (ESPN em horário de Brasília x FPF)", "baixa")
def a06(c):
    o = []
    for n, eid in c.por_numero.items():
        e, j = c.eventos[eid], c.jogo[n]
        dh = (hora_local(e["date"]) - hora_fpf(j)).total_seconds() / 60
        if dh != 0:
            o.append(c.oc(n, fa="ESPN", va=f"{hora_local(e['date']):%d/%m %H:%M}", fb="FPF", vb=f"{j['data'][:5]} {j['horario']}", detalhe=f"{dh:+.0f} min"))
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} iguais"


@regra("A07", "Cada estádio da ESPN corresponde a um único nome na FPF", "media")
def a07(c):
    est = defaultdict(Counter)
    for n, eid in c.por_numero.items():
        est[(c.eventos[eid]["competitions"][0].get("venue") or {}).get("fullName", "")][c.jogo[n]["estadio"]] += 1
    return len(est), [c.oc(fa="ESPN", va=e, fb="FPF", vb=" | ".join(f)) for e, f in est.items() if len(f) > 1], f"{len(est)} estádios na ESPN"


@regra("A08", "Gols dos eventos da ESPN (sem disputa de pênaltis) somam o placar da própria ESPN", "media")
def a08(c):
    o = []
    for n, eid in c.por_numero.items():
        e = c.eventos[eid]
        if gols_espn(e) != placar_espn(e):
            o.append(c.oc(n, fa="eventos", va="x".join(map(str, gols_espn(e))), fb="placar", vb="x".join(map(str, placar_espn(e)))))
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} jogos coerentes"


@regra("A09", "Público igual no scoreboard e no summary da ESPN", "media")
def a09(c):
    o = []
    for n, eid in c.por_numero.items():
        a, b = c.eventos[eid]["competitions"][0].get("attendance"), c.resumos[eid].get("gameInfo", {}).get("attendance")
        if a != b:
            o.append(c.oc(n, fa="ESPN scoreboard", va=a, fb="ESPN summary", vb=b))
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} iguais"


def pontos_primeira_fase(c, fonte="fpf"):
    pts = defaultdict(lambda: dict(P=0, J=0, V=0, E=0, D=0, GP=0, GC=0))
    for n, j in c.jogo.items():
        if j["fase"] != "PRIMEIRA FASE":
            continue
        gm, gv = (int(j["gols_mandante"]), int(j["gols_visitante"])) if fonte == "fpf" else placar_espn(c.eventos[c.por_numero[n]])
        for cid, gf, gc in ((int(j["id_clube_mandante"]), gm, gv), (int(j["id_clube_visitante"]), gv, gm)):
            r = pts[cid]
            r["J"] += 1
            r["GP"] += gf
            r["GC"] += gc
            if gf > gc:
                r["V"] += 1
                r["P"] += 3
            elif gf == gc:
                r["E"] += 1
                r["P"] += 1
            else:
                r["D"] += 1
    return pts


@regra("A10", "Classificação da 1ª fase recalculada com os placares da ESPN x tabela oficial (P, J, V, E, D, GP, GC, SG)", "alta")
def a10(c):
    pts = pontos_primeira_fase(c, "espn")
    o = []
    for r_ in c.class_fpf:
        if r_["fase"] != "PRIMEIRA FASE":
            continue
        r = pts[int(r_["id_clube"])]
        calc = (r["P"], r["J"], r["V"], r["E"], r["D"], r["GP"], r["GC"], r["GP"] - r["GC"])
        of = tuple(int(r_[x]) for x in ("pontos", "jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra", "saldo"))
        if calc != of:
            o.append(c.oc(clube=int(r_["id_clube"]), fa="ESPN", va=calc, fb="FPF", vb=of, detalhe=r_["clube"]))
    return 16, o, f"{16 - len(o)} de 16 clubes iguais à FPF"


@regra("A11", "Cada clube jogou 8 vezes na 1ª fase", "media")
def a11(c):
    pts = pontos_primeira_fase(c)
    return 16, [c.oc(clube=i, fa="jogos", va=r["J"], fb="esperado", vb=8, detalhe=c.nome(i)) for i, r in pts.items() if r["J"] != 8], f"{len(pts)} clubes; jogos por clube {sorted({r['J'] for r in pts.values()})}"


def comparar_cartoes(c, origem, rotulo):
    fpf = {(r["fase"], int(r["id_clube"])): (int(r["amarelos"]), int(r["vermelhos"])) for r in c.class_fpf}
    o = []
    for (fase, idc), of in sorted(fpf.items()):
        got = tuple(origem[(fase, idc)])
        if got != of:
            o.append(c.oc(clube=idc, fa=rotulo, va=got, fb="FPF", vb=of, detalhe=f"{fase} | {c.nome(idc)}"))
    return len(fpf), o


@regra("A12", "Cartões por clube e fase: eventos da ESPN x tabela da FPF (amarelos, vermelhos)", "media")
def a12(c):
    n, o = comparar_cartoes(c, c.ev_card, "ESPN eventos")
    return n, o, f"{n - len(o)} de {n} combinações iguais"


@regra("A13", "Cartões por clube e fase: resumo da partida (boxscore) da ESPN x tabela da FPF", "baixa")
def a13(c):
    n, o = comparar_cartoes(c, c.bx_card, "ESPN resumo")
    return n, o, f"{n - len(o)} de {n} combinações iguais"


@regra("A14", "Total de cartões da temporada (amarelos, vermelhos)", "baixa", info=True)
def a14(c):
    soma = lambda d: [sum(v[i] for v in d.values()) for i in (0, 1)]
    fpf = {(r["fase"], int(r["id_clube"])): (int(r["amarelos"]), int(r["vermelhos"])) for r in c.class_fpf}
    return 1, [], f"FPF {soma(fpf)} | ESPN eventos {soma(c.ev_card)} | ESPN resumo {soma(c.bx_card)}"


@regra("A15", "Jogo decidido nos pênaltis (status da ESPN), VP/DP da FPF e placar da disputa (ESPN x súmula)", "media")
def a15(c):
    pen = [e for e in c.eventos.values() if e["status"]["type"]["name"] == "STATUS_FINAL_PEN"]
    vp = [r for r in c.class_fpf if r["fase"] == "QUARTAS DE FINAL" and (r["vp"] != "0" or r["dp"] != "0")]
    o = [] if (len(pen) == 1 and len(vp) == 2) else [c.oc(fa="ESPN", va=len(pen), fb="FPF", vb=len(vp), detalhe="jogos nos pênaltis x clubes com VP/DP")]
    espn = {n: placar_disputa_espn(c.eventos[eid]) for n, eid in c.por_numero.items()}
    sumula = {n: ((int(r["penaltis_mandante"]), int(r["penaltis_visitante"])) if r.get("penaltis_mandante") not in (None, "") else None) for n, r in c.sp.items()}
    disputas = sorted(n for n in espn if espn[n] or sumula.get(n))
    for n in disputas:
        if espn[n] != sumula.get(n):
            o.append(c.oc(n, fa="ESPN", va=espn[n], fb="súmula", vb=sumula.get(n), detalhe="placar da disputa de pênaltis"))
    return 1 + len(disputas), o, f"ESPN {len(pen)} jogo | FPF VP/DP em {len(vp)} clubes | disputa ESPN x súmula em {len(disputas)} jogo"


@regra("A16", "Público da ESPN é inteiro e positivo", "media")
def a16(c):
    pub = {n: c.eventos[eid]["competitions"][0].get("attendance") for n, eid in c.por_numero.items()}
    o = [c.oc(n, fa="ESPN", va=p, fb="esperado", vb="inteiro positivo") for n, p in pub.items() if not (isinstance(p, int) and p > 0)]
    v = [p for p in pub.values() if isinstance(p, int)]
    return len(pub), o, f"{len(pub) - len(o)} de {len(pub)} | total {sum(v):,} | média {sum(v) / len(v):,.0f} | min {min(v):,} | max {max(v):,}".replace(",", ".")


@regra("A17", "Árbitro presente no summary da ESPN", "baixa")
def a17(c):
    o, nomes = [], set()
    for n, eid in c.por_numero.items():
        nm = (c.resumos[eid]["gameInfo"].get("officials") or [{}])[0].get("fullName")
        if not nm:
            o.append(c.oc(n, fa="ESPN summary", va="", fb="esperado", vb="nome do árbitro"))
        nomes.add(nm)
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} | {len(nomes)} árbitros distintos"


@regra("A18", "Público: boletim financeiro oficial (ingressos vendidos) x ESPN", "alta")
def a18(c):
    o = []
    for n, eid in c.por_numero.items():
        pe, pb = c.eventos[eid]["competitions"][0].get("attendance"), int(c.bo[n]["publico"])
        if pe != pb:
            o.append(c.oc(n, fa="ESPN", va=pe, fb="boletim FPF", vb=pb, detalhe=f"{pe - pb:+d}" if isinstance(pe, int) else ""))
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} iguais"


@regra("A19", "Ordem da 1ª fase pelo Art. 16 do regulamento x posição oficial", "alta")
def a19(c):
    partidas = [{"id_clube_mandante": int(j["id_clube_mandante"]), "id_clube_visitante": int(j["id_clube_visitante"]), "gols_mandante": j["gols_mandante"], "gols_visitante": j["gols_visitante"]} for j in c.jogos if j["fase"] == "PRIMEIRA FASE"]
    cart = {int(r["id_clube"]): (int(r["amarelos"]), int(r["vermelhos"])) for r in c.class_fpf if r["fase"] == "PRIMEIRA FASE"}
    calc = tabela_primeira_fase(partidas, cart)
    pos = {int(r["id_clube"]): int(r["pos"]) for r in c.class_fpf if r["fase"] == "PRIMEIRA FASE"}
    o = [c.oc(clube=l["id_clube"], fa="Art. 16", va=l["posicao"], fb="FPF", vb=pos[l["id_clube"]], detalhe=c.nome(l["id_clube"])) for l in calc if l["posicao"] != pos[l["id_clube"]]]
    empates = sum(1 for l in calc if l["empate_total"])
    return 16, o, f"{16 - len(o)} de 16 posições iguais | empates que precisaram de cartões: {empates}"


@regra("A20", "Boletim: linhas somam a renda bruta e despesas mais renda líquida igual à renda bruta", "media")
def a20(c):
    o = [c.oc(n, fa="boletim", va=f"receita {b['receita_confere']}", fb="boletim", vb=f"renda {b['renda_confere']}") for n, b in c.bo.items() if b["receita_confere"] != "True" or b["renda_confere"] != "True"]
    return len(c.bo), o, f"receita confere em {sum(1 for b in c.bo.values() if b['receita_confere'] == 'True')} de {len(c.bo)}; renda líquida em {sum(1 for b in c.bo.values() if b['renda_confere'] == 'True')}; público pagante identificado em {sum(1 for b in c.bo.values() if b['publico_pagante'])}"


@regra("A21", "Árbitro: súmula x ESPN (o nome completo de uma fonte contém o da outra)", "baixa")
def a21(c):
    o = []
    for n, eid in c.por_numero.items():
        a = norm(c.sp[n]["arbitro"] or "")
        nome_e = (c.resumos[eid]["gameInfo"].get("officials") or [{}])[0].get("fullName") or ""
        b = norm(nome_e)
        if not (a <= b or b <= a):
            o.append(c.oc(n, fa="súmula", va=c.sp[n]["arbitro"], fb="ESPN", vb=nome_e))
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} iguais"


@regra("A22", "Placar final: súmula x tabela da FPF", "alta")
def a22(c):
    o = []
    for n, j in c.jogo.items():
        a, b = (c.sp[n]["gols_mandante"], c.sp[n]["gols_visitante"]), (j["gols_mandante"], j["gols_visitante"])
        if a != b:
            o.append(c.oc(n, fa="súmula", va=" x ".join(a), fb="FPF", vb=" x ".join(b)))
    return len(c.jogo), o, f"{len(c.jogo) - len(o)} de {len(c.jogo)} iguais"


@regra("A23", "Data e horário programados: súmula x tabela da FPF", "media")
def a23(c):
    o = []
    for n, j in c.jogo.items():
        a, b = (c.sp[n]["data"], c.sp[n]["horario"]), (j["data"], j["horario"].replace("h", ":"))
        if a != b:
            o.append(c.oc(n, fa="súmula", va=" ".join(a), fb="FPF", vb=" ".join(b)))
    return len(c.jogo), o, f"{len(c.jogo) - len(o)} de {len(c.jogo)} iguais"


@regra("A24", "Gols: mesma quantidade e minuto igual com tolerância de 2 minutos (súmula x ESPN)", "media")
def a24(c):
    g_s = defaultdict(list)
    for g in c.sg:
        g_s[int(g["numero_jogo"])].append(int(g["minuto"]) + int(g["acrescimo"]))
    o, dist = [], Counter()
    for n, eid in sorted(c.por_numero.items()):
        a, b = minutos_gol_espn(c.eventos[eid]), sorted(g_s[n])
        if len(a) != len(b):
            o.append(c.oc(n, fa="ESPN", va=a, fb="súmula", vb=b, detalhe="quantidade diferente"))
            continue
        difs = [x - y for x, y in zip(a, b)]
        dist.update(difs)
        if any(abs(x) > 2 for x in difs):
            o.append(c.oc(n, fa="ESPN", va=a, fb="súmula", vb=b, detalhe="minuto com diferença maior que 2"))
    return len(c.por_numero), o, f"{len(c.por_numero) - len(o)} de {len(c.por_numero)} jogos dentro da tolerância; diferença ESPN menos súmula por gol: {dict(sorted(dist.items()))}"


@regra("A25", "Cartões por clube e fase: regra da FPF aplicada à súmula x tabela da FPF", "alta")
def a25(c):
    por_fase = defaultdict(list)
    for r in c.sc:
        por_fase[r["fase"]].append({"equipe_id": c.nome_para_id[r["equipe"]], "cartao": r["cartao"]})
    calc = {(fase, idc): av for fase, regs in por_fase.items() for idc, av in contagem_cartoes(regs).items()}
    fpf = {(r["fase"], int(r["id_clube"])): (int(r["amarelos"]), int(r["vermelhos"])) for r in c.class_fpf}
    o = []
    for k, of in sorted(fpf.items()):
        got = tuple(calc.get(k, (0, 0)))
        if got != of:
            o.append(c.oc(clube=k[1], fa="súmula (regra FPF)", va=got, fb="FPF", vb=of, detalhe=f"{k[0]} | {c.nome(k[1])}"))
    return len(fpf), o, f"{len(fpf) - len(o)} de {len(fpf)} combinações iguais"


@regra("A26", "Cartões por equipe e jogo: ESPN x súmula (contando como a ESPN conta)", "media")
def a26(c):
    o, tot_e, tot_s = [], [0, 0], [0, 0]
    for p in c.t["fato_partida"]:
        n = int(p["numero_jogo"])
        for idc in (int(p["id_clube_mandante"]), int(p["id_clube_visitante"])):
            s_ = c.sm_card_jogo[(n, idc)]
            sm = (s_["amarelo"], s_["vermelho"] + s_["2o_amarelo"])
            es = tuple(c.esp_card_jogo[(n, idc)])
            tot_e[0] += es[0]
            tot_e[1] += es[1]
            tot_s[0] += sm[0]
            tot_s[1] += sm[1]
            if es != sm:
                o.append(c.oc(n, idc, fa="ESPN", va=es, fb="súmula", vb=sm, detalhe=c.nome(idc)))
    return 144, o, f"{144 - len(o)} de 144 equipe-jogos iguais; total ESPN {tuple(tot_e)} súmula {tuple(tot_s)}"


@regra("A27", "Gols contra: mesma quantidade por jogo (súmula x ESPN)", "media")
def a27(c):
    ct_s, ct_e = Counter(), Counter()
    for g in c.sg:
        if g["tipo"] == "CT":
            ct_s[int(g["numero_jogo"])] += 1
    for n, eid in c.por_numero.items():
        ct_e[n] = sum(1 for d in c.eventos[eid]["competitions"][0].get("details", []) if d.get("ownGoal"))
    o = [c.oc(n, fa="súmula", va=ct_s[n], fb="ESPN", vb=ct_e[n]) for n in sorted(set(ct_s) | set(ct_e)) if ct_s[n] != ct_e[n]]
    return len(c.por_numero), o, f"súmula {sum(ct_s.values())} | ESPN {sum(ct_e.values())}"


@regra("A28", "Cada rodada tem o número esperado de jogos e nenhum jogo se repete", "alta")
def a28(c):
    por_rodada = Counter(int(j["rodada"]) for j in c.jogos)
    o = [c.oc(fa="jogos na rodada", va=por_rodada[r], fb="esperado", vb=ESPERADO_POR_RODADA.get(r), detalhe=f"rodada {r}") for r in sorted(set(por_rodada) | set(ESPERADO_POR_RODADA)) if por_rodada[r] != ESPERADO_POR_RODADA.get(r)]
    for chave in ("numero", "id_jogo"):
        rep = [k for k, v in Counter(j[chave] for j in c.jogos).items() if v > 1]
        o += [c.oc(fa=chave, va=k, fb="esperado", vb="único", detalhe="repetido") for k in rep]
    return len(ESPERADO_POR_RODADA) + 2, o, f"{len(por_rodada)} rodadas"


@regra("A29", "Minuto dos eventos plausível (1T até 45, 2T de 45 a 90, acréscimo até 20, total até 120)", "media")
def a29(c):
    o, n = [], 0
    for e in c.t["fato_evento"]:
        if e["minuto"] == "" or e["periodo"] not in ("1T", "2T"):
            continue
        n += 1
        m, a = int(e["minuto"]), int(e["acrescimo"] or 0)
        faixa = (0, 45) if e["periodo"] == "1T" else (45, 90)
        if not (faixa[0] <= m <= faixa[1] and 0 <= a <= 20 and m + a <= 120):
            o.append(c.oc(c.num_partida[e["id_partida"]], int(e["id_clube"]), fa="evento", va=f"{e['periodo']} {m}+{a}", fb="faixa", vb=f"{faixa[0]} a {faixa[1]}, acréscimo até 20", detalhe=f"{e['tipo_evento']} {e['pessoa']}"))
    return n, o, f"{n - len(o)} de {n} eventos com minuto"


@regra("A30", "Todo evento é de um dos dois clubes da partida", "alta")
def a30(c):
    clubes = {p["id_partida"]: (p["id_clube_mandante"], p["id_clube_visitante"], int(p["numero_jogo"])) for p in c.t["fato_partida"]}
    o = []
    for e in c.t["fato_evento"]:
        m, v, n = clubes[e["id_partida"]]
        if e["id_clube"] not in (m, v) or e["id_clube_creditado"] not in (m, v):
            o.append(c.oc(n, int(e["id_clube"]), fa="evento", va=e["id_clube"], fb="partida", vb=f"{m} x {v}", detalhe=e["id_evento"]))
    return len(c.t["fato_evento"]), o, f"{len(c.t['fato_evento']) - len(o)} de {len(c.t['fato_evento'])} eventos"


@regra("A31", "Datas coerentes: boletim com a data e hora do jogo e súmula publicada até 1 dia depois", "baixa")
def a31(c):
    o = []
    for n, j in c.jogo.items():
        d_jogo = datetime.strptime(j["data"], "%d/%m/%Y").date()
        bol, prog = (c.bo[n]["data"], c.bo[n]["horario"]), (j["data"], j["horario"].replace("h", ":"))
        if bol != prog:
            o.append(c.oc(n, fa="boletim", va=" ".join(bol), fb="FPF", vb=" ".join(prog)))
        pub = datetime.strptime(c.sp[n]["publicada_em"], "%d/%m/%Y %H:%M").date()
        if not (0 <= (pub - d_jogo).days <= 1):
            o.append(c.oc(n, fa="súmula publicada", va=c.sp[n]["publicada_em"], fb="jogo", vb=j["data"], detalhe="publicação fora de 0 a 1 dia"))
    return len(c.jogo) * 2, o, f"{len(c.jogo) * 2 - len(o)} de {len(c.jogo) * 2} verificações"


@regra("A32", "Completude dos campos principais", "baixa")
def a32(c):
    verificar = [("fato_partida", x) for x in ("id_arbitro", "id_assistente1", "id_assistente2", "id_quarto_arbitro", "id_var", "inicio_1t", "termino_1t", "inicio_2t", "termino_2t", "publico_boletim", "publico_pagante", "renda_bruta", "publico_espn", "id_estadio")] + [("dim_estadio", "capacidade"), ("dim_clube", "sigla"), ("dim_clube", "cor_hex"), ("dim_clube", "arquivo_escudo"), ("fato_evento", "pessoa")]
    o = []
    for tab, col in verificar:
        falta = sum(1 for l in c.t[tab] if l[col] == "")
        if falta:
            o.append(c.oc(fa=f"{tab}.{col}", va=falta, fb="total", vb=len(c.t[tab]), detalhe="campos vazios"))
    return len(verificar), o, f"{len(verificar) - len(o)} de {len(verificar)} colunas completas"


@regra("A33", "Súmula: horários dos tempos plausíveis (1T e 2T de 40 a 80 min; intervalo de 8 a 30 min) e acréscimos não negativos", "media")
def a33(c):
    o = []
    for n, s in c.sp.items():
        i1, t1, i2, t2 = (hhmm(s[k]) for k in ("inicio_1t", "termino_1t", "inicio_2t", "termino_2t"))
        d1, d2, iv = (t1 - i1) % 1440, (t2 - i2) % 1440, (i2 - t1) % 1440
        if not (40 <= d1 <= 80 and 40 <= d2 <= 80 and 8 <= iv <= 30) or int(s["acrescimo_1t_min"]) < 0 or int(s["acrescimo_2t_min"]) < 0:
            o.append(c.oc(n, fa="súmula", va=f"1T {s['inicio_1t']}-{s['termino_1t']}; 2T {s['inicio_2t']}-{s['termino_2t']}", fb="esperado", vb="durações plausíveis", detalhe=f"1T {d1} min, intervalo {iv} min, 2T {d2} min"))
    return len(c.sp), o, f"{len(c.sp) - len(o)} de {len(c.sp)} súmulas"


@regra("A34", "Cada correção documentada (correcoes_dados.csv) está aplicada em fato_evento e o valor original ainda consta na súmula", "alta")
def a34(c):
    correcoes = ler_correcoes()
    o = []
    for k in correcoes:
        n, campo = int(k["numero_jogo"]), k["campo"]
        aplicados = [e for e in c.t["fato_evento"] if e["id_correcao"] == k["id_correcao"]]
        if len(aplicados) != 1 or aplicados[0][campo] != k["valor_corrigido"] or c.num_partida[aplicados[0]["id_partida"]] != n:
            o.append(c.oc(n, fa="fato_evento", va=[e[campo] for e in aplicados], fb="correção", vb=k["valor_corrigido"], detalhe=f"{k['id_correcao']} não está aplicada"))
            continue
        gol = k["tipo_evento"].startswith("gol")
        if not any(int(r["numero_jogo"]) == n and k["pessoa"] in r["jogador" if gol else "pessoa"] and r[campo] == k["valor_original"] for r in (c.sg if gol else c.sc)):
            o.append(c.oc(n, fa="súmula", va="valor original ausente", fb="correção", vb=k["valor_original"], detalhe=f"{k['id_correcao']}: a súmula não traz mais o valor original"))
    return len(correcoes), o, f"{len(correcoes) - len(o)} de {len(correcoes)} correções aplicadas e rastreáveis"


def chave_tempo(periodo, minuto, acrescimo):
    return (ORDEM_PERIODO[periodo], int(minuto) if minuto not in ("", None) else -1, int(acrescimo) if acrescimo not in ("", None) else 0)


def times_do_jogo(c):
    return [(p["id_partida"], p[lado]) for p in c.t["fato_partida"] for lado in ("id_clube_mandante", "id_clube_visitante")]


def em_campo(r, tempo):
    if r["jogou"] != "1":
        return False
    entrada = chave_tempo(r["periodo_entrada"], r["minuto_entrada"], r["acrescimo_entrada"])
    saida = chave_tempo(r["periodo_saida"], r["minuto_saida"], r["acrescimo_saida"]) if r["periodo_saida"] else None
    return entrada <= tempo and (saida is None or tempo <= saida)


def nome_confere(a, b):
    a, b = a.strip().lower(), b.strip().lower()
    return a.startswith(b) or b.startswith(a)


@regra("A35", "Relação de jogadores: 11 titulares por equipe e jogo, registro sem repetição no time e nenhum atleta repetido no jogo", "alta")
def a35(c):
    titulares = Counter((e["id_partida"], e["id_clube"]) for e in c.t["fato_escalacao"] if e["situacao"] == "titular")
    o = []
    for idp, idc in times_do_jogo(c):
        if titulares[(idp, idc)] != 11:
            o.append(c.oc(c.num_partida[idp], int(idc), fa="relação de jogadores", va=titulares[(idp, idc)], fb="esperado", vb=11, detalhe=f"titulares de {c.nome(int(idc))}"))
    for (idp, idc, reg), n in sorted(Counter((e["id_partida"], e["id_clube"], e["registro"]) for e in c.t["fato_escalacao"]).items()):
        if n > 1:
            o.append(c.oc(c.num_partida[idp], int(idc), fa="relação de jogadores", va=f"registro {reg} {n} vezes", fb="esperado", vb="uma vez", detalhe=c.nome(int(idc))))
    for (idp, ida), n in sorted(Counter((e["id_partida"], e["id_atleta"]) for e in c.t["fato_escalacao"]).items()):
        if n > 1:
            o.append(c.oc(c.num_partida[idp], fa="relação de jogadores", va=f"{ida} {n} vezes", fb="esperado", vb="uma vez", detalhe="atleta repetido no jogo"))
    return len(times_do_jogo(c)), o, f"{len(times_do_jogo(c)) - len(o)} de {len(times_do_jogo(c))} equipe-jogos; {len(c.t['fato_escalacao'])} atletas relacionados"


@regra("A36", "Substituições: quem saiu e quem entrou constam na relação do mesmo time (camisa e nome), quem entra é reserva e ninguém sai ou entra duas vezes", "alta")
def a36(c):
    lin = {(int(r["numero_jogo"]), r["equipe"], int(r["numero"])): r for r in c.se}
    o, saiu, entrou = [], set(), set()
    for s in c.ss:
        n, eq = int(s["numero_jogo"]), s["equipe"]
        idc = c.nome_para_id[eq]
        for papel, num, nome, vistos in (("saiu", int(s["numero_saiu"]), s["nome_saiu"], saiu), ("entrou", int(s["numero_entrou"]), s["nome_entrou"], entrou)):
            r = lin.get((n, eq, num))
            alvo = f"{eq} nº {num} {nome}"
            if r is None:
                o.append(c.oc(n, idc, fa="substituição", va=alvo, fb="relação de jogadores", vb="camisa ausente", detalhe=papel))
                continue
            if not nome_confere(r["nome"], nome.removesuffix("...")):
                o.append(c.oc(n, idc, fa="substituição", va=alvo, fb="relação de jogadores", vb=r["nome"], detalhe=f"{papel}: nome diferente"))
            if papel == "entrou" and r["situacao"] != "R":
                o.append(c.oc(n, idc, fa="substituição", va=alvo, fb="relação de jogadores", vb="titular", detalhe="entrou quem já era titular"))
            if (n, eq, num) in vistos:
                o.append(c.oc(n, idc, fa="substituição", va=alvo, fb="esperado", vb="uma vez", detalhe=f"{papel} duas vezes"))
            vistos.add((n, eq, num))
    return len(c.ss), o, f"{len(c.ss) - len(o)} de {len(c.ss)} substituições coerentes com a relação"


@regra("A37", "Substituições por equipe e jogo: até 5 regulares e até 1 na lista de concussão", "baixa")
def a37(c):
    cont = Counter((int(s["numero_jogo"]), s["equipe"], s["bloco"]) for s in c.ss)
    limite = {"regular": 5, "concussao": 1}
    o = [c.oc(n, c.nome_para_id[eq], fa=f"substituições {bloco}", va=v, fb="limite", vb=limite[bloco], detalhe=eq) for (n, eq, bloco), v in sorted(cont.items()) if v > limite[bloco]]
    maximo = max((v for (_, _, b), v in cont.items() if b == "regular"), default=0)
    return 144, o, f"{144 - len(o)} de 144 equipe-jogos; máximo de regulares {maximo}; com concussão: {sum(1 for (_, _, b) in cont if b == 'concussao')} equipe-jogos"


@regra("A38", "Gols: o autor consta na relação do time (camisa e nome) e estava em campo no minuto do gol", "alta")
def a38(c):
    esc = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e for e in c.t["fato_escalacao"]}
    nome = {a["id_atleta"]: a["nome"] for a in c.t["dim_atleta"]}
    gols = [e for e in c.t["fato_evento"] if e["tipo_evento"].startswith("gol")]
    o = []
    for e in gols:
        n, idc = c.num_partida[e["id_partida"]], int(e["id_clube"])
        r = esc.get((e["id_partida"], e["id_clube"], e["numero_camisa"]))
        alvo = f"{e['pessoa']} nº {e['numero_camisa']}"
        if r is None:
            o.append(c.oc(n, idc, fa="gol", va=alvo, fb="relação de jogadores", vb="camisa ausente", detalhe=e["id_evento"]))
        elif not nome_confere(nome[r["id_atleta"]], e["pessoa"]):
            o.append(c.oc(n, idc, fa="gol", va=alvo, fb="relação de jogadores", vb=nome[r["id_atleta"]], detalhe=f"{e['id_evento']}: nome diferente"))
        elif not em_campo(r, chave_tempo(e["periodo"], e["minuto"], e["acrescimo"])):
            o.append(c.oc(n, idc, fa="gol", va=f"{alvo} em {e['periodo']} {e['minuto']}+{e['acrescimo'] or 0}", fb="relação de jogadores", vb="atleta fora de campo", detalhe=e["id_evento"]))
    return len(gols), o, f"{len(gols) - len(o)} de {len(gols)} gols de atleta relacionado e em campo"


@regra("A39", "Cartões de atletas: o atleta consta na relação do time (camisa e nome)", "media")
def a39(c):
    esc = {(e["id_partida"], e["id_clube"], e["numero_camisa"]): e for e in c.t["fato_escalacao"]}
    nome = {a["id_atleta"]: a["nome"] for a in c.t["dim_atleta"]}
    cartoes = [e for e in c.t["fato_evento"] if e["funcao"] == "Atleta" and e["tipo_evento"] in ("amarelo", "segundo_amarelo", "vermelho")]
    o, banco = [], 0
    for e in cartoes:
        n, idc = c.num_partida[e["id_partida"]], int(e["id_clube"])
        r = esc.get((e["id_partida"], e["id_clube"], e["numero_camisa"]))
        alvo = f"{e['pessoa']} nº {e['numero_camisa']}"
        if r is None:
            o.append(c.oc(n, idc, fa="cartão", va=alvo, fb="relação de jogadores", vb="camisa ausente", detalhe=e["id_evento"]))
        elif not nome_confere(nome[r["id_atleta"]], e["pessoa"]):
            o.append(c.oc(n, idc, fa="cartão", va=alvo, fb="relação de jogadores", vb=nome[r["id_atleta"]], detalhe=f"{e['id_evento']}: nome diferente"))
        elif e["periodo"] in ("1T", "2T") and e["minuto"] != "" and not em_campo(r, chave_tempo(e["periodo"], e["minuto"], e["acrescimo"])):
            banco += 1
    return len(cartoes), o, f"{len(cartoes) - len(o)} de {len(cartoes)} cartões de atleta relacionado; {banco} recebidos no banco (reserva que não entrou ou atleta já substituído)"


@regra("A40", "Comissão técnica: um técnico com nome por equipe e jogo", "media")
def a40(c):
    tecnicos = Counter((e["id_partida"], e["id_clube"]) for e in c.t["fato_comissao"] if e["funcao"] == "Técnico")
    o = []
    for idp, idc in times_do_jogo(c):
        if tecnicos[(idp, idc)] != 1:
            o.append(c.oc(c.num_partida[idp], int(idc), fa="súmula", va="técnico sem nome" if tecnicos[(idp, idc)] == 0 else f"{tecnicos[(idp, idc)]} técnicos", fb="esperado", vb="1 técnico", detalhe=c.nome(int(idc))))
    nomes = {(e["id_clube"], e["nome"]) for e in c.t["fato_comissao"] if e["funcao"] == "Técnico"}
    return 144, o, f"{144 - len(o)} de 144 equipe-jogos; {len(nomes)} técnicos distintos em {len({idc for idc, _ in nomes})} clubes"


@regra("A41", "Atletas: cada registro da FPF tem um só nome e um só clube, e cada nome joga por um só clube", "media")
def a41(c):
    por_registro, por_nome = defaultdict(set), defaultdict(set)
    for r in c.se:
        por_registro[r["registro"]].add((r["nome"], r["equipe"]))
        por_nome[r["nome"]].add((r["registro"], r["equipe"]))
    o = []
    for reg, v in sorted(por_registro.items()):
        if len({x[0] for x in v}) > 1 or len({x[1] for x in v}) > 1:
            o.append(c.oc(fa="registro", va=reg, fb="esperado", vb="um nome e um clube", detalhe=" | ".join(f"{n} ({e})" for n, e in sorted(v))))
    for nome, v in sorted(por_nome.items()):
        if len({x[1] for x in v}) > 1:
            o.append(c.oc(fa="nome", va=nome, fb="esperado", vb="um clube", detalhe=" | ".join(f"{e} ({r})" for r, e in sorted(v)), ))
    dois = sum(1 for v in por_nome.values() if len({x[0] for x in v}) > 1)
    return len(por_registro), o, f"{len(por_registro)} registros e {len(por_nome)} atletas; {dois} atletas com dois registros no mesmo clube"


def por_jogo(linhas):
    d = defaultdict(list)
    for l in linhas:
        d[int(l["numero_jogo"])].append(l)
    return d


def soma_dec(linhas, campo):
    return sum((Decimal(l[campo]) for l in linhas), Decimal(0))


def milhar(n):
    return f"{n:,}".replace(",", ".")


def reais(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def jogos_com_ocorrencia(o):
    return len({x["numero_jogo"] for x in o if x["numero_jogo"]})


@regra("A42", "Boletim, ingressos: as linhas somam o público e a renda bruta, preço vezes quantidade dá a arrecadação de cada linha e o público pagante confere", "alta")
def a42(c):
    linhas = por_jogo(c.bi)
    proc_q, proc_r = Counter(), defaultdict(Decimal)
    for i in c.t["fato_ingresso"]:
        proc_q[int(i["id_partida"])] += int(i["ingressos"])
        proc_r[int(i["id_partida"])] += Decimal(i["arrecadacao"])
    o, pagantes, total = [], 0, 0
    for n, b in sorted(c.bo.items()):
        ls = linhas.get(n, [])
        vend = sum(int(l["vendidos"]) for l in ls)
        pag = sum(int(l["vendidos"]) for l in ls if Decimal(l["arrecadacao"]) > 0)
        total, pagantes = total + vend, pagantes + pag
        conferir = [("público (vendidos)", vend, int(b["publico"])), ("renda bruta", soma_dec(ls, "arrecadacao"), Decimal(b["renda_bruta"])),
                    ("ingressos à venda", sum(int(l["a_venda"]) for l in ls), int(b["ingressos_a_venda"])), ("ingressos devolvidos", sum(int(l["devolvidos"]) for l in ls), int(b["ingressos_devolvidos"])),
                    ("público na tabela fato_ingresso", proc_q[c.id_partida[n]], int(b["publico"])), ("renda bruta na tabela fato_ingresso", proc_r[c.id_partida[n]], Decimal(b["renda_bruta"]))]
        if b["publico_pagante"]:
            conferir.append(("público pagante", pag, int(b["publico_pagante"])))
        for rotulo, achado, esperado in conferir:
            if achado != esperado:
                o.append(c.oc(n, fa="linhas do boletim", va=achado, fb="TOTAIS do boletim", vb=esperado, detalhe=rotulo))
        for l in ls:
            if Decimal(l["preco"]) * int(l["vendidos"]) != Decimal(l["arrecadacao"]) or int(l["a_venda"]) != int(l["vendidos"]) + int(l["devolvidos"]):
                o.append(c.oc(n, fa="linha do boletim", va=f"{l['vendidos']} x R$ {l['preco']} = R$ {l['arrecadacao']}", fb="preço x vendidos", vb=f"R$ {Decimal(l['preco']) * int(l['vendidos'])}", detalhe=l["localidade"]))
    return len(c.bo), o, f"{len(c.bo) - jogos_com_ocorrencia(o)} de {len(c.bo)} jogos; {len(c.bi)} linhas de ingresso somam {milhar(total)} ingressos ({milhar(pagantes)} pagantes, {milhar(total - pagantes)} gratuitos)"


@regra("A43", "Boletim, despesas: as linhas de cada bloco (B1, B2, B3) somam o subtotal, os blocos somam o total das despesas e renda líquida é renda bruta menos despesas", "alta")
def a43(c):
    linhas = por_jogo(c.bd)
    proc = defaultdict(Decimal)
    for d in c.t["fato_despesa"]:
        proc[int(d["id_partida"])] += Decimal(d["valor"])
    o, retido, jogos_retido = [], Decimal(0), 0
    for n, b in sorted(c.bo.items()):
        ls = linhas.get(n, [])
        if b["despesas_total"] == "" or b["renda_liquida"] == "":
            o.append(c.oc(n, fa="leitura por conta (boletim)", va="sem total", fb="linhas do boletim", vb=soma_dec(ls, "valor"), detalhe="total das despesas ou renda líquida não identificado"))
            continue
        conferir = [(f"subtotal {k}", soma_dec([l for l in ls if l["bloco"] == k], "valor"), Decimal(b[f"total_{k.lower()}"])) for k in ("B1", "B2", "B3")]
        conferir += [("total das despesas", soma_dec(ls, "valor"), Decimal(b["despesas_total"])), ("renda líquida", Decimal(b["renda_bruta"]) - soma_dec(ls, "valor"), Decimal(b["renda_liquida"])), ("despesas na tabela fato_despesa", proc[c.id_partida[n]], Decimal(b["despesas_total"]))]
        for rotulo, achado, esperado in conferir:
            if achado != esperado:
                o.append(c.oc(n, fa="linhas do boletim", va=achado, fb="total do boletim", vb=esperado, detalhe=rotulo))
        ret = Decimal(b["retencao_inss_informada"])
        retido += ret
        jogos_retido += 1 if ret else 0
    rubricas = {l["rubrica"] for l in c.bd}
    return len(c.bo), o, f"{len(c.bo) - jogos_com_ocorrencia(o)} de {len(c.bo)} jogos; {len(c.bd)} linhas em {len(rubricas)} rubricas; retenções de INSS informadas depois do total (fora da conta): {reais(retido)} em {jogos_retido} jogos"


@regra("A44", "Boletim, divisão da renda líquida: os dois clubes na ordem do jogo, percentuais somam 100%, valores somam a renda líquida e líquido a receber é valor menos deduções", "media")
def a44(c):
    linhas = por_jogo(c.br)
    proc = defaultdict(list)
    for r in c.t["fato_rateio"]:
        proc[int(r["id_partida"])].append(r)
    o, cem, outras, negativa = [], 0, 0, 0
    for n, b in sorted(c.bo.items()):
        ls = linhas.get(n, [])
        nomes = b["jogo"].split(" x ")
        if [l["clube"] for l in ls] != nomes:
            o.append(c.oc(n, fa="divisão da renda", va=" | ".join(l["clube"] for l in ls), fb="jogo do boletim", vb=" | ".join(nomes), detalhe="clubes ou ordem diferentes"))
        if soma_dec(ls, "percentual") != 100:
            o.append(c.oc(n, fa="percentuais", va=soma_dec(ls, "percentual"), fb="esperado", vb=100, detalhe="percentuais da divisão"))
        if b["renda_liquida"] != "" and soma_dec(ls, "valor") != Decimal(b["renda_liquida"]):
            o.append(c.oc(n, fa="valores da divisão", va=soma_dec(ls, "valor"), fb="renda líquida", vb=b["renda_liquida"], detalhe="soma dos valores"))
        for l in ls:
            esperado = Decimal(l["valor"]) - Decimal(l["deducao_inss"]) - Decimal(l["deducao_outras"])
            if Decimal(l["liquido"]) != esperado:
                o.append(c.oc(n, fa="líquido a receber", va=l["liquido"], fb="valor menos deduções", vb=esperado, detalhe=l["clube"]))
        if sorted(r["lado"] for r in proc[c.id_partida[n]]) != ["mandante", "visitante"]:
            o.append(c.oc(n, fa="tabela fato_rateio", va=len(proc[c.id_partida[n]]), fb="esperado", vb="1 mandante e 1 visitante", detalhe="linhas da divisão no ETL"))
        cem += 1 if ls and Decimal(ls[0]["percentual"]) == 100 else 0
        outras += 1 if any(Decimal(l["deducao_outras"]) for l in ls) else 0
        negativa += 1 if b["renda_liquida"] != "" and Decimal(b["renda_liquida"]) < 0 else 0
    return len(c.bo), o, f"{len(c.bo) - jogos_com_ocorrencia(o)} de {len(c.bo)} jogos; mandante com 100% em {cem}; deduções outras em {outras}; renda líquida negativa em {negativa}"


@regra("A45", "Classificação do financeiro: toda rubrica de despesa tem grupo em despesa_grupos.csv, ingressos em Outros não passam de 1% e gratuidade (preço zero) traz uma lei no rótulo", "media")
def a45(c):
    o, sem_grupo = [], defaultdict(list)
    for d in c.t["fato_despesa"]:
        if d["grupo"] == "Sem grupo":
            sem_grupo[d["rubrica"]].append(Decimal(d["valor"]))
    for rubrica, valores in sorted(sem_grupo.items()):
        o.append(c.oc(fa="boletim", va=rubrica, fb="despesa_grupos.csv", vb="sem grupo", detalhe=f"{len(valores)} linhas, {reais(sum(valores))}"))
    total = sum(int(i["ingressos"]) for i in c.t["fato_ingresso"])
    por_categoria, rotulos_outros = Counter(), Counter()
    for i in c.t["fato_ingresso"]:
        por_categoria[i["categoria"]] += int(i["ingressos"])
        if i["categoria"] == "Outros":
            rotulos_outros[i["localidade"]] += int(i["ingressos"])
        if Decimal(i["preco"]) == 0 and "lei" not in texto_simples(i["localidade"]):
            o.append(c.oc(c.num_partida[int(i["id_partida"])], fa="linha de preço zero", va=i["localidade"], fb="esperado", vb="lei no rótulo (gratuidade por lei)", detalhe=f"{i['ingressos']} ingressos"))
    if total and por_categoria["Outros"] / total > 0.01:
        o.append(c.oc(fa="ingressos", va=f"{100 * por_categoria['Outros'] / total:.1f}% em Outros", fb="limite", vb="1%", detalhe="; ".join(f"{k} ({v})" for k, v in rotulos_outros.most_common(5))))
    pcts = " | ".join(f"{k} {100 * v / total:.1f}%" for k, v in sorted(por_categoria.items(), key=lambda kv: -kv[1])) if total else ""
    return len(c.t["fato_ingresso"]) + len(c.t["fato_despesa"]), o, f"{len({d['rubrica'] for d in c.t['fato_despesa']})} rubricas em {len({d['grupo'] for d in c.t['fato_despesa']})} grupos; ingressos: {pcts}"
