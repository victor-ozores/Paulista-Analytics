"""Tira os prints das oito telas do dashboard para o README (docs/prints/*.png, 1920 x 1080).

Abre prototype/app/index.html (gerado por scripts/13_montar_app.py, é a mesma página que vai na medida html_dashboard do Power BI)
num Edge ou Chrome instalado, pelo Playwright, e põe cada tela num estado que mostra bem o que ela faz. Os estados usam os ganchos
`?debug` das telas. Nada é coletado nem gravado fora de docs/prints/.

Uso: python scripts/16_gerar_prints.py [--so vg,jg]    (sem --so, tira todos)
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from comum import RAIZ

PAGINA = RAIZ / "prototype" / "app" / "index.html"
SAIDA = RAIZ / "docs" / "prints"

PREPARO_DUELO = """(par) => {
  const V = window.__vsx, id = (c) => V.D.clubes.find((x) => x.curto === c).id;
  V.abrirVS(id(par[0]), id(par[1]), null);
  V.est.tab = par[2];
  V.mostrarTab(false);
}"""

PRINTS = [
    ("01_visao_geral", "vg", None, None),
    ("02_duelo_escolha", "vs", "() => { const V = window.__vsx; V.voltar(); V.est.a = V.D.clubes.find((c) => c.curto === 'Palmeiras').id; V.est.b = V.D.clubes.find((c) => c.curto === 'Novorizontino').id; V.est.aba = 'clubes'; V.atualizarSel(); }", None),
    ("03_duelo_comparativo", "vs", PREPARO_DUELO, ["Palmeiras", "Novorizontino", "comp"]),
    ("04_duelo_confronto_direto", "vs", PREPARO_DUELO, ["Palmeiras", "Novorizontino", "conf"]),
    ("05_classificacao_e_chave", "clas", None, None),
    ("06_gols_e_artilharia", "gl", None, None),
    ("07_disciplina_e_arbitragem", "ds", None, None),
    ("08_jogos_e_escalacoes", "jg", "() => { const J = window.__jgx; J.acao('limpar'); J.acao('jogo', 72); J.acao('aba', null, 'pu'); }", None),
    ("09_publico_e_renda", "fin", None, None),
    ("10_conferencia_e_fontes", "conf", None, None),
]


def principal():
    so = None
    if "--so" in sys.argv:
        so = set(sys.argv[sys.argv.index("--so") + 1].split(","))
    if not PAGINA.exists():
        raise SystemExit("rode scripts/13_montar_app.py antes (falta prototype/app/index.html)")
    SAIDA.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            nav = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            nav = p.chromium.launch(channel="chrome", headless=True)
        pagina = nav.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        erros = []
        pagina.on("pageerror", lambda e: erros.append(str(e)))
        for nome, tela, preparo, arg in PRINTS:
            if so and tela not in so and nome not in so:
                continue
            pagina.goto(PAGINA.as_uri() + "?debug#" + tela)
            pagina.wait_for_function("window.PA && window.PA.ir && document.querySelector('#pa .barra')")
            pagina.evaluate(f"window.PA.ir('{tela}')")
            time.sleep(0.8)
            if preparo:
                pagina.evaluate(preparo, arg) if arg else pagina.evaluate(preparo)
            time.sleep(1.6)
            pagina.evaluate("document.getAnimations().forEach((a) => { try { a.finish() } catch (e) {} })")
            pagina.mouse.move(5, 1075)
            time.sleep(0.4)
            destino = SAIDA / f"{nome}.png"
            pagina.screenshot(path=str(destino))
            print(f"{destino.relative_to(RAIZ)}  {destino.stat().st_size // 1024} KB")
        nav.close()
    if erros:
        raise SystemExit("erros de JavaScript na página: " + "; ".join(erros[:3]))


if __name__ == "__main__":
    principal()
