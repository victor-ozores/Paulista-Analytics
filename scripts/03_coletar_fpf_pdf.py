import argparse
import csv
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CABECALHO = {"User-Agent": "Mozilla/5.0"}
PAUSA = 0.4
TENTATIVAS = 3
URL_SUMULA = "https://conteudo.fpf.org.br/sumulas/{ano}/{cod}/{n}.pdf"
URL_BOLETIM = "https://conteudo.fpf.org.br/Competicoes/{ano}/{cod}/boletins-financeiros/{n}/boletins/{n}.pdf"


def baixar(url):
    ultimo = None
    for t in range(1, TENTATIVAS + 1):
        try:
            req = urllib.request.Request(url, headers=CABECALHO)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return e.code, b""
            ultimo = e
        except Exception as e:
            ultimo = e
        time.sleep(PAUSA * t * 2)
    raise RuntimeError(f"falhou {url}: {ultimo}")


def principal():
    ap = argparse.ArgumentParser(description="Baixa súmulas e boletins financeiros oficiais da FPF (PDF).")
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--cod", default="3973", help="código da pasta de PDFs da competição (vem dos links do JSON de jogos)")
    ap.add_argument("--jogos", default=str(RAIZ / "data" / "referencia" / "fpf_a1_2026_jogos.csv"))
    ap.add_argument("--refrescar", action="store_true")
    a = ap.parse_args()

    with open(a.jogos, encoding="utf-8", newline="") as f:
        numeros = sorted(int(l["numero"]) for l in csv.DictReader(f, delimiter=";"))
    pasta = RAIZ / "data" / "raw" / "fpf_pdf" / str(a.ano)
    arq_man = pasta / "manifest.json"
    man = json.loads(arq_man.read_text(encoding="utf-8")) if arq_man.exists() else {}
    novos, ausentes = 0, []

    for tipo, modelo in (("sumula", URL_SUMULA), ("boletim", URL_BOLETIM)):
        (pasta / tipo).mkdir(parents=True, exist_ok=True)
        for n in numeros:
            chave = f"{tipo}/{n}.pdf"
            arq = pasta / chave
            if arq.exists() and not a.refrescar:
                continue
            url = modelo.format(ano=a.ano, cod=a.cod, n=n)
            status, corpo = baixar(url)
            time.sleep(PAUSA)
            if status == 200 and corpo.startswith(b"%PDF"):
                arq.write_bytes(corpo)
                man[chave] = {"url": url, "bytes": len(corpo), "sha256": hashlib.sha256(corpo).hexdigest(), "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                novos += 1
            else:
                man[chave] = {"url": url, "status": status, "ausente": True, "verificado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                ausentes.append(chave)

    arq_man.write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    ok = sum(1 for v in man.values() if not v.get("ausente"))
    print(f"jogos: {len(numeros)} | PDFs esperados: {2 * len(numeros)} | baixados agora: {novos} | presentes: {ok} | ausentes: {len(ausentes)}")
    for c in ausentes:
        print("  ausente:", c, man[c]["status"])
    print(f"pasta: {pasta}")


if __name__ == "__main__":
    principal()
