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

const raiz = new Fake("vgx");
const doc = new Fake("document");
doc.getElementById = () => raiz;
doc.createElement = () => new Fake("criado");
const timers = [];
const idas = [];
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
ctx.PA = { ir: (nome) => idas.push(nome) };
vm.createContext(ctx);
for (const s of scripts) {
  if (!comLogos && /^\s*window\.PA=\{clubes:/.test(s)) continue;
  vm.runInContext(s, ctx);
}
ctx.PA.ir = (nome) => idas.push(nome);
const fecharTimers = () => timers.splice(0).forEach((f) => f());

const V = ctx.__vgx;
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
const estado = () => ({ fase: V.est.fase, ajuda: ajudaAberta() });
const PAINEIS = [".p0", ".p1", ".p2", ".p3", ".p4", ".p5"];
const painel = (n) => EL[".p" + n].innerHTML;
const tudo = () => [EL[".kpis"].innerHTML, ...[0, 1, 2, 3, 4, 5].map(painel), EL[".ctl"].innerHTML, EL[".sub"].textContent, EL[".rod"].innerHTML, AJ.innerHTML].join("\n");

const saida = { meta: V.D.meta, fases: {}, cliques: [], teclas: [], tips: [], idas };

function foto(f) {
  V.est.fase = f;
  V.atualizar({ semAnimar: true });
  return {
    f,
    kpis: limpar(EL[".kpis"].innerHTML),
    paineis: [0, 1, 2, 3, 4, 5].map((n) => limpar(painel(n))),
    ctl: EL[".ctl"].innerHTML,
    sub: EL[".sub"].textContent,
    subTip: EL[".sub"].attrs["data-tip"],
    ruim: ruins(tudo()),
    tem: [0, 1, 2, 3, 4, 5].map((n) => EL[".p" + n].classes.has("on")),
  };
}
for (const f of ["t", "p", "m"]) saida.fases[f] = foto(f);
V.est.fase = "t";
V.atualizar({ semAnimar: true });
saida.rodape = { rod: EL[".rod"].innerHTML, aj: AJ.innerHTML };
const metaReal = { camp: V.D.meta.camp, vice: V.D.meta.vice };
const corinthians = Object.values(V.CL).find((c) => c.curto === "Corinthians");
V.D.meta.camp = Number(corinthians.id);
V.D.meta.vice = metaReal.camp;
V.atualizar({ semAnimar: true });
saida.campeaoSintetico = { camp: V.D.meta.camp, vice: V.D.meta.vice, p0: limpar(painel(0)) };
V.D.meta.camp = metaReal.camp;
V.D.meta.vice = metaReal.vice;
V.atualizar({ semAnimar: true });

const registro = (rot, tag, dentro) => {
  const antes = estado();
  clicar(tag, dentro);
  saida.cliques.push({ rot, act: tag ? atributo(tag, "data-act") : null, v: tag ? atributo(tag, "data-v") : null, antes, depois: estado(), idas: idas.length });
};
const reiniciar = () => { V.est.fase = "t"; if (ajudaAberta()) V.acao("ajuda-fechar"); V.atualizar({ semAnimar: true }); };
const chip = (v) => achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "fase" && atributo(t, "data-v") === v);
const botao = (act) => achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === act);

