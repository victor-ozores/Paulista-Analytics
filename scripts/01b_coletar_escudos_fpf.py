import hashlib
import io
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from PIL import Image

from comum import RAIZ, REF, URL_ESCUDO, clubes_da_fpf, ler_csv

SAIDA = RAIZ / "data" / "raw" / "escudos"
CABECALHO = {"User-Agent": "Mozilla/5.0"}
PAUSA = 0.4


def principal(refrescar=False):
    clubes = clubes_da_fpf(ler_csv(REF / "fpf_a1_2026_jogos.csv"))
    SAIDA.mkdir(parents=True, exist_ok=True)
    arq_man = SAIDA / "manifest.json"
    man = json.loads(arq_man.read_text(encoding="utf-8")) if arq_man.exists() else {}
    novos, problemas = 0, []
    for id_clube, nome in sorted(clubes.items()):
        idc = str(id_clube)
        arq = SAIDA / f"{idc}.png"
        if arq.exists() and not refrescar:
            continue
        url = URL_ESCUDO.format(id=idc)
        try:
            req = urllib.request.Request(url, headers=CABECALHO)
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo, tipo = r.read(), r.headers.get("Content-Type", "")
            img = Image.open(io.BytesIO(corpo))
            img.verify()
        except (urllib.error.URLError, OSError, ValueError) as e:
            problemas.append(f"{idc} {nome}: {e}")
            continue
        arq.write_bytes(corpo)
        w, h = Image.open(io.BytesIO(corpo)).size
        man[idc] = {"clube": nome, "url": url, "tipo": tipo, "bytes": len(corpo), "largura": w, "altura": h, "sha256": hashlib.sha256(corpo).hexdigest(), "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        novos += 1
        time.sleep(PAUSA)
    arq_man.write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"clubes: {len(clubes)} | baixados agora: {novos} | no manifesto: {len(man)} | problemas: {len(problemas)}")
    for p in problemas:
        print("  ", p)


if __name__ == "__main__":
    principal()
