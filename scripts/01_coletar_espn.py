import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LIGA = "bra.camp.paulista"
BASE = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LIGA}/"
CABECALHO = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}
PAUSA = 0.4
TENTATIVAS = 3

TEMPORADAS = {
    2026: (date(2026, 1, 10), date(2026, 3, 8)),
}


def baixar(url):
    ultimo = None
    for t in range(1, TENTATIVAS + 1):
        try:
            req = urllib.request.Request(url, headers=CABECALHO)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            ultimo = e
            time.sleep(PAUSA * t * 2)
    raise RuntimeError(f"falhou {url}: {ultimo}")


def salvar_se_preciso(arq, url, manifesto, refrescar):
    if arq.exists() and not refrescar:
        return False
    arq.parent.mkdir(parents=True, exist_ok=True)
    corpo = baixar(url)
    json.loads(corpo.decode("utf-8"))
    arq.write_bytes(corpo)
    manifesto[arq.name] = {
        "url": url,
        "bytes": len(corpo),
        "sha256": hashlib.sha256(corpo).hexdigest(),
        "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    time.sleep(PAUSA)
    return True


def principal():
    ap = argparse.ArgumentParser(description="Coleta bruta da ESPN (scoreboard por dia e summary por jogo).")
    ap.add_argument("--temporada", type=int, default=2026)
    ap.add_argument("--inicio")
    ap.add_argument("--fim")
    ap.add_argument("--refrescar", action="store_true", help="baixa de novo mesmo se já existir")
    a = ap.parse_args()

    ini, fim = TEMPORADAS.get(a.temporada, (None, None))
    if a.inicio:
        ini = date.fromisoformat(a.inicio)
    if a.fim:
        fim = date.fromisoformat(a.fim)
    if not ini or not fim:
        sys.exit("informe --inicio e --fim para esta temporada")

    pasta = RAIZ / "data" / "raw" / "espn" / LIGA / str(a.temporada)
    (pasta / "scoreboard").mkdir(parents=True, exist_ok=True)
    (pasta / "summary").mkdir(parents=True, exist_ok=True)
    arq_manifesto = pasta / "manifest.json"
    manifesto = json.loads(arq_manifesto.read_text(encoding="utf-8")) if arq_manifesto.exists() else {}

    novos = {"scoreboard": 0, "summary": 0}
    ids = []
    d = ini
    while d <= fim:
        arq = pasta / "scoreboard" / f"{d:%Y%m%d}.json"
        if salvar_se_preciso(arq, f"{BASE}scoreboard?dates={d:%Y%m%d}", manifesto, a.refrescar):
            novos["scoreboard"] += 1
        for e in json.loads(arq.read_text(encoding="utf-8")).get("events", []):
            ids.append(e["id"])
        d += timedelta(days=1)

    for eid in sorted(set(ids)):
        arq = pasta / "summary" / f"{eid}.json"
        if salvar_se_preciso(arq, f"{BASE}summary?event={eid}", manifesto, a.refrescar):
            novos["summary"] += 1

    arq_manifesto.write_text(json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"temporada {a.temporada}: {ini} a {fim}")
    print(f"jogos encontrados: {len(set(ids))} | baixados agora: {novos} | no manifesto: {len(manifesto)} arquivos")
    print(f"pasta: {pasta}")


if __name__ == "__main__":
    principal()
