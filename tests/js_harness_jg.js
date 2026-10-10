const vm = require("vm");
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (!scripts.length) throw new Error("sem <script>");
const comLogos = process.argv[3] !== "semlogos";

class Fake {
  constructor(nome) {
    this.nome = nome;
    this.innerHTML = "";
    this.textContent = "";
    this.style = {};
    this.filhos = {};
    this.ouvintes = {};
    this.attrs = {};
    this.classes = new Set();
    const cls = this.classes;
    this.classList = {
      add: (c) => cls.add(c),
      remove: (c) => cls.delete(c),
      toggle: (c, on) => {
        const quer = on === undefined ? !cls.has(c) : !!on;
        if (quer) cls.add(c);
        else cls.delete(c);
        return quer;
      },
      contains: (c) => cls.has(c),
    };
    this.offsetParent = {};
    this.offsetWidth = 100;
    this.offsetHeight = 100;
    this.clientWidth = 1920;
    this.clientHeight = 1024;
    this.scrollTop = 0;
  }
  querySelector(sel) {
    return this.filhos[sel] || (this.filhos[sel] = new Fake(sel));
  }
  querySelectorAll() {
    return [];
  }
  addEventListener(ev, fn) {
    (this.ouvintes[ev] = this.ouvintes[ev] || []).push(fn);
  }
  getAttribute(k) {
    return k in this.attrs ? this.attrs[k] : null;
  }
  setAttribute(k, v) {
    this.attrs[k] = v;
  }
  getBoundingClientRect() {
    return { left: 0, top: 0, width: 1920, height: 1024 };
  }
  focus() {}
}

