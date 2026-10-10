import csv
import hashlib
import html
import io
import json
import re
import sys
import base64
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classificacao import contagem_cartoes, tabela_primeira_fase
from comum import RAIZ, REF, URL_ESCUDO, carregar_espn, ler_csv, mapa_clubes, norm, pareamento, placar_disputa_espn, slug
from correcoes import aplicar_correcoes, ler_correcoes
from financeiro import COLUNAS_DESPESA, COLUNAS_INGRESSO, COLUNAS_RATEIO, ler_grupos_despesa, ler_regras_ingresso, montar_financeiro
from nomes import TAMANHO_NOME_SUMULA, completar_nome, desambiguar, nome_curto

PROC = RAIZ / "data" / "processed"
FPF = PROC / "fpf"
RAW_ESCUDOS = RAIZ / "data" / "raw" / "escudos"
VERSAO = "0.7.0"
COMPETICAO = {"id_competicao": "PAULISTA-A1-2026", "id_campeonato_fpf": 73, "id_categoria_fpf": 39, "exercicio": 2026, "nome": "Paulistão Casas Bahia", "serie": "A1", "categoria": "Profissional"}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
ORDEM_PERIODO = {"AJ": 0, "1T": 1, "INT": 2, "2T": 3, "PJ": 4, "PEN": 5}
TIPO_GOL = {"NR": "gol", "PN": "gol_penalti", "CT": "gol_contra", "FT": "gol_falta"}
TIPO_CARTAO = {"amarelo": "amarelo", "2o_amarelo": "segundo_amarelo", "vermelho": "vermelho"}
SITUACAO = {"T": "titular", "R": "reserva"}
VINCULO = {"P": "profissional", "A": "amador"}
COLUNAS_ATLETA = ["id_atleta", "nome", "nome_truncado", "apelido", "nome_curto", "id_clube", "registros"]
COLUNAS_ESCALACAO = ["id_escalacao", "id_partida", "id_clube", "id_atleta", "numero_camisa", "situacao", "vinculo", "registro", "jogou", "periodo_entrada", "minuto_entrada", "acrescimo_entrada", "periodo_saida", "minuto_saida", "acrescimo_saida", "minutos_jogados", "gols", "gols_contra", "amarelos", "vermelhos"]
COLUNAS_SUBSTITUICAO = ["id_substituicao", "id_partida", "id_clube", "ordem", "tipo", "id_atleta_saiu", "id_atleta_entrou", "numero_saiu", "numero_entrou", "periodo", "minuto", "acrescimo", "minuto_total", "motivo"]
COLUNAS_COMISSAO = ["id_comissao", "id_partida", "id_clube", "funcao", "nome", "nome_truncado"]
ESTATISTICAS = {"possessionPct": "posse_pct", "totalShots": "finalizacoes", "shotsOnTarget": "finalizacoes_no_alvo", "blockedShots": "finalizacoes_bloqueadas", "foulsCommitted": "faltas", "wonCorners": "escanteios", "offsides": "impedimentos", "totalPasses": "passes", "accuratePasses": "passes_certos", "totalCrosses": "cruzamentos", "accurateCrosses": "cruzamentos_certos", "totalTackles": "desarmes", "effectiveTackles": "desarmes_certos", "interceptions": "interceptacoes", "totalClearance": "cortes", "saves": "defesas_goleiro"}
TABELAS = {}