reiniciar();
registro("chip todas com todas", chip("t"), false);
registro("chip 1a fase", chip("p"), false);
registro("chip 1a fase de novo", chip("p"), false);
registro("chip mata-mata", chip("m"), false);
registro("chip todas", chip("t"), false);
registro("chip mata-mata de novo", chip("m"), false);
registro("limpar", botao("limpar"), false);
registro("limpar sem filtro", botao("limpar"), false);
registro("chip 1a fase antes da ajuda", chip("p"), false);
registro("abre ajuda", botao("ajuda"), false);
registro("clique fora da ajuda", null, false);
registro("abre ajuda de novo", botao("ajuda"), false);
registro("entendi", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
registro("abre ajuda com filtro", botao("ajuda"), false);
registro("clique dentro da janela", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
registro("selo da conferencia", achar(painel(5), (t) => atributo(t, "data-act") === "conf"), false);
registro("selo de novo", achar(painel(5), (t) => atributo(t, "data-act") === "conf"), false);
saida.acoesVistas = [...new Set([...tudo().matchAll(/data-act="([^"]+)"/g)].map((m) => m[1]))].sort();
reiniciar();
V.acao("fase", null, "x");
saida.faseInvalida = estado();
V.acao("fase", null, null);
saida.faseNula = estado();
V.acao("fase", null, "__proto__");
saida.faseProto = estado();
V.acao("conf", null, null);

reiniciar();
const t = saida.teclas;
t.push({ rot: "esc sem filtro", tratou: V.tecla("Escape", false), estado: estado() });
V.acao("fase", null, "m");
t.push({ rot: "esc solta", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
V.acao("fase", null, "p");
t.push({ rot: "backspace solta", antes: estado(), tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "backspace sem filtro", tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "abre com ?", tratou: V.tecla("?", false), estado: estado() });
t.push({ rot: "esc fecha a ajuda", tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "h abre", tratou: V.tecla("h", false), estado: estado() });
t.push({ rot: "enter fecha", tratou: V.tecla("Enter", false), estado: estado() });
t.push({ rot: "h com ctrl nao abre", tratou: V.tecla("h", true), estado: estado() });
t.push({ rot: "outra tecla", tratou: V.tecla("x", false), estado: estado() });
V.acao("fase", null, "m");
V.tecla("h", false);
t.push({ rot: "esc com ajuda e filtro fecha so a ajuda", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
V.tecla("?", false);
t.push({ rot: "backspace com ajuda aberta nao solta", tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "espaco fecha a ajuda", tratou: V.tecla(" ", false), estado: estado() });
const teclaDoc = (k) => { let prevenido = false; for (const fn of doc.ouvintes.keydown || []) fn({ key: k, ctrlKey: false, metaKey: false, preventDefault() { prevenido = true; } }); return prevenido; };
reiniciar();
V.acao("fase", null, "p");
const escDoc = teclaDoc("Escape");
const faseDepoisDoEsc = V.est.fase;
V.acao("fase", null, "p");
raiz.offsetParent = null;
const comEscondido = teclaDoc("Escape");
raiz.offsetParent = {};
saida.teclaNoDocumento = { escPrevenido: escDoc, faseDepoisDoEsc, escondidoPrevenido: comEscondido, faseEscondido: V.est.fase };
reiniciar();

fecharTimers();
const alvos = [];
for (const f of ["t", "p", "m"]) {
  V.est.fase = f;
  V.atualizar({ semAnimar: true });
  const blocos = [["kpis", EL[".kpis"].innerHTML], ...[0, 1, 2, 3, 4, 5].map((n) => ["p" + n, painel(n)]), ["controles", EL[".ctl"].innerHTML], ["rodape", EL[".rod"].innerHTML]];
  for (const [rot, h] of blocos) for (const m of h.matchAll(/data-tip="([^"]*)"/g)) alvos.push([f, rot, decod(m[1])]);
  alvos.push([f, "cabecalho", EL[".sub"].attrs["data-tip"]]);
}
for (const [f, rot, tip] of alvos) {
  const d = { getAttribute: (k) => (k === "data-tip" ? tip : null) };
  const alvo = { closest: (sel) => (sel === "[data-tip]" ? d : null) };
  for (const fn of raiz.ouvintes.mouseover || []) fn({ target: alvo, clientX: 300, clientY: 200 });
  fecharTimers();
  saida.tips.push({ f, rot, tip, html: TIP.innerHTML, visivel: TIP.classes.has("on"), tipHtml: V.tipHtml(tip) });
  for (const fn of raiz.ouvintes.mouseleave || []) fn({});
}
saida.tipEscondeAoSair = !TIP.classes.has("on");
saida.tipHtml = { completo: V.tipHtml("Título||@A::1\nB::2||Parágrafo||~Nota"), escapado: V.tipHtml('<b>x</b> & "y"') };
console.log(JSON.stringify(saida));
