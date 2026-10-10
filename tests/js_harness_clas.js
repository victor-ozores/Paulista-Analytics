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

const raiz = new Fake("clx");
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

const C = ctx.__clx;
if (!C) {
  console.log(JSON.stringify({ semGancho: true }));
  process.exit(0);
}
const EL = raiz.filhos;
const AJ = EL[".aj"], TIP = EL[".tip"];
const ruins = (t) => /NaN|undefined|Infinity|\[object|null/.test(t.replace(/(src|href)="[^"]*"/g, ""));
const semTags = (t) => t.replace(/<[^>]*>/g, "");
const decod = (s) => s.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const limpar = (t) => t.replace(/(src|href)="data:[^"]*"/g, '$1="L"');
const atributo = (tag, k) => {
  const m = new RegExp("[ ]" + k + '="([^"]*)"').exec(tag);
  return m ? decod(m[1]) : null;
};
const abertas = (h) => h.match(/<(?:button|polyline|g)\b[^>]*data-act="[^"]*"[^>]*>/g) || [];
const achar = (h, filtro) => abertas(h).find((t) => filtro(t));
const deClube = (id, classe) => (t) => atributo(t, "data-act") === "clube" && atributo(t, "data-id") === String(id) && (!classe || new RegExp('class="' + classe + '[ "]').test(t));
function clicar(tag, dentroDaJanela) {
  const alvo = { getAttribute: (k) => atributo(tag, k), closest: (sel) => (sel === "[data-act]" && tag ? alvo : sel === ".cx" && tag && dentroDaJanela ? alvo : null) };
  for (const fn of raiz.ouvintes.click || []) fn({ target: alvo });
}
const ajudaAberta = () => AJ.classes.has("on");
const estado = () => ({ sel: C.est.sel, ajuda: ajudaAberta() });
const painel = (n) => EL[".p" + n].innerHTML;
const todosOsPaineis = () => [EL[".kpis"].innerHTML, painel(1), painel(2), painel(3), EL[".ctl"].innerHTML, EL[".rod"].innerHTML, AJ.innerHTML].join("\n");

const ids = C.D.tab.map((t) => t.c);
const saida = { meta: C.D.meta, estados: [], cliques: [], teclas: [], tips: [], ids };

function foto(sel) {
  C.est.sel = sel;
  C.atualizar({ semAnimar: true });
  const p1 = painel(1), p2 = painel(2), p3 = painel(3);
  return {
    sel,
    kpis: limpar(EL[".kpis"].innerHTML),
    p1: limpar(p1),
    p2: limpar(p2),
    p3: limpar(p3),
    ctl: EL[".ctl"].innerHTML,
    sub: EL[".sub"].textContent,
    ruim: ruins(p1) || ruins(p2) || ruins(p3) || ruins(EL[".kpis"].innerHTML) || ruins(EL[".ctl"].innerHTML) || ruins(EL[".sub"].textContent),
  };
}
for (const sel of [null, ...ids]) saida.estados.push(foto(sel));
C.est.sel = null;
C.atualizar({ semAnimar: true });
saida.rodape = { rod: EL[".rod"].innerHTML, aj: AJ.innerHTML, subTip: EL[".sub"].attrs["data-tip"], ruim: ruins(EL[".rod"].innerHTML) || ruins(AJ.innerHTML) };
saida.ordemQuartas = C.ordemQuartas().map((j) => j.n);
saida.camposDeTip = {};

const registro = (rot, tag, dentro) => {
  const antes = estado();
  if (!tag) { clicar(null, dentro); }
  else clicar(tag, dentro);
  saida.cliques.push({ rot, act: tag ? atributo(tag, "data-act") : null, id: tag ? atributo(tag, "data-id") : null, tag: tag ? (/^<(\w+)/.exec(tag) || [])[1] + (atributo(tag, "class") ? "." + atributo(tag, "class").split(" ")[0] : "") : null, antes, depois: estado() });
};
const reiniciar = () => { C.est.sel = null; if (ajudaAberta()) C.acao("ajuda-fechar"); C.atualizar({ semAnimar: true }); };

reiniciar();
for (const id of ids) {
  registro("linha da tabela " + id, achar(painel(1), deClube(id, "tr")), false);
  registro("linha da tabela de novo " + id, achar(painel(1), deClube(id, "tr")), false);
}
for (const id of ids) {
  registro("linha do grafico " + id, achar(painel(3), deClube(id, "hit")), false);
  registro("linha do grafico de novo " + id, achar(painel(3), deClube(id, "hit")), false);
  registro("rotulo do grafico " + id, achar(painel(3), deClube(id, "fim")), false);
  registro("rotulo do grafico de novo " + id, achar(painel(3), deClube(id, "fim")), false);
}
const noChaveamento = [...new Set([...painel(2).matchAll(/class="tl[ "][^>]*data-id="(\d+)"/g)].map((m) => Number(m[1])))];
saida.noChaveamento = noChaveamento;
for (const id of noChaveamento) {
  registro("time no chaveamento " + id, achar(painel(2), deClube(id, "tl")), false);
  registro("time no chaveamento de novo " + id, achar(painel(2), deClube(id, "tl")), false);
}
registro("botao do campeao", achar(painel(2), deClube(C.D.meta.camp, "cp")), false);
registro("botao do campeao de novo", achar(painel(2), deClube(C.D.meta.camp, "cp")), false);
registro("linha " + ids[2], achar(painel(1), deClube(ids[2], "tr")), false);
registro("troca direto para linha " + ids[5], achar(painel(1), deClube(ids[5], "tr")), false);
registro("limpar", achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "limpar"), false);
registro("limpar sem nada", achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "limpar"), false);
registro("abre ajuda", achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "ajuda"), false);
registro("clique fora da ajuda", null, false);
registro("abre ajuda de novo", achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "ajuda"), false);
registro("entendi", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
registro("linha antes da ajuda " + ids[0], achar(painel(1), deClube(ids[0], "tr")), false);
registro("abre ajuda com clube", achar(EL[".ctl"].innerHTML, (t) => atributo(t, "data-act") === "ajuda"), false);
registro("clique dentro da janela da ajuda", achar(AJ.innerHTML, (t) => atributo(t, "data-act") === "ajuda-fechar"), true);
saida.acoesVistas = [...new Set([...todosOsPaineis().matchAll(/data-act="([^"]+)"/g)].map((m) => m[1]))].sort();
reiniciar();
C.acao("clube", "999999", null);
saida.clubeInexistente = estado();
C.acao("clube", null, null);
saida.clubeSemId = estado();
C.acao("clube", "abc", null);
saida.clubeTextoInvalido = estado();

reiniciar();
const t = saida.teclas;
t.push({ rot: "esc sem clube", tratou: C.tecla("Escape", false), estado: estado() });
C.acao("clube", String(ids[3]), null);
t.push({ rot: "esc solta", antes: estado(), tratou: C.tecla("Escape", false), estado: estado() });
C.acao("clube", String(ids[3]), null);
t.push({ rot: "backspace solta", antes: estado(), tratou: C.tecla("Backspace", false), estado: estado() });
t.push({ rot: "backspace sem clube", tratou: C.tecla("Backspace", false), estado: estado() });
t.push({ rot: "abre com ?", tratou: C.tecla("?", false), estado: estado() });
t.push({ rot: "esc fecha a ajuda", tratou: C.tecla("Escape", false), estado: estado() });
t.push({ rot: "h abre", tratou: C.tecla("h", false), estado: estado() });
t.push({ rot: "enter fecha", tratou: C.tecla("Enter", false), estado: estado() });
t.push({ rot: "h com ctrl nao abre", tratou: C.tecla("h", true), estado: estado() });
t.push({ rot: "outra tecla", tratou: C.tecla("x", false), estado: estado() });
C.acao("clube", String(ids[1]), null);
C.tecla("h", false);
t.push({ rot: "esc com ajuda e clube fecha so a ajuda", antes: { sel: C.est.sel, ajuda: ajudaAberta() }, tratou: C.tecla("Escape", false), estado: estado() });
C.tecla("?", false);
t.push({ rot: "outra tecla com ajuda aberta", tratou: C.tecla("x", false), estado: estado() });
t.push({ rot: "backspace com ajuda aberta nao solta", tratou: C.tecla("Backspace", false), estado: estado() });
t.push({ rot: "? fecha", tratou: C.tecla("?", false), estado: estado() });
const teclaDoc = (k, extra) => { let prevenido = false; for (const fn of doc.ouvintes.keydown || []) fn({ key: k, ctrlKey: false, metaKey: false, preventDefault() { prevenido = true; }, ...extra }); return prevenido; };
reiniciar();
C.acao("clube", String(ids[4]), null);
const escDoc = teclaDoc("Escape");
const selDepoisDoEsc = estado().sel;
C.acao("clube", String(ids[4]), null);
raiz.offsetParent = null;
const comEscondido = teclaDoc("Escape");
raiz.offsetParent = {};
saida.teclaNoDocumento = { escPrevenido: escDoc, selDepoisDoEsc, escondidoPrevenido: comEscondido, selEscondido: estado().sel };
reiniciar();

fecharTimers();
const alvos = [];
for (const [rot, h] of [["tabela", painel(1)], ["chaveamento", painel(2)], ["grafico", painel(3)], ["kpis", EL[".kpis"].innerHTML], ["controles", EL[".ctl"].innerHTML], ["rodape", EL[".rod"].innerHTML]])
  for (const m of h.matchAll(/data-tip="([^"]*)"/g)) alvos.push([rot, decod(m[1])]);
alvos.push(["cabecalho", EL[".sub"].attrs["data-tip"]]);
for (const [rot, tip] of alvos) {
  const d = { getAttribute: (k) => (k === "data-tip" ? tip : null) };
  const alvo = { closest: (sel) => (sel === "[data-tip]" ? d : null) };
  for (const fn of raiz.ouvintes.mouseover || []) fn({ target: alvo, clientX: 300, clientY: 200 });
  fecharTimers();
  saida.tips.push({ rot, tip, html: TIP.innerHTML, visivel: TIP.classes.has("on"), tipHtml: C.tipHtml(tip) });
  for (const fn of raiz.ouvintes.mouseleave || []) fn({});
}
saida.tipEscondeAoSair = !TIP.classes.has("on");
saida.tipHtml = { completo: C.tipHtml("Título||@A::1\nB::2||Parágrafo||~Nota"), escapado: C.tipHtml('<b>x</b> & "y"') };
console.log(JSON.stringify(saida));