def gravar(nome, linhas, colunas):
    PROC.mkdir(parents=True, exist_ok=True)
    with open(PROC / f"{nome}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(colunas)
        for l in linhas:
            w.writerow(["" if l.get(c) is None else l.get(c) for c in colunas])
    TABELAS[nome] = (linhas, colunas)


def inteiro(v):
    return int(v) if str(v).strip() != "" else None


def luminancia(hexa):
    r, g, b = (int(hexa[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def processar_escudo(src, dst):
    im = Image.open(src).convert("RGBA")
    im.thumbnail((128, 128), Image.LANCZOS)
    q = im.quantize(colors=96, method=Image.FASTOCTREE)
    dst.parent.mkdir(parents=True, exist_ok=True)
    q.save(dst, "PNG", optimize=True)
    return q.size[0], q.size[1], dst.stat().st_size


def folha_de_escudos(clubes):
    cards = []
    for c in sorted(clubes, key=lambda x: x["nome_popular"]):
        orig = RAW_ESCUDOS / f"{c['id_clube']}.png"
        red = PROC / c["arquivo_escudo"]
        b64 = lambda p: base64.b64encode(p.read_bytes()).decode("ascii")
        cards.append(f'<div class="c"><div class="im"><img src="data:image/png;base64,{b64(orig)}" alt=""><img src="data:image/png;base64,{b64(red)}" alt=""></div><b>{html.escape(c["nome_popular"])}</b><span>{html.escape(c["nome_oficial"])}</span><span>id {c["id_clube"]} · sigla {html.escape(c["sigla"])} · cor #{c["cor_hex"]}</span><span>oficial {orig.stat().st_size:,} bytes · reduzido {c["escudo_largura"]}×{c["escudo_altura"]} px, {c["escudo_bytes"]:,} bytes</span></div>'.replace(",", "."))
    pagina = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Conferir escudos</title><style>body{font-family:Segoe UI,Arial,sans-serif;background:#12161d;color:#e9edf2;margin:0;padding:24px}h1{font-size:20px;margin:0 0 4px}p{color:#93a0b1;margin:0 0 18px}.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}.c{background:#1a2029;border:1px solid #283140;border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:4px}.im{display:flex;gap:12px;align-items:center;background:#e9edf2;border-radius:10px;padding:10px;justify-content:center;margin-bottom:6px}.im img{max-width:100px;max-height:100px}.c b{font-size:15px}.c span{font-size:12px;color:#93a0b1}</style></head><body><h1>Conferência dos 16 escudos oficiais da FPF</h1><p>Em cada cartão: à esquerda o arquivo oficial, à direita a cópia reduzida que o dashboard usará. Confira se cada escudo é do clube certo e se a cópia reduzida não perdeu qualidade.</p><div class="g">' + "".join(cards) + "</div></body></html>")
    (PROC / "escudos" / "conferir_escudos.html").write_text(pagina, encoding="utf-8", newline="\n")


def minuto_base(periodo, minuto):
    if minuto is None:
        return 45 if periodo == "INT" else 0
    return minuto


def montar_elenco(esc_raw, sub_raw, com_raw, evs, nome_para_id, id_partida):
    base = {}
    for r in esc_raw:
        n, idc, num = int(r["numero_jogo"]), nome_para_id[r["equipe"]], int(r["numero"])
        k = (id_partida[n], idc, num)
        if k in base:
            raise ValueError(f"camisa repetida na relação do jogo {n}: {r['equipe']} nº {num}")
        base[k] = {"lado": 0 if r["lado"] == "mandante" else 1, "nome": r["nome"], "situacao": SITUACAO[r["situacao"]], "vinculo": VINCULO[r["vinculo"]], "registro": r["registro"], "id_atleta": slug(r["nome"]), "original": len(base)}

    entrada, saida, subs = {}, {}, []
    for original, r in enumerate(sub_raw):
        n, idc = int(r["numero_jogo"]), nome_para_id[r["equipe"]]
        ns, ne = int(r["numero_saiu"]), int(r["numero_entrou"])
        ks, ke = (id_partida[n], idc, ns), (id_partida[n], idc, ne)
        dado = {"periodo": r["periodo"], "minuto": inteiro(r["minuto"]), "acrescimo": inteiro(r["acrescimo"]) or 0}
        if ks in saida or ke in entrada:
            raise ValueError(f"atleta sai ou entra duas vezes no jogo {n}: {r['equipe']} {ns} -> {ne}")
        saida[ks], entrada[ke] = dado, dado
        subs.append({"id_partida": id_partida[n], "id_clube": idc, "tipo": r["bloco"], "ks": ks, "ke": ke, "numero_saiu": ns, "numero_entrou": ne, **dado, "motivo": r["motivo"] or None, "original": original})
    subs.sort(key=lambda s: (s["id_partida"], s["id_clube"], ORDEM_PERIODO[s["periodo"]], s["minuto"] if s["minuto"] is not None else 0, s["acrescimo"], s["original"]))
    seq = Counter()
    substituicoes = []
    for s in subs:
        seq[(s["id_partida"], s["id_clube"])] += 1
        ordem = seq[(s["id_partida"], s["id_clube"])]
        substituicoes.append({"id_substituicao": f'{s["id_partida"]}-{s["id_clube"]}-{ordem:02d}', "id_partida": s["id_partida"], "id_clube": s["id_clube"], "ordem": ordem, "tipo": s["tipo"], "id_atleta_saiu": base[s["ks"]]["id_atleta"] if s["ks"] in base else None, "id_atleta_entrou": base[s["ke"]]["id_atleta"] if s["ke"] in base else None, "numero_saiu": s["numero_saiu"], "numero_entrou": s["numero_entrou"], "periodo": s["periodo"], "minuto": s["minuto"], "acrescimo": s["acrescimo"], "minuto_total": s["minuto"] + s["acrescimo"] if s["minuto"] is not None else None, "motivo": s["motivo"]})

    por_atleta, expulsao = defaultdict(Counter), {}
    for e in evs:
        if e["funcao"] == "Atleta" and e["numero_camisa"] is not None:
            k = (e["id_partida"], e["id_clube"], e["numero_camisa"])
            por_atleta[k][e["tipo_evento"]] += 1
            if e["tipo_evento"] in ("vermelho", "segundo_amarelo") and (e["minuto"] is not None or e["periodo"] == "INT"):
                expulsao[k] = min(expulsao.get(k, 90), minuto_base(e["periodo"], e["minuto"]))

    escalacao = []
    for k, b in sorted(base.items(), key=lambda kv: (kv[0][0], kv[1]["lado"], kv[1]["situacao"] != "titular", kv[0][2])):
        c = por_atleta.get(k, Counter())
        if b["situacao"] == "titular":
            ent = {"periodo": "1T", "minuto": 0, "acrescimo": 0}
        else:
            ent = entrada.get(k)
        sai = saida.get(k)
        jogou = ent is not None
        ini = minuto_base(ent["periodo"], ent["minuto"]) if jogou else 0
        fim = min(minuto_base(sai["periodo"], sai["minuto"]) if sai else 90, expulsao.get(k, 90))
        escalacao.append({"id_escalacao": f"{k[0]}-{k[1]}-{k[2]}", "id_partida": k[0], "id_clube": k[1], "id_atleta": b["id_atleta"], "numero_camisa": k[2], "situacao": b["situacao"], "vinculo": b["vinculo"], "registro": b["registro"], "jogou": 1 if jogou else 0,
                           "periodo_entrada": ent["periodo"] if jogou else None, "minuto_entrada": ent["minuto"] if jogou else None, "acrescimo_entrada": ent["acrescimo"] if jogou else None,
                           "periodo_saida": sai["periodo"] if sai else None, "minuto_saida": sai["minuto"] if sai else None, "acrescimo_saida": sai["acrescimo"] if sai else None,
                           "minutos_jogados": max(0, fim - ini) if jogou else 0,
                           "gols": c["gol"] + c["gol_penalti"] + c["gol_falta"], "gols_contra": c["gol_contra"], "amarelos": c["amarelo"] - c["segundo_amarelo"], "vermelhos": c["vermelho"] + c["segundo_amarelo"]})

    apelidos, pessoas = defaultdict(Counter), defaultdict(Counter)
    for e in evs:
        if e["funcao"] == "Atleta" and e["numero_camisa"] is not None:
            b = base.get((e["id_partida"], e["id_clube"], e["numero_camisa"]))
            if b:
                if e.get("pessoa"):
                    pessoas[b["id_atleta"]][e["pessoa"]] += 1
                if e["apelido"]:
                    apelidos[b["id_atleta"]][e["apelido"]] += 1
    ficha = defaultdict(lambda: {"nome": None, "registros": set(), "clubes": Counter()})
    for k, b in base.items():
        f = ficha[b["id_atleta"]]
        f["nome"] = b["nome"]
        f["registros"].add(b["registro"])
        f["clubes"][k[1]] += 1
    atletas = []
    for ida in sorted(ficha):
        f = ficha[ida]
        nome = f["nome"]
        truncado = len(nome) >= TAMANHO_NOME_SUMULA
        completo, cortado = nome, truncado
        nome_inteiro = completar_nome(nome, pessoas[ida])
        if nome_inteiro:
            completo, cortado = nome_inteiro, False
        apelido = sorted(apelidos[ida].items(), key=lambda x: (-x[1], x[0]))[0][0] if apelidos[ida] else None
        atletas.append({"id_atleta": ida, "nome": nome, "nome_truncado": 1 if truncado else 0, "apelido": apelido, "nome_curto": nome_curto(completo, apelido, cortado), "id_clube": sorted(f["clubes"].items(), key=lambda x: (-x[1], x[0]))[0][0], "registros": "; ".join(sorted(f["registros"])), "_nome": completo, "_truncado": cortado})
    desambiguar(atletas)

    comissao, seq = [], Counter()
    for r in com_raw:
        if not r["nome"]:
            continue
        n, idc = int(r["numero_jogo"]), nome_para_id[r["equipe"]]
        seq[(n, idc)] += 1
        comissao.append({"id_comissao": f"{id_partida[n]}-{idc}-{seq[(n, idc)]:02d}", "id_partida": id_partida[n], "id_clube": idc, "funcao": r["funcao"], "nome": r["nome"], "nome_truncado": inteiro(r["nome_truncado"])})
    return atletas, escalacao, substituicoes, comissao


def principal():
    jogos = ler_csv(REF / "fpf_a1_2026_jogos.csv")
    class_fpf = ler_csv(REF / "fpf_a1_2026_classificacao.csv")
    fases_ref = ler_csv(REF / "fpf_a1_2026_fases.csv")
    oficiais = {int(c["id_clube"]): c["nome_oficial"] for c in class_fpf}
    sp = {int(r["numero_jogo"]): r for r in ler_csv(FPF / "sumula_partida.csv")}
    sg = ler_csv(FPF / "sumula_gol.csv")
    sc = ler_csv(FPF / "sumula_cartao.csv")
    bo = {int(r["numero_jogo"]): r for r in ler_csv(FPF / "boletim_partida.csv")}
    eventos, resumos = carregar_espn()
    fpf_nome, espn_time, mapa, sem_par = mapa_clubes(jogos, eventos)
    assert not sem_par, f"clubes da ESPN sem par: {sem_par}"
    por_numero = pareamento(jogos, eventos, mapa)
    nome_para_id = {v: k for k, v in fpf_nome.items()}
    espn_do_clube = {v: k for k, v in mapa.items()}
    jogo_por_num = {int(j["numero"]): j for j in jogos}
    id_comp = COMPETICAO["id_competicao"]
    fase_id = {f["nome_fase"]: int(f["id_fase"]) for f in fases_ref}

    datas = [datetime.strptime(j["data"], "%d/%m/%Y").date() for j in jogos]
    atualizado = max(c["atualizado"] for c in class_fpf)
    gravar("dim_competicao", [{**COMPETICAO, "data_inicio": min(datas).isoformat(), "data_fim": max(datas).isoformat(), "total_jogos": len(jogos), "atualizado_fpf_em": atualizado}], ["id_competicao", "id_campeonato_fpf", "id_categoria_fpf", "exercicio", "nome", "serie", "categoria", "data_inicio", "data_fim", "total_jogos", "atualizado_fpf_em"])

    jogos_fase = Counter(j["fase"] for j in jogos)
    gravar("dim_fase", [{"id_fase": int(f["id_fase"]), "id_competicao": id_comp, "nome_fase": f["nome_fase"], "ordem": int(f["ordem"]), "tipo": "pontos_corridos" if int(f["ordem"]) == 1 else "mata_mata", "jogos": jogos_fase[f["nome_fase"]]} for f in fases_ref], ["id_fase", "id_competicao", "nome_fase", "ordem", "tipo", "jogos"])

    clubes = []
    for idc in sorted(fpf_nome, key=lambda i: fpf_nome[i]):
        t = espn_time[espn_do_clube[idc]]
        cor, alt = (t.get("color") or "666666").upper(), (t.get("alternateColor") or "").upper()
        cor_hex = alt if (luminancia(cor) < 40 and alt) else cor
        larg, alt_px, tam = processar_escudo(RAW_ESCUDOS / f"{idc}.png", PROC / "escudos" / f"{idc}.png")
        clubes.append({"id_clube": idc, "nome_popular": fpf_nome[idc], "nome_oficial": oficiais[idc], "sigla": t["abbreviation"], "cor_hex": cor_hex, "cor_espn": cor, "cor_alternativa_espn": alt, "id_espn": t["id"], "url_escudo": URL_ESCUDO.format(id=idc), "arquivo_escudo": f"escudos/{idc}.png", "escudo_largura": larg, "escudo_altura": alt_px, "escudo_bytes": tam, "tem_escudo": 1})
    gravar("dim_clube", clubes, ["id_clube", "nome_popular", "nome_oficial", "sigla", "cor_hex", "cor_espn", "cor_alternativa_espn", "id_espn", "url_escudo", "arquivo_escudo", "escudo_largura", "escudo_altura", "escudo_bytes", "tem_escudo"])
    folha_de_escudos(clubes)

    wiki = {"Botafogo": 42, "Capivariano": 58, "Corinthians": 78, "Guarani": 242, "Mirassol": 3293, "Noroeste": 3303, "Novorizontino": 9541, "Palmeiras": 3320, "Ponte Preta": 3344, "Portuguesa": 3347, "Primavera": 15915, "Red Bull Bragantino": 45, "Santos": 3383, "São Bernardo": 3388, "São Paulo": 3395, "Velo Clube": 3448}
    aliases, vistos = [], set()

    def alias(texto, idc, fonte):
        k = (texto.strip().lower(), idc)
        if texto.strip() and k not in vistos:
            vistos.add(k)
            aliases.append({"alias": texto.strip(), "alias_normalizado": " ".join(sorted(norm(texto))), "id_clube": idc, "fonte": fonte})

    for c in clubes:
        alias(c["nome_popular"], c["id_clube"], "FPF")
        alias(c["nome_oficial"], c["id_clube"], "FPF")
        alias(espn_time[espn_do_clube[c["id_clube"]]]["displayName"], c["id_clube"], "ESPN")
        alias(c["sigla"], c["id_clube"], "ESPN")
    for n, idc in wiki.items():
        alias(n, idc, "Wikipédia")
    gravar("dim_clube_alias", aliases, ["alias", "alias_normalizado", "id_clube", "fonte"])

    est_espn = defaultdict(set)
    for n, eid in por_numero.items():
        est_espn[jogo_por_num[n]["estadio"]].add((eventos[eid]["competitions"][0].get("venue") or {}).get("fullName", ""))
    assert all(len(v) == 1 for v in est_espn.values()), f"estádio da FPF com mais de um nome na ESPN: {est_espn}"
    mun = {j["estadio"]: j["municipio"] for j in jogos}
    conta_est = Counter(j["estadio"] for j in jogos)
    estadios = [{"id_estadio": slug(n), "nome_fpf": n, "nome_espn": next(iter(est_espn[n])), "municipio": mun[n], "capacidade": None, "fonte_capacidade": None, "jogos": conta_est[n]} for n in sorted(mun)]
    gravar("dim_estadio", estadios, ["id_estadio", "nome_fpf", "nome_espn", "municipio", "capacidade", "fonte_capacidade", "jogos"])
    id_estadio = {e["nome_fpf"]: e["id_estadio"] for e in estadios}

    papeis = {"arbitro": "jogos_arbitro", "assistente1": "jogos_assistente", "assistente2": "jogos_assistente", "quarto_arbitro": "jogos_quarto_arbitro", "var": "jogos_var", "avar1": "jogos_var", "avar2": "jogos_var"}
    pessoas = {}
    for s in sp.values():
        for campo, col in papeis.items():
            nome = (s[campo] or "").strip()
            if nome:
                p = pessoas.setdefault(slug(nome), {"id_arbitro": slug(nome), "nome": nome, "jogos_arbitro": 0, "jogos_assistente": 0, "jogos_quarto_arbitro": 0, "jogos_var": 0})
                p[col] += 1
    gravar("dim_arbitro", [pessoas[k] for k in sorted(pessoas)], ["id_arbitro", "nome", "jogos_arbitro", "jogos_assistente", "jogos_quarto_arbitro", "jogos_var"])

    dias_de_jogo = set(datas)
    cal = []
    d = date(COMPETICAO["exercicio"], 1, 1)
    while d <= date(COMPETICAO["exercicio"], 12, 31):
        cal.append({"data": d.isoformat(), "ano": d.year, "mes": d.month, "nome_mes": MESES[d.month - 1], "dia": d.day, "dia_semana": d.isoweekday(), "nome_dia_semana": DIAS[d.weekday()], "semana_iso": d.isocalendar()[1], "trimestre": (d.month - 1) // 3 + 1, "dia_de_jogo": 1 if d in dias_de_jogo else 0})
        d += timedelta(days=1)
    gravar("dim_calendario", cal, ["data", "ano", "mes", "nome_mes", "dia", "dia_semana", "nome_dia_semana", "semana_iso", "trimestre", "dia_de_jogo"])

    partidas, penaltis = [], {}
    for n in sorted(jogo_por_num):
        j, s, b, e = jogo_por_num[n], sp[n], bo[n], eventos[por_numero[n]]
        comp = e["competitions"][0]
        disputa = placar_disputa_espn(e)
        if disputa:
            penaltis[n] = disputa
        pen_sumula = (inteiro(s["penaltis_mandante"]), inteiro(s["penaltis_visitante"])) if s.get("penaltis_mandante") not in (None, "") else (None, None)
        hora = j["horario"].lower().replace("h", ":")
        dh = datetime.strptime(f'{j["data"]} {hora}', "%d/%m/%Y %H:%M")
        partidas.append({"id_partida": int(j["id_jogo"]), "numero_jogo": n, "id_competicao": id_comp, "id_fase": fase_id[j["fase"]], "rodada": int(j["rodada"]), "grupo": j["grupo"], "data_jogo": dh.date().isoformat(), "hora_programada": dh.strftime("%H:%M"), "data_hora_programada": dh.isoformat(timespec="minutes"), "id_clube_mandante": int(j["id_clube_mandante"]), "id_clube_visitante": int(j["id_clube_visitante"]), "gols_mandante": int(j["gols_mandante"]), "gols_visitante": int(j["gols_visitante"]), "penaltis_mandante": pen_sumula[0], "penaltis_visitante": pen_sumula[1], "id_estadio": id_estadio[j["estadio"]], "publico_boletim": int(b["publico"]), "publico_pagante": int(b["publico_pagante"]), "renda_bruta": b["renda_bruta"], "despesas_total": b["despesas_total"], "renda_liquida": b["renda_liquida"], "publico_espn": comp.get("attendance"), "id_arbitro": slug(s["arbitro"]), "id_assistente1": slug(s["assistente1"] or "") or None, "id_assistente2": slug(s["assistente2"] or "") or None, "id_quarto_arbitro": slug(s["quarto_arbitro"] or "") or None, "id_var": slug(s["var"] or "") or None, "id_avar1": slug(s["avar1"] or "") or None, "id_avar2": slug(s["avar2"] or "") or None, "inicio_1t": s["inicio_1t"], "termino_1t": s["termino_1t"], "atraso_1t_min": s["atraso_1t_min"], "acrescimo_1t_min": s["acrescimo_1t_min"], "inicio_2t": s["inicio_2t"], "termino_2t": s["termino_2t"], "atraso_2t_min": s["atraso_2t_min"], "acrescimo_2t_min": s["acrescimo_2t_min"], "publicada_em": s["publicada_em"], "id_evento_espn": por_numero[n]})
    gravar("fato_partida", partidas, ["id_partida", "numero_jogo", "id_competicao", "id_fase", "rodada", "grupo", "data_jogo", "hora_programada", "data_hora_programada", "id_clube_mandante", "id_clube_visitante", "gols_mandante", "gols_visitante", "penaltis_mandante", "penaltis_visitante", "id_estadio", "publico_boletim", "publico_pagante", "renda_bruta", "despesas_total", "renda_liquida", "publico_espn", "id_arbitro", "id_assistente1", "id_assistente2", "id_quarto_arbitro", "id_var", "id_avar1", "id_avar2", "inicio_1t", "termino_1t", "atraso_1t_min", "acrescimo_1t_min", "inicio_2t", "termino_2t", "atraso_2t_min", "acrescimo_2t_min", "publicada_em", "id_evento_espn"])
    id_partida = {p["numero_jogo"]: p["id_partida"] for p in partidas}

    brutos = []
    for g in sg:
        n = int(g["numero_jogo"])
        j = jogo_por_num[n]
        quem = nome_para_id[g["equipe"]]
        outro = int(j["id_clube_visitante"]) if quem == int(j["id_clube_mandante"]) else int(j["id_clube_mandante"])
        m = re.match(r"^(?P<nome>.+?) - \((?P<apelido>.+)\)$", g["jogador"])
        brutos.append((n, {"id_clube": quem, "id_clube_creditado": outro if g["tipo"] == "CT" else quem, "tipo_evento": TIPO_GOL[g["tipo"]], "funcao": "Atleta", "numero_camisa": inteiro(g["numero"]), "pessoa": m.group("nome") if m else g["jogador"], "apelido": m.group("apelido") if m else None, "minuto": inteiro(g["minuto"]), "acrescimo": inteiro(g["acrescimo"]), "periodo": g["periodo"], "motivo": None, "fonte": "SUMULA"}))
    for c in sc:
        n = int(c["numero_jogo"])
        quem = nome_para_id[c["equipe"]]
        brutos.append((n, {"id_clube": quem, "id_clube_creditado": quem, "tipo_evento": TIPO_CARTAO[c["cartao"]], "funcao": c["funcao"], "numero_camisa": inteiro(c["numero"]), "pessoa": c["pessoa"], "apelido": None, "minuto": inteiro(c["minuto"]), "acrescimo": inteiro(c["acrescimo"]), "periodo": c["periodo"], "motivo": c["motivo"] or None, "fonte": "SUMULA"}))
    for n in penaltis:
        comp = eventos[por_numero[n]]["competitions"][0]
        for dt in sorted((d for d in comp["details"] if d.get("shootout") and d.get("scoringPlay")), key=lambda d: d["clock"]["value"]):
            quem = mapa[dt["team"]["id"]]
            mi = re.match(r"^(\d+)", dt["clock"]["displayValue"])
            brutos.append((n, {"id_clube": quem, "id_clube_creditado": quem, "tipo_evento": "penalti_disputa", "funcao": "Atleta", "numero_camisa": None, "pessoa": (dt.get("athletesInvolved") or [{}])[0].get("displayName"), "apelido": None, "minuto": int(mi.group(1)) if mi else None, "acrescimo": 0, "periodo": "PEN", "motivo": None, "fonte": "ESPN"}))
    aplicar_correcoes(brutos, ler_correcoes())
    brutos.sort(key=lambda x: (x[0], ORDEM_PERIODO[x[1]["periodo"]], (x[1]["minuto"] if x[1]["minuto"] is not None else -1) + (x[1]["acrescimo"] or 0), x[1]["tipo_evento"]))
    seq, evs = Counter(), []
    for n, ev in brutos:
        seq[n] += 1
        ev["id_evento"] = f"{id_partida[n]}-{seq[n]:02d}"
        ev["id_partida"] = id_partida[n]
        ev["minuto_total"] = ev["minuto"] + (ev["acrescimo"] or 0) if ev["minuto"] is not None else None
        evs.append(ev)
    gravar("fato_evento", evs, ["id_evento", "id_partida", "id_clube", "id_clube_creditado", "tipo_evento", "funcao", "numero_camisa", "pessoa", "apelido", "minuto", "acrescimo", "minuto_total", "periodo", "motivo", "fonte", "id_correcao"])

    atletas, escalacao, substituicoes, comissao = montar_elenco(ler_csv(FPF / "sumula_escalacao.csv"), ler_csv(FPF / "sumula_substituicao.csv"), ler_csv(FPF / "sumula_comissao.csv"), evs, nome_para_id, id_partida)
    gravar("dim_atleta", atletas, COLUNAS_ATLETA)
    gravar("fato_escalacao", escalacao, COLUNAS_ESCALACAO)
    gravar("fato_substituicao", substituicoes, COLUNAS_SUBSTITUICAO)
    gravar("fato_comissao", comissao, COLUNAS_COMISSAO)

    jogos_bol = {n: {"id_partida": id_partida[n], "id_mandante": int(jogo_por_num[n]["id_clube_mandante"]), "id_visitante": int(jogo_por_num[n]["id_clube_visitante"]), "jogo": bo[n]["jogo"]} for n in id_partida}
    ingressos, despesas, rateio = montar_financeiro(ler_csv(FPF / "boletim_ingresso.csv"), ler_csv(FPF / "boletim_despesa.csv"), ler_csv(FPF / "boletim_rateio.csv"), jogos_bol, ler_regras_ingresso(), ler_grupos_despesa())
    gravar("fato_ingresso", ingressos, COLUNAS_INGRESSO)
    gravar("fato_despesa", despesas, COLUNAS_DESPESA)
    gravar("fato_rateio", rateio, COLUNAS_RATEIO)

    est = []
    for n, eid in sorted(por_numero.items()):
        for t in resumos[eid]["boxscore"]["teams"]:
            valores = {s["name"]: s.get("displayValue") for s in t["statistics"]}
            linha = {"id_partida": id_partida[n], "id_clube": mapa[t["team"]["id"]]}
            for k, col in ESTATISTICAS.items():
                v = valores.get(k)
                linha[col] = float(v) if col == "posse_pct" and v not in (None, "") else (int(float(v)) if v not in (None, "") else None)
            est.append(linha)
    gravar("fato_estatistica_time", est, ["id_partida", "id_clube"] + list(ESTATISTICAS.values()))

    gravar("fato_classificacao_oficial", [{"id_fase": fase_id[c["fase"]], "fase": c["fase"], "grupo": c["grupo"], "posicao": int(c["pos"]), "id_clube": int(c["id_clube"]), "pontos": int(c["pontos"]), "jogos": int(c["jogos"]), "vitorias": int(c["vitorias"]), "empates": int(c["empates"]), "derrotas": int(c["derrotas"]), "gols_pro": int(c["gols_pro"]), "gols_contra": int(c["gols_contra"]), "saldo": int(c["saldo"]), "vp": int(c["vp"]), "dp": int(c["dp"]), "amarelos": int(c["amarelos"]), "vermelhos": int(c["vermelhos"]), "atualizado_em": c["atualizado"]} for c in class_fpf], ["id_fase", "fase", "grupo", "posicao", "id_clube", "pontos", "jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra", "saldo", "vp", "dp", "amarelos", "vermelhos", "atualizado_em"])

    primeira = [p for p in partidas if p["id_fase"] == fase_id["PRIMEIRA FASE"]]
    cart1 = contagem_cartoes([{"equipe_id": nome_para_id[c["equipe"]], "cartao": c["cartao"]} for c in sc if c["fase"] == "PRIMEIRA FASE"])
    ref = tabela_primeira_fase(primeira, cart1)
    gravar("ref_classificacao_primeira_fase", [{**l, "empate_total": 1 if l["empate_total"] else 0} for l in ref], ["posicao", "id_clube", "jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra", "saldo", "pontos", "aproveitamento", "amarelos", "vermelhos", "empate_total"])

    manifestos = json.loads((RAIZ / "data" / "raw" / "espn" / "bra.camp.paulista" / "2026" / "manifest.json").read_text(encoding="utf-8"))
    coleta_espn = max(v["baixado_em"] for v in manifestos.values() if "baixado_em" in v)
    manifestos_pdf = json.loads((RAIZ / "data" / "raw" / "fpf_pdf" / "2026" / "manifest.json").read_text(encoding="utf-8"))
    coleta_pdf = max(v["baixado_em"] for v in manifestos_pdf.values() if "baixado_em" in v)
    hash_ref = {a.name: hashlib.sha256(a.read_bytes()).hexdigest()[:16] for a in sorted([*REF.glob("fpf_a1_2026_*.csv"), *REF.glob("correcoes_dados.csv"), *REF.glob("ingresso_categorias.csv"), *REF.glob("despesa_grupos.csv")])}
    config = [("versao_pipeline", VERSAO), ("temporada", COMPETICAO["exercicio"]), ("competicao", COMPETICAO["id_competicao"]), ("gerado_em", datetime.now(timezone.utc).isoformat(timespec="seconds")), ("fpf_atualizado_em", atualizado), ("coleta_espn_em", coleta_espn), ("coleta_pdf_em", coleta_pdf)] + [(f"hash_{k}", v) for k, v in hash_ref.items()]
    gravar("aux_config", [{"chave": k, "valor": v} for k, v in config], ["chave", "valor"])

    verificar(partidas, clubes, estadios, evs, est, ref, class_fpf, fase_id, nome_para_id, sc)
    manifesto = {nome: {"linhas": len(l), "colunas": len(c), "sha256": hashlib.sha256((PROC / f"{nome}.csv").read_bytes()).hexdigest()} for nome, (l, c) in TABELAS.items()}
    (PROC / "manifesto.json").write_text(json.dumps({"versao": VERSAO, "gerado_em": config[3][1], "tabelas": manifesto}, ensure_ascii=False, indent=1), encoding="utf-8")
    for nome, (l, c) in TABELAS.items():
        print(f"{nome:34s} {len(l):5d} linhas  {len(c):3d} colunas")
    print(f"escudos: {len(clubes)} em {PROC / 'escudos'} (conferência visual: escudos/conferir_escudos.html)")
    print("integridade: OK")


def verificar(partidas, clubes, estadios, evs, est, ref, class_fpf, fase_id, nome_para_id, sc):
    erros = []

    def ok(cond, msg):
        if not cond:
            erros.append(msg)

    for nome, (linhas, _) in TABELAS.items():
        chave = {"dim_competicao": "id_competicao", "dim_fase": "id_fase", "dim_clube": "id_clube", "dim_estadio": "id_estadio", "dim_arbitro": "id_arbitro", "dim_calendario": "data", "fato_partida": "id_partida", "fato_evento": "id_evento", "dim_atleta": "id_atleta", "fato_escalacao": "id_escalacao", "fato_substituicao": "id_substituicao", "fato_comissao": "id_comissao", "fato_ingresso": "id_ingresso", "fato_despesa": "id_despesa", "fato_rateio": "id_rateio"}.get(nome)
        if chave:
            ok(len({l[chave] for l in linhas}) == len(linhas), f"{nome}: chave {chave} repetida")
    ids_clube = {c["id_clube"] for c in clubes}
    ids_est = {e["id_estadio"] for e in estadios}
    ids_arb = {a["id_arbitro"] for a in TABELAS["dim_arbitro"][0]}
    ids_part = {p["id_partida"] for p in partidas}
    ids_fase = set(fase_id.values())
    for p in partidas:
        ok(p["id_clube_mandante"] in ids_clube and p["id_clube_visitante"] in ids_clube, f"clube inexistente na partida {p['id_partida']}")
        ok(p["id_estadio"] in ids_est and p["id_arbitro"] in ids_arb and p["id_fase"] in ids_fase, f"FK inválida na partida {p['id_partida']}")
        ok((p["penaltis_mandante"] is None) == (p["penaltis_visitante"] is None), f"pênaltis só de um lado na partida {p['id_partida']}")
        if p["penaltis_mandante"] is not None:
            ok(p["gols_mandante"] == p["gols_visitante"] and p["penaltis_mandante"] != p["penaltis_visitante"], f"disputa de pênaltis sem empate no tempo normal ou sem vencedor na partida {p['id_partida']}")
    for e in evs:
        ok(e["id_partida"] in ids_part and e["id_clube"] in ids_clube and e["id_clube_creditado"] in ids_clube, f"FK inválida no evento {e['id_evento']}")
    for e in est:
        ok(e["id_partida"] in ids_part and e["id_clube"] in ids_clube, "FK inválida em estatística")
    ids_atl = {a["id_atleta"] for a in TABELAS["dim_atleta"][0]}
    for a in TABELAS["dim_atleta"][0]:
        ok(a["id_clube"] in ids_clube, f"clube inexistente no atleta {a['id_atleta']}")
    for e in TABELAS["fato_escalacao"][0]:
        ok(e["id_partida"] in ids_part and e["id_clube"] in ids_clube and e["id_atleta"] in ids_atl, f"FK inválida na escalação {e['id_escalacao']}")
    for s in TABELAS["fato_substituicao"][0]:
        ok(s["id_partida"] in ids_part and s["id_clube"] in ids_clube, f"FK inválida na substituição {s['id_substituicao']}")
        ok(all(a is None or a in ids_atl for a in (s["id_atleta_saiu"], s["id_atleta_entrou"])), f"atleta inexistente na substituição {s['id_substituicao']}")
    for c in TABELAS["fato_comissao"][0]:
        ok(c["id_partida"] in ids_part and c["id_clube"] in ids_clube, f"FK inválida na comissão {c['id_comissao']}")
    soma_ing, soma_arr, soma_desp = Counter(), defaultdict(Decimal), defaultdict(Decimal)
    for i in TABELAS["fato_ingresso"][0]:
        ok(i["id_partida"] in ids_part, f"FK inválida no ingresso {i['id_ingresso']}")
        soma_ing[i["id_partida"]] += i["ingressos"]
        soma_arr[i["id_partida"]] += Decimal(i["arrecadacao"])
    for d in TABELAS["fato_despesa"][0]:
        ok(d["id_partida"] in ids_part, f"FK inválida na despesa {d['id_despesa']}")
        soma_desp[d["id_partida"]] += Decimal(d["valor"])
    for r in TABELAS["fato_rateio"][0]:
        ok(r["id_partida"] in ids_part and r["id_clube"] in ids_clube, f"FK inválida na divisão da renda {r['id_rateio']}")
    for p in partidas:
        ok(soma_ing[p["id_partida"]] == p["publico_boletim"], f"ingressos != público na partida {p['id_partida']}")
        ok(soma_arr[p["id_partida"]] == Decimal(p["renda_bruta"]), f"arrecadação != renda bruta na partida {p['id_partida']}")
        ok(soma_desp[p["id_partida"]] == Decimal(p["despesas_total"]), f"despesas != total das despesas na partida {p['id_partida']}")
    ok(len(partidas) == 72 and len(clubes) == 16 and len(estadios) == 16 and len(TABELAS["dim_fase"][0]) == 4, "contagens esperadas (72 jogos, 16 clubes, 16 estádios, 4 fases)")
    ok(len(est) == 144, f"estatísticas: esperado 144 linhas, veio {len(est)}")
    ok(all(v is not None for l in est for k, v in l.items() if k != "id_partida"), "estatística de time com valor ausente")
    gols_evt = Counter()
    for e in evs:
        if e["tipo_evento"].startswith("gol"):
            gols_evt[(e["id_partida"], e["id_clube_creditado"])] += 1
    for p in partidas:
        ok(gols_evt[(p["id_partida"], p["id_clube_mandante"])] == p["gols_mandante"] and gols_evt[(p["id_partida"], p["id_clube_visitante"])] == p["gols_visitante"], f"gols dos eventos != placar na partida {p['id_partida']}")
    ok(sum(p["gols_mandante"] + p["gols_visitante"] for p in partidas) == 168, "total de gols diferente de 168")
    ok(sum(p["publico_boletim"] for p in partidas) == sum(p["publico_espn"] for p in partidas) == 784369, "público total diferente de 784.369")
    pos_ofic = {int(c["id_clube"]): int(c["pos"]) for c in class_fpf if c["fase"] == "PRIMEIRA FASE"}
    for l in ref:
        o = next(c for c in class_fpf if c["fase"] == "PRIMEIRA FASE" and int(c["id_clube"]) == l["id_clube"])
        ok(pos_ofic[l["id_clube"]] == l["posicao"], f"posição calculada != oficial: {l['id_clube']}")
        ok((l["pontos"], l["jogos"], l["vitorias"], l["empates"], l["derrotas"], l["gols_pro"], l["gols_contra"], l["saldo"], l["amarelos"], l["vermelhos"]) == tuple(int(o[k]) for k in ("pontos", "jogos", "vitorias", "empates", "derrotas", "gols_pro", "gols_contra", "saldo", "amarelos", "vermelhos")), f"linha calculada != oficial: {l['id_clube']}")
    por_fase = defaultdict(list)
    for c in sc:
        por_fase[c["fase"]].append({"equipe_id": nome_para_id[c["equipe"]], "cartao": c["cartao"]})
    for fase, regs in por_fase.items():
        for clube, (a, v) in contagem_cartoes(regs).items():
            o = next((c for c in class_fpf if c["fase"] == fase and int(c["id_clube"]) == clube), None)
            ok(o is not None and (a, v) == (int(o["amarelos"]), int(o["vermelhos"])), f"cartões != FPF: {fase} {clube}")
    if erros:
        raise SystemExit("INTEGRIDADE FALHOU:\n  " + "\n  ".join(erros[:30]))


if __name__ == "__main__":
    principal()
