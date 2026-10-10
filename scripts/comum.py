import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REF = RAIZ / "data" / "referencia"
STOP = {"saf", "fc", "sp", "ae", "ec", "gremio", "futebol", "clube", "s", "a", "f"}
URL_ESCUDO = "https://api.fpf.org.br/filiacao/v1/entidades/CLUBE/{id}/escudo"
FASE_ESPN = {"league-phase": "PRIMEIRA FASE", "quarterfinals": "QUARTAS DE FINAL", "semifinals": "SEMIFINAL", "finals": "FINAL"}


def norm(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return frozenset(t for t in re.split(r"[^a-z0-9]+", s) if t and t not in STOP)


def slug(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def ler_csv(arq):
    with open(arq, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def pasta_espn(temporada=2026):
    return RAIZ / "data" / "raw" / "espn" / "bra.camp.paulista" / str(temporada)


def carregar_espn(temporada=2026):
    pasta = pasta_espn(temporada)
    eventos = {}
    for arq in sorted((pasta / "scoreboard").glob("*.json")):
        for e in json.loads(arq.read_text(encoding="utf-8")).get("events", []):
            eventos[e["id"]] = e
    resumos = {i.stem: json.loads(i.read_text(encoding="utf-8")) for i in (pasta / "summary").glob("*.json")}
    return eventos, resumos


def clubes_da_fpf(jogos_fpf):
    """{id_clube: nome popular} de todos os clubes que aparecem nos jogos da FPF."""
    fpf = {}
    for j in jogos_fpf:
        fpf[int(j["id_clube_mandante"])] = j["mandante"]
        fpf[int(j["id_clube_visitante"])] = j["visitante"]
    return fpf


def mapa_clubes(jogos_fpf, eventos):
    fpf = clubes_da_fpf(jogos_fpf)
    espn = {}
    for e in eventos.values():
        for c in e["competitions"][0]["competitors"]:
            espn[c["team"]["id"]] = c["team"]
    mapa, sem_par = {}, []
    por_norm = defaultdict(list)
    for i, n in fpf.items():
        por_norm[norm(n)].append(i)
    for tid, t in espn.items():
        achados = por_norm.get(norm(t["displayName"]), [])
        if len(achados) == 1:
            mapa[tid] = achados[0]
        else:
            sem_par.append((tid, t["displayName"], len(achados)))
    return fpf, espn, mapa, sem_par


def parear(jogos_fpf, eventos, mapa):
    """Liga cada jogo da ESPN ao jogo da FPF pela chave (fase, mandante, visitante).

    Retorna ({numero_jogo: id_evento}, [descrições dos jogos sem par único]).
    """
    chave_fpf = {(j["fase"], int(j["id_clube_mandante"]), int(j["id_clube_visitante"])): int(j["numero"]) for j in jogos_fpf}
    por_numero, erros = {}, []
    for eid, e in eventos.items():
        comp = e["competitions"][0]["competitors"]
        m = next(x for x in comp if x["homeAway"] == "home")["team"]["id"]
        v = next(x for x in comp if x["homeAway"] == "away")["team"]["id"]
        k = (FASE_ESPN[e["season"]["slug"]], mapa.get(m), mapa.get(v))
        if k not in chave_fpf or chave_fpf[k] in por_numero:
            erros.append(f"{eid} {e['name']}")
        else:
            por_numero[chave_fpf[k]] = eid
    return por_numero, erros


def pareamento(jogos_fpf, eventos, mapa):
    por_numero, erros = parear(jogos_fpf, eventos, mapa)
    if erros:
        raise ValueError("jogos da ESPN sem par único na FPF: " + "; ".join(erros))
    return por_numero


def hora_local(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%MZ") - timedelta(hours=3)


def hora_fpf(j):
    h = j["horario"].lower().replace("h", ":")
    return datetime.strptime(f'{j["data"]} {h}', "%d/%m/%Y %H:%M")

def placar_disputa_espn(evento):
    """Cobranças convertidas da disputa de pênaltis de um jogo da ESPN: (mandante, visitante), ou None se não houve disputa.
    Só serve para conferir a súmula (a fonte oficial do placar da disputa) e para listar as cobranças."""
    comp = evento["competitions"][0]
    casa = next(x for x in comp["competitors"] if x["homeAway"] == "home")["team"]["id"]
    pm = pv = 0
    for dt in comp.get("details", []):
        if dt.get("shootout") and dt.get("scoringPlay"):
            if dt["team"]["id"] == casa:
                pm += 1
            else:
                pv += 1
    return (pm, pv) if (pm or pv) else None
