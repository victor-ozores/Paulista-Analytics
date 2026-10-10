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

const raiz = new Fake("glx");
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

const V = ctx.__glx;
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
const deClube = (id, classe) => (t) => atributo(t, "data-act") === "clube" && atributo(t, "data-id") === String(id) && new RegExp('class="' + classe + '[ "]').test(t);
function clicar(tag, dentroDaJanela) {
  const alvo = { getAttribute: (k) => atributo(tag, k), closest: (sel) => (sel === "[data-act]" && tag ? alvo : sel === ".cx" && tag && dentroDaJanela ? alvo : null) };
  for (const fn of raiz.ouvintes.click || []) fn({ target: alvo });
}
const ajudaAberta = () => AJ.classes.has("on");
const estado = () => ({ fase: V.est.fase, clube: V.est.clube, ajuda: ajudaAberta() });
const painel = (n) => EL[".p" + n].innerHTML;
const tudo = () => [EL[".kpis"].innerHTML, ...[1, 2, 3, 4, 5].map(painel), EL[".ctl"].innerHTML, EL[".sub"].textContent, EL[".rod"].innerHTML, AJ.innerHTML].join("\n");

const saida = { estados: [], cliques: [], teclas: [], tips: [] };

function foto(f, c) {
  V.est.fase = f;
  V.est.clube = c;
  V.atualizar();
  return {
    f,
    c,
    kpis: limpar(EL[".kpis"].innerHTML),
    paineis: [1, 2, 3, 4, 5].map((n) => limpar(painel(n))),
    ctl: EL[".ctl"].innerHTML,
    sub: EL[".sub"].textContent,
    ruim: ruins(tudo()),
  };
}
const clubesDaFase = (f) => [...new Set(V.nosJogos(f, null).flatMap((j) => [j.m, j.v]))].sort((a, b) => a - b);
for (const f of ["t", "p", "m"]) {
  saida.estados.push(foto(f, null));
  for (const c of clubesDaFase(f)) saida.estados.push(foto(f, c));
}
V.est.fase = "t";
V.est.clube = null;
V.atualizar();
saida.rodape = { rod: EL[".rod"].innerHTML, aj: AJ.innerHTML };
saida.clubes = V.D.clubes.map((c) => Number(c.id));
saida.clubesNoMata = clubesDaFase("m");

