const vm = require("vm");
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (!scripts.length) throw new Error("sem <script>");

class Fake {
  constructor(nome) {
    this.nome = nome;
    this.innerHTML = "";
    this.textContent = "";
    this.style = {};
    this.scrollTop = 0;
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

const raiz = new Fake("cnx");
const doc = new Fake("document");
doc.getElementById = () => raiz;
doc.createElement = () => new Fake("criado");
const ctx = {
  document: doc,
  location: { search: "?debug" },
  performance: { now: () => 0 },
  requestAnimationFrame() {},
  setTimeout: () => 0,
  clearTimeout() {},
  navigator: {},
  matchMedia: () => ({ matches: false }),
  console,
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
for (const s of scripts) vm.runInContext(s, ctx);

const C = ctx.__cnx;
if (!C) {
  console.log(JSON.stringify({ semGancho: true }));
  process.exit(0);
}
const EL = raiz.filhos;
const ruins = (t) => /NaN|undefined|Infinity|\[object|null/.test(t);
const semTags = (t) => t.replace(/<[^>]*>/g, "");
const decod = (s) => s.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const atributo = (tag, k) => {
  const m = new RegExp(" " + k + '="([^"]*)"').exec(tag);
  return m ? decod(m[1]) : null;
};
const botoes = (h) => h.match(/<button[^>]*>/g) || [];
const achar = (h, act, v, id) => botoes(h).find((t) => atributo(t, "data-act") === act && (v === undefined || atributo(t, "data-v") === String(v)) && (id === undefined || atributo(t, "data-id") === String(id)));
function clicar(tag, dentroDaJanela) {
  const alvo = { getAttribute: (k) => atributo(tag, k), closest: (sel) => (sel === "[data-act]" && tag ? alvo : sel === ".cx" && tag && dentroDaJanela ? alvo : null) };
  for (const fn of raiz.ouvintes.click || []) fn({ target: alvo });
}
const ajudaAberta = () => EL[".aj"].classes.has("on");
const estado = () => ({ res: C.est.res, st: C.est.st, sel: C.est.sel });
const painel = (n) => EL[".p" + n].innerHTML;

function render(f) {
  C.est.res = f.res;
  C.est.st = f.st;
  C.est.sel = f.sel;
  C.atualizar({ semAnimar: true });
  const p1 = painel(1), p2 = painel(2), kp = EL[".kpis"].innerHTML;
  return {
    f,
    regras: C.regrasFiltradas().map((r) => r.c),
    ocorr: C.ocorrFiltradas().map((o) => o.i),
    contaRes: C.contaRes(),
    contaSt: C.contaSt(),
    linhasRegras: (p1.match(/<button class="rr[ "]/g) || []).length,
    linhasSel: (p1.match(/<button class="rr sel/g) || []).length,
    linhasOcorr: (p2.match(/<div class="oc[ "]/g) || []).length,
    abertasComTexto: (p2.match(/<div class="l3">/g) || []).length,
    vazio: p2.indexOf('class="vazio"') >= 0 ? semTags(decod(p2.slice(p2.indexOf('class="vazio"')))) : null,
    chipsRes: [...p1.matchAll(/class="chp sm( on)?" data-act="res" data-v="(\w+)"/g)].map((m) => [m[2], !!m[1]]),
    chipsSt: [...p2.matchAll(/class="chp sm( on)?" data-act="st" data-v="(\w+)"/g)].map((m) => [m[2], !!m[1]]),
    tituloP2: (/<h3><span[^>]*>[^<]*<\/span><small>([^<]*)<\/small>/.exec(p2) || ["", ""])[1],
    tituloP1: (/<h3><span[^>]*>[^<]*<\/span><small>([^<]*)<\/small>/.exec(p1) || ["", ""])[1],
    ruim: ruins(p1) || ruins(p2) || ruins(kp) || ruins(painel(3)) || ruins(painel(4)) || ruins(painel(5)) || ruins(EL[".ctl"].innerHTML),
    limparVisivel: EL[".ctl"].innerHTML.indexOf("lim off") < 0,
    temFiltro: C.temFiltro(),
  };
}

const saida = { combos: [], acoes: [], tecla: [], render: {}, cliques: [], meta: { regras: C.D.reg.length, ocorr: C.D.oc.length } };
const codigos = C.D.reg.map((r) => r.c);
for (const res of ["t", "ok", "explicada", "aberta", "info"])
  for (const st of ["t", "aberta", "explicada", "aceita", "corrigida"])
    for (const sel of [null, ...codigos]) saida.combos.push(render({ res, st, sel }));

C.limparTudo();
C.atualizar({ semAnimar: true });
const kp = EL[".kpis"].innerHTML;
saida.kpis = [...kp.matchAll(/<h4>([^<]*)<\/h4><div class="v"><span data-i="\d">([^<]*)<\/span>(?:<em>([^<]*)<\/em>)?<\/div><small>([^<]*)<\/small>/g)].map((m) => [decod(m[1]), m[2], m[3] ? decod(m[3]) : "", decod(m[4])]);
saida.kpiTips = [...kp.matchAll(/class="kpi"[^>]*data-tip="([^"]*)"/g)].length;
saida.render = {
  kpis: kp, p1: painel(1), p2: painel(2), p3: painel(3), p4: painel(4), p5: painel(5), ctl: EL[".ctl"].innerHTML, sub: EL[".sub"].textContent, subTip: EL[".sub"].attrs["data-tip"], rod: EL[".rod"].innerHTML, aj: EL[".aj"].innerHTML,
  fontes: (painel(3).match(/class="fo"/g) || []).length, camadas: (painel(4).match(/class="cm"/g) || []).length, correcoes: (painel(5).match(/class="cr"/g) || []).length,
};

const passos = [
  ["res", null, "aberta"], ["regra", "A32", null], ["regra", "A32", null], ["st", null, "aberta"], ["regra", "A12", null], ["st", null, "explicada"], ["regra", "A01", null], ["limpar"],
  ["regra", "A13", null], ["res", null, "ok"], ["st", null, "aceita"], ["limpar"], ["regra", "XXX", null], ["res", null, "info"], ["res", null, "t"],
  ["regra", "A12", null], ["res", null, "explicada"], ["res", null, "aberta"], ["res", null, "t"], ["regra", "A33", null], ["res", null, "t"], ["limpar"],
  ["res", null, "ok"], ["regra", "A01", null], ["st", null, "aberta"], ["res", null, "explicada"], ["regra", "A06", null], ["regra", "A12", null], ["limpar"],
];
for (const [a, id, v] of passos) {
  C.acao(a, id === null || id === undefined ? null : id, v === undefined ? null : v);
  saida.acoes.push({ passo: [a, id || null, v || null], estado: estado(), temFiltro: C.temFiltro() });
}
C.limparTudo();
C.atualizar({ semAnimar: true });

const vistas = new Set();
const coletar = (h) => { for (const m of h.matchAll(/data-act="([^"]+)"/g)) vistas.add(m[1]); };
const ctl = () => EL[".ctl"].innerHTML;
const snap = () => ({ ...estado(), ajuda: ajudaAberta() });
const reg = (rot, tag, dentro) => {
  const antes = snap();
  const html = [painel(1), painel(2), ctl(), EL[".aj"].innerHTML].find((h) => tag && h.indexOf(tag) >= 0);
  let rotulo = null;
  if (html) { const i = html.indexOf(tag); rotulo = semTags(decod(html.slice(i, html.indexOf("</button>", i)))); }
  clicar(tag, dentro);
  saida.cliques.push({ rot, act: tag ? atributo(tag, "data-act") : null, v: tag ? atributo(tag, "data-v") : null, id: tag ? atributo(tag, "data-id") : null, rotulo, antes, depois: snap() });
};
[painel(1), painel(2), ctl(), EL[".aj"].innerHTML].forEach(coletar);
for (const v of ["ok", "explicada", "aberta", "info", "t"]) reg("chip regras " + v, achar(painel(1), "res", v), false);
for (const c of ["A06", "A12", "A33", "A06"]) reg("regra " + c, achar(painel(1), "regra", undefined, c), false);
reg("regra A12 de novo", achar(painel(1), "regra", undefined, "A12"), false);
reg("chip regras explicada (mantem A12)", achar(painel(1), "res", "explicada"), false);
reg("chip regras aberta (solta A12)", achar(painel(1), "res", "aberta"), false);
reg("chip regras todas", achar(painel(1), "res", "t"), false);
for (const v of ["aberta", "explicada", "aceita", "corrigida", "t"]) reg("chip ocorr " + v, achar(painel(2), "st", v), false);
reg("regra A24", achar(painel(1), "regra", undefined, "A24"), false);
reg("limpar", achar(ctl(), "limpar"), false);
reg("abre ajuda", achar(ctl(), "ajuda"), false);
reg("clique fora da ajuda", null, false);
reg("abre ajuda de novo", achar(ctl(), "ajuda"), false);
reg("entendi", achar(EL[".aj"].innerHTML, "ajuda-fechar"), true);
saida.acoesVistas = [...vistas].sort();

C.limparTudo();
C.atualizar({ semAnimar: true });
const antes = (f) => { f(); return estado(); };
saida.tecla.push({ semFiltro: C.tecla("Escape", false), estado: estado() });
C.acao("regra", null, null);
C.acao("res", null, "aberta");
C.acao("regra", "A32", null);
saida.tecla.push({ antes: estado(), tratou: C.tecla("Escape", false), depois: estado() });
saida.tecla.push({ antes: estado(), tratou: C.tecla("Backspace", false), depois: estado() });
saida.tecla.push({ antes: estado(), tratou: C.tecla("Escape", false), depois: estado() });
const abrir = C.tecla("?", false), aberta = ajudaAberta(), fecharComEsc = C.tecla("Escape", false);
saida.tecla.push({ abrir, aberta, fechou: fecharComEsc, fechada: !ajudaAberta(), hComCtrl: C.tecla("h", true), outra: C.tecla("x", false) });
C.acao("regra", "A12", null);
C.tecla("h", false);
saida.tecla.push({ ajudaAbertaComFiltro: ajudaAberta(), escFechaSoAAjuda: C.tecla("Escape", false), selDepois: C.est.sel, fechada: !ajudaAberta() });
C.limparTudo();
C.atualizar({ semAnimar: true });

saida.tipHtml = { completo: C.tipHtml("Título||@A::1\nB::2||Parágrafo||~Nota"), escapado: C.tipHtml('<b>x</b> & "y"') };
console.log(JSON.stringify(saida));
