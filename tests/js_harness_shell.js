const vm = require("vm");
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const cabeca = scripts.find((s) => s.trim().startsWith("window.PA=window.PA||{};window.PA.shell=true"));
const navegacao = scripts.find((s) => s.indexOf("window.PA.ir=ir") >= 0);
if (!cabeca || !navegacao) throw new Error("scripts do shell não encontrados");

function el(nome, atributos) {
  const cls = new Set(atributos && atributos.classe ? atributos.classe.split(" ") : []);
  const attrs = Object.assign({}, atributos && atributos.attrs);
  return {
    nome,
    classes: cls,
    attrs,
    classList: {
      toggle: (c, on) => {
        if (on) cls.add(c);
        else cls.delete(c);
      },
      add: (c) => cls.add(c),
      remove: (c) => cls.delete(c),
      contains: (c) => cls.has(c),
    },
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
    setAttribute: (k, v) => {
      attrs[k] = v;
    },
    removeAttribute: (k) => {
      delete attrs[k];
    },
    closest(sel) {
      return sel === "button" || sel === "button[data-mod]" ? this : null;
    },
    ouvintes: {},
    addEventListener(ev, fn) {
      this.ouvintes[ev] = fn;
    },
  };
}

const CHAVES = ["vg", "vs", "clas", "gl", "ds", "jg", "fin", "conf"];
const B = {};
for (const k of CHAVES) B[k] = el("b-" + k, { classe: k === "vg" ? "on" : "", attrs: k === "vg" ? { "data-mod": k, "aria-current": "page" } : { "data-mod": k } });
const botoes = CHAVES.map((k) => B[k]);
const selo = el("selo", { attrs: { "data-mod": "conf" } });
const navEl = el("nav");
const pa = el("pa");
pa.querySelectorAll = () => botoes;
const ESQUERDA = { vg: 10, vs: 200, clas: 380, gl: 560, ds: 760, jg: 960, fin: 1160, conf: 1750 };
for (const k of CHAVES) B[k].getBoundingClientRect = () => ({ left: ESQUERDA[k], bottom: 74 });
pa.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1920, height: 1080 });
const tipEl = el("pa-tip");
tipEl.innerHTML = "";
tipEl.style = {};
tipEl.offsetWidth = 320;
const barraEl = el("barra");
pa.querySelector = (sel) => (sel === ".barra" ? barraEl : navEl);
const clicar = (alvo, dentroDaNav) => {
  const ev = { target: alvo };
  if (dentroDaNav && navEl.ouvintes.click) navEl.ouvintes.click(ev);
  if (barraEl.ouvintes.click) barraEl.ouvintes.click(ev);
};
const mods = {};
for (const k of CHAVES) mods["mod-" + k] = el("mod-" + k, { classe: k === "vg" ? "mod on" : "mod" });
const timers = new Map();
let seq = 0;
const rodarTimers = () => {
  for (const [id, fn] of [...timers]) {
    timers.delete(id);
    fn();
  }
};
const ctx = { document: { getElementById: (id) => (id === "pa" ? pa : id === "pa-tip" ? tipEl : mods[id]) }, location: { hash: process.argv[3] || "" }, setTimeout: (fn) => { timers.set(++seq, fn); return seq; }, clearTimeout: (id) => timers.delete(id), console };
ctx.window = ctx;
vm.createContext(ctx);
let entrou = 0;
vm.runInContext(cabeca, ctx);
for (const k of ["vg", "clas", "gl", "ds", "jg", "fin", "conf"]) ctx.window.PA.mods[k] = { entrar: () => entrou++ };
vm.runInContext(navegacao, ctx);
rodarTimers();

const estado = () => {
  const e = { corrente: botoes.map((b) => b.attrs["aria-current"] || null), entrou };
  for (const k of CHAVES) {
    e[k] = mods["mod-" + k].classes.has("on");
    e["b" + k] = B[k].classes.has("on");
  }
  return e;
};
const saida = { inicio: estado(), flag: ctx.window.PA.shell === true, temIr: typeof ctx.window.PA.ir };
clicar(B.fin, true);
saida.aposFin = estado();
clicar(B.vs, true);
saida.aposVs = estado();
ctx.window.PA.ir("inexistente");
saida.aposInvalido = estado();
ctx.window.PA.ir("fin");
saida.aposIrFin = estado();
clicar(B.clas, true);
saida.aposClas = estado();
clicar(B.conf, true);
saida.aposConf = estado();
clicar(B.gl, true);
saida.aposGl = estado();
clicar(B.ds, true);
saida.aposDs = estado();
clicar(B.jg, true);
saida.aposJg = estado();
clicar(B.vg, true);
saida.aposVg = estado();
clicar(B.vs, true);
clicar(selo, false);
saida.aposSelo = estado();
ctx.window.PA.ir("vs");
ctx.window.PA.ir("clas");
saida.aposIrClas = estado();
ctx.window.PA.ir("vg");
saida.aposIrVg = estado();
const fundoDaNav = { closest: () => null };
const ligada = () => tipEl.classes.has("on");
saida.dicas = {};
for (const k of CHAVES) {
  navEl.ouvintes.mouseover({ target: B[k] });
  const antesDoAtraso = ligada();
  rodarTimers();
  saida.dicas[k] = { antesDoAtraso, html: tipEl.innerHTML, ligada: ligada(), left: tipEl.style.left, top: tipEl.style.top };
  navEl.ouvintes.mouseleave();
  saida.dicas[k].aposSair = ligada();
}
navEl.ouvintes.mouseover({ target: B.vg });
navEl.ouvintes.mouseover({ target: B.vs });
rodarTimers();
saida.trocaRapida = tipEl.innerHTML;
navEl.ouvintes.mouseover({ target: fundoDaNav });
saida.fundo = ligada();
navEl.ouvintes.focusin({ target: B.jg });
saida.foco = { ligada: ligada(), html: tipEl.innerHTML };
navEl.ouvintes.focusout({});
saida.focoFora = ligada();
navEl.ouvintes.focusin({ target: B.fin });
navEl.ouvintes.click({ target: B.fin });
saida.aposClique = ligada();
navEl.ouvintes.mouseover({ target: B.gl });
navEl.ouvintes.click({ target: B.gl });
rodarTimers();
saida.cliqueAntesDoAtraso = ligada();
console.log(JSON.stringify(saida));
