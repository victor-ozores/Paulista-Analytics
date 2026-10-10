"""Experimento: captura da FPF por navegador automatizado. Testado em 06/10/2026: o portal bloqueia (HTTP 403, desafio anti-robô).
Mantido só para rechecar se o bloqueio mudou. Método oficial: scripts/captura_fpf_navegador.js."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
JS = RAIZ / "scripts" / "captura_fpf_navegador.js"
SINAIS_DE_BLOQUEIO = ("just a moment", "attention required", "access denied", "verify you are human")


def fnv(texto):
    h = 0x811C9DC5
    for b in texto.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def principal():
    ap = argparse.ArgumentParser(description="Captura jogos e classificação oficiais da FPF dirigindo um navegador de verdade.")
    ap.add_argument("--idcampeonato", type=int, default=73)
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--idcategoria", type=int, default=39)
    ap.add_argument("--prefixo", default="fpf_a1_2026")
    ap.add_argument("--saida", default=str(RAIZ / "data" / "referencia"))
    ap.add_argument("--canal", default="msedge", help="navegador instalado: msedge ou chrome")
    ap.add_argument("--headless", action="store_true", help="sem janela (mais fácil de ser barrado)")
    a = ap.parse_args()

    url = f"https://futebolpaulista.com.br/Competicoes/Classificacao.aspx?idCampeonato={a.idcampeonato}&ano={a.ano}&idCategoria={a.idcategoria}&nav=1"
    cfg = {"idCampeonato": a.idcampeonato, "ano": a.ano, "idCategoria": a.idcategoria, "prefixo": a.prefixo, "baixar": False}

    with sync_playwright() as p:
        try:
            nav = p.chromium.launch(channel=a.canal, headless=a.headless)
        except PlaywrightError as e:
            sys.exit(f"não consegui abrir o navegador '{a.canal}': {str(e).splitlines()[0]}")
        pagina = nav.new_page()
        resp = pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
        pagina.wait_for_timeout(2500)
        titulo = (pagina.title() or "").lower()
        status = resp.status if resp else 0
        if status >= 400 or any(s in titulo for s in SINAIS_DE_BLOQUEIO):
            nav.close()
            sys.exit(f"BLOQUEADO pelo portal (HTTP {status}, título '{titulo}'). Não há tentativa de contornar. Use scripts/captura_fpf_navegador.js no console do navegador.")
        sonda = pagina.evaluate(
            """async cfg => {
                const r = await fetch('/Handlers/Competicoes/ListarClassificacaoFases.ashx?idCampeonato=' + cfg.idCampeonato + '&exercicio=' + cfg.ano + '&idCategoria=' + cfg.idCategoria + '&_=' + Date.now());
                return { status: r.status, desafio: r.headers.get('cf-mitigated') };
            }""",
            cfg,
        )
        if sonda["status"] >= 400 or sonda["desafio"]:
            nav.close()
            sys.exit(f"BLOQUEADO: o portal respondeu HTTP {sonda['status']} (desafio anti-robô: {sonda['desafio']}) às consultas de dados. Nenhum disfarce é usado. Use scripts/captura_fpf_navegador.js no console do navegador.")
        pagina.evaluate("cfg => { window.__CFG_OVERRIDE = cfg; }", cfg)
        try:
            resultado = pagina.evaluate(JS.read_text(encoding="utf-8"))
        except PlaywrightError as e:
            nav.close()
            sys.exit(f"BLOQUEADO ou instável: o portal passou a responder sem JSON no meio da captura ({str(e).splitlines()[0][:120]}). Nenhum disfarce é usado. Use scripts/captura_fpf_navegador.js no console do navegador.")
        nav.close()

    if not resultado or not resultado.get("jogos"):
        sys.exit("o portal respondeu sem jogos; nada foi salvo")

    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    arqs = {"jogos": saida / f"{a.prefixo}_jogos.csv", "classificacao": saida / f"{a.prefixo}_classificacao.csv", "fases": saida / f"{a.prefixo}_fases.csv"}
    resumo = {"metodo": "playwright", "canal": a.canal, "url": url, "capturado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "arquivos": {}}
    for chave, arq in arqs.items():
        texto = resultado[chave]
        arq.write_text(texto, encoding="utf-8", newline="\n")
        resumo["arquivos"][arq.name] = {"linhas": texto.count("\n") - 1, "bytes": len(texto.encode("utf-8")), "hash_fnv1a": fnv(texto)}
    (saida / f"{a.prefixo}_captura.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    for nome, info in resumo["arquivos"].items():
        print(f"{nome}: {info['linhas']} linhas | {info['bytes']} bytes | hash {info['hash_fnv1a']}")
    print(f"salvo em {saida}")


if __name__ == "__main__":
    principal()