const registro = (rot, tag, dentro) => {
  const antes = estado();
  clicar(tag, dentro);
  saida.cliques.push({ rot, act: tag ? atributo(tag, "data-act") : null, v: tag ? atributo(tag, "data-v") : null, id: tag ? atributo(tag, "data-id") : null, tag: tag ? (/class="([a-z]+)/.exec(tag) || [])[1] || null : null, antes, depois: estado() });
};
const reiniciar = () => { V.est.fase = "t"; V.est.clube = null; if (ajudaAberta()) V.acao("ajuda-fechar"); V.atualizar(); };
const chip = (v) => achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "fase" && atributo(t, "data-v") === v);
const botao = (act) => achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === act);
const foraDoMata = saida.clubes.find((c) => !saida.clubesNoMata.includes(c));
const noMata = saida.clubesNoMata[0];

reiniciar();
registro("pc do clube fora do mata-mata", achar(painel(4), deClube(foraDoMata, "pc")), false);
registro("pc do mesmo de novo", achar(painel(4), deClube(foraDoMata, "pc")), false);
registro("pc do clube fora do mata-mata outra vez", achar(painel(4), deClube(foraDoMata, "pc")), false);
registro("chip mata-mata solta o clube que nao jogou nela", chip("m"), false);
registro("chip todas", chip("t"), false);
registro("pc do clube que esta no mata-mata", achar(painel(4), deClube(noMata, "pc")), false);
registro("chip mata-mata mantem o clube", chip("m"), false);
registro("pc do mesmo no mata-mata solta", achar(painel(4), deClube(noMata, "pc")), false);
registro("chip 1a fase", chip("p"), false);
const primeiro = /<button class="ar[ "][^>]*data-id="(\d+)"/.exec(painel(3));
registro("linha da artilharia", achar(painel(3), (t) => atributo(t, "data-act") === "clube" && atributo(t, "data-id") === primeiro[1] && /class="ar[ "]/.test(t)), false);
registro("linha da artilharia de novo", achar(painel(3), (t) => atributo(t, "data-act") === "clube" && atributo(t, "data-id") === primeiro[1] && /class="ar[ "]/.test(t)), false);
registro("limpar com fase", botao("limpar"), false);
registro("chip mata-mata", chip("m"), false);
registro("pc no mata-mata", achar(painel(4), deClube(noMata, "pc")), false);
registro("limpar solta clube e fase", botao("limpar"), false);
registro("limpar sem nada", botao("limpar"), false);
registro("abre ajuda", botao("ajuda"), false);
registro("clique fora da ajuda", null, false);
registro("abre ajuda de novo", botao("ajuda"), false);
registro("entendi", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
registro("pc antes da ajuda", achar(painel(4), deClube(noMata, "pc")), false);
registro("abre ajuda com clube", botao("ajuda"), false);
registro("clique dentro da janela", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
saida.acoesVistas = [...new Set([...tudo().matchAll(/data-act="([^"]+)"/g)].map((m) => m[1]))].sort();
saida.foraDoMata = foraDoMata;
saida.noMata = noMata;
reiniciar();
V.acao("clube", "999999", null);
saida.clubeInexistente = estado();
V.acao("clube", null, null);
saida.clubeSemId = estado();
V.acao("clube", "abc", null);
saida.clubeTexto = estado();
V.acao("fase", null, "__proto__");
saida.faseProto = estado();
V.acao("fase", null, "x");
saida.faseInvalida = estado();
V.acao("fase", null, "m");
V.acao("clube", String(foraDoMata), null);
saida.clubeForaDaFase = estado();

reiniciar();
const t = saida.teclas;
t.push({ rot: "esc sem nada", tratou: V.tecla("Escape", false), estado: estado() });
V.acao("clube", String(noMata), null);
V.acao("fase", null, "m");
t.push({ rot: "esc solta o clube primeiro", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "esc depois solta a fase", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "esc de novo nao trata", tratou: V.tecla("Escape", false), estado: estado() });
V.acao("fase", null, "p");
V.acao("clube", String(noMata), null);
t.push({ rot: "backspace solta o clube", antes: estado(), tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "backspace solta a fase", tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "abre com ?", tratou: V.tecla("?", false), estado: estado() });
t.push({ rot: "esc fecha a ajuda", tratou: V.tecla("Escape", false), estado: estado() });
t.push({ rot: "h abre", tratou: V.tecla("h", false), estado: estado() });
t.push({ rot: "enter fecha", tratou: V.tecla("Enter", false), estado: estado() });
t.push({ rot: "h com ctrl nao abre", tratou: V.tecla("h", true), estado: estado() });
t.push({ rot: "outra tecla", tratou: V.tecla("x", false), estado: estado() });
V.acao("fase", null, "m");
V.acao("clube", String(noMata), null);
V.tecla("h", false);
t.push({ rot: "esc com ajuda e clube fecha so a ajuda", antes: estado(), tratou: V.tecla("Escape", false), estado: estado() });
V.tecla("?", false);
t.push({ rot: "backspace com ajuda aberta nao solta", tratou: V.tecla("Backspace", false), estado: estado() });
t.push({ rot: "espaco fecha a ajuda", tratou: V.tecla(" ", false), estado: estado() });
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

fecharTimers();
const alvos = [];
for (const [f, c] of [["t", null], ["p", null], ["m", null], ["t", noMata], ["p", foraDoMata], ["m", noMata]]) {
  V.est.fase = f;
  V.est.clube = c;
  V.atualizar();
  const blocos = [["kpis", EL[".kpis"].innerHTML], ...[1, 2, 3, 4, 5].map((n) => ["p" + n, painel(n)]), ["controles", EL[".ctl"].innerHTML], ["rodape", EL[".rod"].innerHTML]];
  for (const [rot, h] of blocos) for (const m of h.matchAll(/data-tip="([^"]*)"/g)) alvos.push([f, c, rot, decod(m[1])]);
  alvos.push([f, c, "cabecalho", EL[".sub"].attrs["data-tip"]]);
}
for (const [f, c, rot, tip] of alvos) {
  const d = { getAttribute: (k) => (k === "data-tip" ? tip : null) };
  const alvo = { closest: (sel) => (sel === "[data-tip]" ? d : null) };
  for (const fn of raiz.ouvintes.mouseover || []) fn({ target: alvo, clientX: 300, clientY: 200 });
  fecharTimers();
  saida.tips.push({ f, c, rot, tip, html: TIP.innerHTML, visivel: TIP.classes.has("on"), tipHtml: V.tipHtml(tip) });
  for (const fn of raiz.ouvintes.mouseleave || []) fn({});
}
saida.tipEscondeAoSair = !TIP.classes.has("on");
const totalAtletas = V.D.atl.length;
V.D.atl.reverse();
V.D.gols.forEach((g) => { g.a = totalAtletas - 1 - g.a; });
saida.permutado = [foto("t", null), foto("p", null)];
saida.tipHtml = { completo: V.tipHtml("Título||@A::1\nB::2||Parágrafo||~Nota"), escapado: V.tipHtml('<b>x</b> & "y"') };
console.log(JSON.stringify(saida));