const raiz = new Fake("jgx");
const doc = new Fake("document");
doc.getElementById = () => raiz;
doc.createElement = () => new Fake("criado");
const timers = [];
const ctx = {
  document: doc,
  location: { search: "?debug" },
  performance: { now: () => 0 },
  requestAnimationFrame() {},
  setTimeout: (fn) => timers.push(fn),
  clearTimeout() {},
  navigator: {},
  matchMedia: () => ({ matches: false }),
  console,
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
for (const s of scripts) {
  if (!comLogos && /^\s*window\.PA=\{clubes:/.test(s)) continue;
  vm.runInContext(s, ctx);
}
const fecharTimers = () => timers.splice(0).forEach((f) => f());

const V = ctx.__jgx;
if (!V) {
  console.log(JSON.stringify({ semGancho: true }));
  process.exit(0);
}
const EL = raiz.filhos;
const AJ = EL[".aj"], TIP = EL[".tip"];
const ruins = (t) => /NaN|undefined|Infinity|\[object|null/.test(t.replace(/(src|href)="[^"]*"/g, ""));
const decod = (s) => s.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const limpar = (t) => t.replace(/(src|href)="data:[^"]*"/g, '$1="L"');
const atributo = (tag, k) => {
  const m = new RegExp("[ ]" + k + '="([^"]*)"').exec(tag);
  return m ? decod(m[1]) : null;
};
const abertas = (h) => h.match(/<button\b[^>]*data-act="[^"]*"[^>]*>/g) || [];
const achar = (h, filtro) => abertas(h).find((t) => filtro(t));
function clicar(tag, dentroDaJanela) {
  const alvo = { getAttribute: (k) => atributo(tag, k), closest: (sel) => (sel === "[data-act]" && tag ? alvo : sel === ".cx" && tag && dentroDaJanela ? alvo : null) };
  for (const fn of raiz.ouvintes.click || []) fn({ target: alvo });
}
const ajudaAberta = () => AJ.classes.has("on");
const estado = () => ({ fase: V.est.fase, rod: V.est.rod, clube: V.est.clube, res: V.est.res, jogo: V.est.jogo, aba: V.est.aba, ajuda: ajudaAberta() });
const painel = (n) => EL[".p" + n].innerHTML;
const tudo = () => [EL[".ctl"].innerHTML, ...[1, 2, 3, 4, 5, 6].map(painel), EL[".sub"].textContent, EL[".rod"].innerHTML, AJ.innerHTML].join("\n");
const topo = () => EL[".p1 .rola"].scrollTop;

const saida = { filtros: [], jogos: [], cliques: [], teclas: [], tips: [] };
const reiniciar = () => {
  if (ajudaAberta()) V.acao("ajuda-fechar");
  V.acao("limpar");
  V.acao("aba", null, "pu");
  V.acao("jogo", String(V.D.jogos[V.D.jogos.length - 1].n), null);
  V.atualizar();
};

const clubes = V.ORDEM_CLUBES.map((c) => Number(c.id));
const rods = V.RODADAS.slice();
const cfgs = [{}, { fase: "p" }, { fase: "m" }, { res: "m" }, { res: "e" }, { res: "v" }];
for (const r of rods) cfgs.push({ rod: r });
for (const c of clubes) cfgs.push({ clube: c });
for (const c of clubes) cfgs.push({ clube: c, res: "v" });
for (const c of clubes) cfgs.push({ fase: "m", clube: c });
cfgs.push({ fase: "p", rod: 3 }, { fase: "m", rod: 3 }, { fase: "m", rod: 10 }, { rod: 12, res: "v" }, { rod: 5, res: "e" }, { fase: "p", clube: clubes[3], res: "m" }, { fase: "p", rod: 8, clube: clubes[0], res: "e" });
for (const cfg of cfgs) {
  reiniciar();
  const pedido = { fase: cfg.fase || "t", rod: cfg.rod === undefined ? null : cfg.rod, clube: cfg.clube === undefined ? null : cfg.clube, res: cfg.res === undefined ? null : cfg.res };
  if (cfg.fase) V.acao("fase", null, cfg.fase);
  if (cfg.rod !== undefined) V.acao("rod", null, String(cfg.rod));
  if (cfg.clube !== undefined) V.acao("clube", String(cfg.clube), null);
  if (cfg.res !== undefined) V.acao("res", null, cfg.res);
  saida.filtros.push({ pedido, estado: estado(), ctl: EL[".ctl"].innerHTML, sub: EL[".sub"].textContent, paineis: [1, 2, 3, 4, 5, 6].map((n) => limpar(painel(n))), topo: topo(), ruim: ruins(tudo()) });
}

reiniciar();
for (const j of V.D.jogos) {
  V.acao("aba", null, "pu");
  V.acao("jogo", String(j.n), null);
  const e = { n: j.n, estado: estado(), paineis: [2, 3, 4, 5].map((n) => limpar(painel(n))), abas: {}, ruim: false };
  for (const aba of ["pu", "ar", "es"]) {
    V.acao("aba", null, aba);
    e.abas[aba] = limpar(painel(6));
    e.ruim = e.ruim || ruins(tudo());
  }
  saida.jogos.push(e);
}
V.acao("aba", null, "pu");
saida.rodape = { rod: EL[".rod"].innerHTML, aj: AJ.innerHTML };
saida.clubes = clubes;
saida.rodadas = rods;
saida.jogosNoMata = V.D.jogos.filter((j) => j.f > 1).map((j) => j.n);

const registro = (rot, tag, dentro) => {
  const antes = estado();
  clicar(tag, dentro);
  saida.cliques.push({ rot, act: tag ? atributo(tag, "data-act") : null, v: tag ? atributo(tag, "data-v") : null, id: tag ? atributo(tag, "data-id") : null, tag: tag ? (/class="([a-z]+)/.exec(tag) || [])[1] || null : null, antes, depois: estado(), topoDepois: topo() });
};
const chip = (v) => achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "fase" && atributo(t, "data-v") === v);
const botao = (act) => achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === act);
const porAcao = (n, act, filtro) => achar(painel(n), (t) => atributo(t, "data-act") === act && filtro(t));
const rodChip = (r) => porAcao(1, "rod", (t) => atributo(t, "data-v") === String(r));
const crest = (c) => porAcao(1, "clube", (t) => atributo(t, "data-id") === String(c));
const resChip = (v) => porAcao(1, "res", (t) => atributo(t, "data-v") === v);
const linhaDoJogo = (n) => porAcao(1, "jogo", (t) => atributo(t, "data-id") === String(n));
const aba = (v) => porAcao(6, "aba", (t) => atributo(t, "data-v") === v);
const jogosDaFase = (f) => V.D.jogos.filter((j) => (f === "p" ? j.f === 1 : j.f > 1));
const foraDoMata = clubes.find((c) => !V.D.jogos.some((j) => j.f > 1 && (j.m === c || j.v === c)));
const noMata = clubes.find((c) => V.D.jogos.some((j) => j.f > 1 && (j.m === c || j.v === c)));
const primeiroDoMata = jogosDaFase("m")[0].n;
const primeiroDaPrimeira = jogosDaFase("p")[0].n;
const jogoDasQuartas = V.D.jogos.find((j) => j.r === 9);
const resDasQuartas = jogoDasQuartas.gm > jogoDasQuartas.gv ? "m" : jogoDasQuartas.gm < jogoDasQuartas.gv ? "v" : "e";

reiniciar();
registro("rodada 3", rodChip(3), false);
registro("rodada 3 de novo solta", rodChip(3), false);
registro("rodada 3 outra vez", rodChip(3), false);
registro("chip mata-mata solta a rodada que nao existe nela", chip("m"), false);
registro("chip todas", chip("t"), false);
registro("clube fora do mata-mata", crest(foraDoMata), false);
registro("chip mata-mata solta o clube que nao jogou nela", chip("m"), false);
registro("chip todas de novo", chip("t"), false);
registro("clube no mata-mata", crest(noMata), false);
registro("rodada 12 com o clube", rodChip(12), false);
registro("resultado visitante", resChip("v"), false);
registro("resultado visitante de novo solta", resChip("v"), false);
registro("limpar tudo", botao("limpar"), false);
registro("limpar sem nada", botao("limpar"), false);
registro("chip 1a fase", chip("p"), false);
registro("rodada 12 fora da 1a fase", rodChip(12), false);
registro("resultado empate", resChip("e"), false);
const empatesDaPrimeira = V.lista().map((j) => j.n);
registro("jogo da lista", linhaDoJogo(empatesDaPrimeira[1]), false);
registro("jogo da lista de novo", linhaDoJogo(empatesDaPrimeira[1]), false);
registro("aba arbitragem", aba("ar"), false);
registro("aba estatisticas", aba("es"), false);
registro("aba publico", aba("pu"), false);
registro("abre ajuda", botao("ajuda"), false);
registro("clique fora da ajuda", null, false);
registro("abre ajuda de novo", botao("ajuda"), false);
registro("entendi", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
registro("jogo antes da ajuda", linhaDoJogo(empatesDaPrimeira[0]), false);
registro("abre ajuda com filtro", botao("ajuda"), false);
registro("clique dentro da janela", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
const achaSoltaResultado = () => {
  for (const c of clubes) for (const r of ["m", "e", "v"]) {
    const l = (f, cl, rs) => V.listaDe({ fase: f, rod: null, clube: cl, res: rs });
    if (l("t", c, r).length && !l("m", c, r).length && l("m", c, null).length) return { c, r };
  }
  return null;
};
const caso = achaSoltaResultado();
saida.casoDoResultado = caso;
reiniciar();
registro("clube do caso do resultado", crest(caso.c), false);
registro("resultado do caso", resChip(caso.r), false);
registro("chip mata-mata solta so o resultado", chip("m"), false);
const finalDeVolta = V.D.jogos.find((j) => j.r === 12);
const resFinal = finalDeVolta.gm > finalDeVolta.gv ? "m" : finalDeVolta.gm < finalDeVolta.gv ? "v" : "e";
const outroRes = ["m", "e", "v"].find((x) => x !== resFinal);
const clubeForaDaFinal = clubes.find((c) => c !== finalDeVolta.m && c !== finalDeVolta.v);
reiniciar();
registro("rodada 12", rodChip(12), false);
registro("resultado que houve na rodada 12", resChip(resFinal), false);
registro("clube que nao jogou a rodada 12", crest(clubeForaDaFinal), false);
registro("resultado que nao houve na rodada 12", resChip(outroRes), false);
registro("clube que jogou a rodada 12", crest(finalDeVolta.m), false);
registro("o mesmo clube de novo solta", crest(finalDeVolta.m), false);
saida.final12 = { m: finalDeVolta.m, v: finalDeVolta.v, res: resFinal, outro: outroRes, fora: clubeForaDaFinal };
saida.acoesVistas = [...new Set([...tudo().matchAll(/data-act="([^"]+)"/g)].map((m) => m[1]))].sort();
saida.foraDoMata = foraDoMata;
saida.noMata = noMata;
saida.primeiroDoMata = primeiroDoMata;
saida.primeiroDaPrimeira = primeiroDaPrimeira;

reiniciar();
V.acao("clube", "999999", null);
saida.clubeInexistente = estado();
V.acao("clube", null, null);
saida.clubeSemId = estado();
V.acao("clube", "abc", null);
saida.clubeTexto = estado();
V.acao("rod", null, "99");
saida.rodadaInexistente = estado();
V.acao("rod", null, "x");
saida.rodadaTexto = estado();
V.acao("res", null, "z");
saida.resultadoInvalido = estado();
V.acao("res", null, "__proto__");
saida.resultadoProto = estado();
V.acao("fase", null, "__proto__");
saida.faseProto = estado();
V.acao("fase", null, "x");
saida.faseInvalida = estado();
V.acao("aba", null, "x");
saida.abaInvalida = estado();
V.acao("jogo", "999", null);
saida.jogoInexistente = estado();
V.acao("jogo", "abc", null);
saida.jogoTexto = estado();
V.acao("fase", null, "m");
V.acao("clube", String(foraDoMata), null);
saida.clubeForaDaFase = estado();
V.acao("jogo", String(primeiroDaPrimeira), null);
saida.jogoForaDaLista = estado();
V.acao("rod", null, "3");
saida.rodadaForaDaFase = estado();

reiniciar();
const t = saida.teclas;
t.push({ rot: "esc sem nada", tratou: V.tecla("Escape", false), estado: estado() });
V.acao("fase", null, "m");
V.acao("rod", null, "9");
V.acao("clube", String(jogoDasQuartas.m), null);
V.acao("res", null, resDasQuartas);
const comTudo = estado();
t.push({ rot: "esc solta o resultado primeiro", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "esc solta o clube", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "esc solta a rodada", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "esc solta a fase", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "esc de novo nao trata", tratou: V.tecla("Escape", false), estado: estado() });
saida.comTudo = comTudo;
saida.quartas = { clube: jogoDasQuartas.m, res: resDasQuartas };
V.acao("clube", String(noMata), null);
t.push({ rot: "backspace solta o clube", antes: estado(), tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "abre com ?", tratou: V.tecla("?", false), estado: estado() });
t.push({ rot: "seta com a ajuda aberta nao anda", tratou: V.tecla("ArrowDown", false), estado: estado() });
t.push({ rot: "esc fecha a ajuda", tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "h abre", tratou: V.tecla("h", false), estado: estado() });
t.push({ rot: "enter fecha", tratou: V.tecla("Enter", false), estado: estado() });
t.push({ rot: "h com ctrl nao abre", tratou: V.tecla("h", true), estado: estado() });
t.push({ rot: "outra tecla", tratou: V.tecla("x", false), estado: estado() });
V.tecla("h", false);
t.push({ rot: "esc com ajuda e filtro fecha so a ajuda", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
V.tecla("?", false);
t.push({ rot: "backspace com ajuda aberta nao solta", tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "espaco fecha a ajuda", tratou: V.tecla(" ", false), estado: estado() });
reiniciar();
V.acao("fase", null, "m");
const jogoDoMata = V.D.jogos.find((j) => j.f > 1);
const resDoMata = jogoDoMata.gm > jogoDoMata.gv ? "m" : jogoDoMata.gm < jogoDoMata.gv ? "v" : "e";
V.acao("res", null, resDoMata);
V.tecla("h", false);
t.push({ rot: "esc com ajuda e resultado fecha so a ajuda", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
saida.resDoMata = resDoMata;
reiniciar();
const ultimo = V.D.jogos[V.D.jogos.length - 1].n;
const primeiro = V.D.jogos[0].n;
t.push({ rot: "seta para baixo no ultimo jogo", antes: estado(), tratou: V.tecla("ArrowDown", false), estado: estado(), topo: topo() });
t.push({ rot: "seta para cima anda um", antes: estado(), tratou: V.tecla("ArrowUp", false), estado: estado(), topo: topo() });
saida.limitesDeJogos = { primeiro, ultimo };
for (let i = 0; i < 80; i++) V.tecla("ArrowUp", false);
t.push({ rot: "seta para cima no primeiro jogo", antes: estado(), tratou: V.tecla("ArrowUp", false), estado: estado(), topo: topo() });
t.push({ rot: "seta para baixo desce um", antes: estado(), tratou: V.tecla("ArrowDown", false), estado: estado(), topo: topo() });
V.acao("clube", String(clubes[0]), null);
const daLista = V.lista().map((j) => j.n);
t.push({ rot: "seta com clube anda so na lista", antes: estado(), tratou: V.tecla("ArrowDown", false), estado: estado(), lista: daLista });
const teclaDoc = (k) => { let prevenido = false; for (const fn of doc.ouvintes.keydown || []) fn({ key: k, ctrlKey: false, metaKey: false, preventDefault() { prevenido = true; } }); return prevenido; };
reiniciar();
V.acao("clube", String(noMata), null);
const escDoc = teclaDoc("Escape");
const clubeDepoisDoEsc = V.est.clube;
V.acao("clube", String(noMata), null);
raiz.offsetParent = null;
const comEscondido = teclaDoc("Escape");
raiz.offsetParent = {};
saida.teclaNoDocumento = { escPrevenido: escDoc, clubeDepoisDoEsc, escondidoPrevenido: comEscondido, clubeEscondido: V.est.clube };
reiniciar();

const rolagem = [];
reiniciar();
for (let k = 0; k < 72; k++) {
  V.acao("jogo", String(V.D.jogos[k].n), null);
  rolagem.push({ n: V.D.jogos[k].n, topo: topo() });
}
for (let k = 71; k >= 0; k--) {
  V.acao("jogo", String(V.D.jogos[k].n), null);
  rolagem.push({ n: V.D.jogos[k].n, topo: topo() });
}
saida.rolagem = rolagem;
reiniciar();

const antesG = V.geometria(0);
V.D.sub[0].push([0, 1, 2, 1, 45, antesG.e1 + 5, 0]);
V.D.ev[0].push(["a", 2, 90, antesG.e2 + 4, 1, 0, 0, 0, 0]);
const depoisG = V.geometria(0);
saida.geometriaSintetica = { a1: V.D.jogos[0].a1, a2: V.D.jogos[0].a2, antes: [antesG.e1, antesG.e2], depois: [depoisG.e1, depoisG.e2] };
V.D.sub[0].pop();
V.D.ev[0].pop();
fecharTimers();
const alvos = [];
const estadosDeDica = [[{}, 72], [{ fase: "m" }, primeiroDoMata], [{ clube: noMata }, null], [{ rod: 12 }, null], [{}, 47], [{}, 68], [{}, 41]];
for (const [cfg, jogo] of estadosDeDica) {
  reiniciar();
  if (cfg.fase) V.acao("fase", null, cfg.fase);
  if (cfg.clube) V.acao("clube", String(cfg.clube), null);
  if (cfg.rod) V.acao("rod", null, String(cfg.rod));
  if (jogo) V.acao("jogo", String(jogo), null);
  for (const a of ["pu", "ar", "es"]) {
    V.acao("aba", null, a);
    const blocos = [...[1, 2, 3, 4, 5, 6].map((n) => ["p" + n, painel(n)]), ["controles", EL[".ctl"].innerHTML], ["rodape", EL[".rod"].innerHTML]];
    for (const [rot, h] of blocos) for (const m of h.matchAll(/data-tip="([^"]*)"/g)) alvos.push([estado(), rot, decod(m[1])]);
    alvos.push([estado(), "cabecalho", EL[".sub"].attrs["data-tip"]]);
  }
}
for (const [est, rot, tip] of alvos) {
  const d = { getAttribute: (k) => (k === "data-tip" ? tip : null) };
  const alvo = { closest: (sel) => (sel === "[data-tip]" ? d : null) };
  for (const fn of raiz.ouvintes.mouseover || []) fn({ target: alvo, clientX: 300, clientY: 200 });
  fecharTimers();
  saida.tips.push({ rot, tip, html: TIP.innerHTML, visivel: TIP.classes.has("on"), tipHtml: V.tipHtml(tip) });
  for (const fn of raiz.ouvintes.mouseleave || []) fn({});
}
saida.tipEscondeAoSair = !TIP.classes.has("on");
saida.tipHtml = { completo: V.tipHtml("Título||@A::1\nB::2||Parágrafo||~Nota"), escapado: V.tipHtml('<b>x</b> & "y"') };
console.log(JSON.stringify(saida));
