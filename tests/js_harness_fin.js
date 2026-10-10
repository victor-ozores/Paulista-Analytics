const vm = require("vm");
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
const casos = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
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

const raiz = new Fake("fnx");
const doc = new Fake("document");
doc.getElementById = () => raiz;
doc.createElement = () => new Fake("criado");
const timers = [];
const ctx = {
  document: doc,
  location: { search: "?debug" },
  performance: { now: () => 0 },
  requestAnimationFrame() {},
  setTimeout: (fn) => {
    timers.push(fn);
    return timers.length;
  },
  clearTimeout() {},
  navigator: {},
  matchMedia: () => ({ matches: false }),
  console,
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
for (const s of scripts) vm.runInContext(s, ctx);

const F = ctx.__fnx;
if (!F) {
  console.log(JSON.stringify({ semGancho: true }));
  process.exit(0);
}
const EL = raiz.filhos;
const painel = (n) => EL[".p" + n].innerHTML;
const ruins = (t) => /NaN|undefined|Infinity|\[object/.test(t);
const fdOn = () => EL[".fd"].classes.has("on");
const acoesVistas = new Set();
const coletarAcoes = (html) => {
  for (const m of html.matchAll(/data-act="([^"]+)"/g)) acoesVistas.add(m[1]);
};
const semTags = (t) => t.replace(/<[^>]*>/g, "");
const decod = (s) => s.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const atributo = (tag, k) => {
  const m = new RegExp(" " + k + '="([^"]*)"').exec(tag);
  return m ? decod(m[1]) : null;
};
const botoes = (html) => html.match(/<button[^>]*>/g) || [];
const achar = (html, act, v, id) => botoes(html).find((t) => atributo(t, "data-act") === act && (v === undefined || atributo(t, "data-v") === String(v)) && (id === undefined || atributo(t, "data-id") === String(id)));
function clicar(tag, dentroDaJanela) {
  const alvo = { getAttribute: (k) => atributo(tag, k), closest: (sel) => (sel === "[data-act]" && tag ? alvo : sel === ".cx" && tag && dentroDaJanela ? alvo : null) };
  for (const fn of raiz.ouvintes.click || []) fn({ target: alvo });
}

function resumo(a) {
  return {
    n: a.n, pu: a.pu, pg: a.pg, rb: a.rb, ds: a.ds, rl: a.rl, dd: a.dd, lq: a.lq, vi: a.vi, vr: a.vr, neg: a.neg, pmax: a.pmax, pmin: a.pmin, ci: a.ci, cr: a.cr, gd: a.gd, bd: a.bd,
    ru: Object.keys(a.ru).length ? Object.entries(a.ru).map(([k, v]) => [Number(k), v]).sort((x, y) => x[0] - y[0]) : [],
  };
}

function padrao(f) {
  F.aplicar(f);
  Object.assign(F.est, { rank: f.rank || "pub", metrica: f.metrica || "ing", ord: f.ord || "d", dir: f.dir || 1 });
}

function painelInfo() {
  F.atualizar({ semAnimar: true });
  const ps = [1, 2, 3, 4, 5].map(painel);
  const kp = EL[".kpis"].innerHTML;
  [...ps, kp, EL[".ctl"].innerHTML].forEach(coletarAcoes);
  const ctl = EL[".ctl"].innerHTML;
  return {
    kpiTextos: [...kp.matchAll(/<h4>([^<]*)<\/h4><div class="v">([\s\S]*?)<\/div><small>/g)].map((m) => [m[1], semTags(m[2])]),
    centro: (/<div class="cn">([\s\S]*?)<\/div>/.exec(ps[0]) || ["", ""])[1],
    filtrosN: Number((/<b>Filtros<\/b><small>(\d+) ligad/.exec(ctl) || [0, 0])[1]),
    filtrosLegenda: (/<b>Filtros<\/b><small>([^<]*)<\/small>/.exec(ctl) || ["", ""])[1],
    filtrosAtivo: ctl.indexOf('class="bfil ativo"') >= 0,
    comoApagado: ctl.indexOf('class="lin sem"') >= 0,
    botoesDoCabecalho: { fase: (ctl.match(/data-act="fase"/g) || []).length, como: (ctl.match(/data-act="como"/g) || []).length, filtros: (ctl.match(/data-act="filtros"/g) || []).length, limpar: (ctl.match(/data-act="limpar"/g) || []).length, ajuda: (ctl.match(/data-act="ajuda"/g) || []).length },
    ruim: ps.some(ruins) || ruins(kp) || ruins(EL[".sub"].textContent) || ruins(EL[".ctl"].innerHTML),
    legenda: (ps[0].match(/class="l( zero)?"/g) || []).length,
    fatias: (ps[0].match(/<circle/g) || []).length,
    barras: (ps[1].match(/<rect class="br/g) || []).length,
    grupos: (ps[2].match(/class="g"/g) || []).length,
    blocos: (ps[2].match(/<u style="background/g) || []).length,
    clubes: (ps[3].match(/<button class="r[ "]/g) || []).length,
    selecionados: (ps[3].match(/<button class="r sel/g) || []).length,
    jogosLinhas: (ps[4].match(/class="jr/g) || []).length,
    jogosSel: (ps[4].match(/class="jr sel/g) || []).length,
    vazio: ps.some((p) => p.indexOf('class="vazio"') >= 0),
    kpis: (kp.match(/class="kpi"/g) || []).length,
    tips: ps.concat([kp]).map((p) => (p.match(/data-tip="/g) || []).length).reduce((x, y) => x + y, 0),
    sub: EL[".sub"].textContent,
    subTip: EL[".sub"].attrs["data-tip"],
    limparVisivel: EL[".ctl"].innerHTML.indexOf("lim off") < 0,
    tituloRanking: (/<h3><span[^>]*>([^<]*)<\/span>/.exec(ps[3]) || ["", ""])[1],
    classeRanking: (/<div class="rk ([^"]*)">/.exec(ps[3]) || ["", ""])[1],
    comoOn: (/class="chp on[^"]*" data-act="como" data-v="(\w+)"/.exec(EL[".ctl"].innerHTML) || [0, null])[1],
  };
}

function dialogoInfo() {
  const d = F.dialogo();
  coletarAcoes(d);
  const on = (re) => (d.match(re) || []).length;
  return {
    resumo: [...d.matchAll(/<div style="--kc:[^"]*"><h4>([^<]*)<\/h4><b>([\s\S]*?)<\/b><\/div>/g)].map((m) => [m[1], semTags(m[2])]),
    aviso: d.indexOf('class="av"') >= 0,
    cabecalhoFixo: d.indexOf('class="hd"') >= 0 && d.indexOf('class="corpo"') >= 0,
    ruim: ruins(d),
    clubes: on(/<button class="cb/g),
    clubesOn: on(/<button class="cb on/g),
    clubesOff: on(/<button class="cb[^"]* off/g),
    rod: on(/data-act="f-rod"/g),
    rodOn: on(/class="chp on[^"]*" data-act="f-rod"/g),
    dia: on(/data-act="f-dia"/g),
    diaOn: on(/class="chp on[^"]*" data-act="f-dia"/g),
    hora: on(/data-act="f-hora"/g),
    horaOn: on(/class="chp on[^"]*" data-act="f-hora"/g),
    est: on(/data-act="f-est"/g),
    estOn: on(/class="chp on[^"]*" data-act="f-est"/g),
    res: on(/data-act="f-res"/g),
    resOn: (/class="chp on[^"]*" data-act="f-res" data-v="(\d)"/.exec(d) || [0, null])[1],
    comoOn: (/class="chp on[^"]*" data-act="como" data-v="(\w+)"/.exec(d) || [0, null])[1],
    titulo: (/<h2>Filtros<small>([^<]*)<\/small>/.exec(d) || ["", ""])[1],
  };
}

const saida = { combos: [], render: [], jogos: [], ordem: [], acoes: [], kpi: {}, tecla: [], cascata: [], cores: {}, meta: { jogos: F.D.jogos.length, clubes: F.D.clubes.length, cat: F.D.cat.map((c) => c.n), grp: F.D.grp.map((g) => g.n), rub: F.D.rub.map((r) => r[0]), estadios: F.OPC.est.map((o) => o.v) } };

for (const f of casos.combos) {
  padrao(f);
  const js = F.filtrar();
  const a = F.somar(js);
  const rk = F.porClube().map((r) => ({ id: r.c.id, n: r.n, pu: r.pu, rb: r.rb, rl: r.rl, pg: r.pg, vi: r.vi }));
  saida.combos.push({ filtros: f, ids: js.map((j) => j.i), ...resumo(a), rk, info: painelInfo(), dialogo: dialogoInfo(), nFiltros: F.nFiltros(), temFiltro: F.temFiltro() });
}

for (const r of casos.render) {
  padrao(r.filtros);
  F.atualizar({ semAnimar: true });
  const a = F.somar(F.filtrar());
  saida.render.push({ nome: r.nome, filtros: r.filtros, n: a.n, kpis: EL[".kpis"].innerHTML, p1: painel(1), p2: painel(2), p3: painel(3), p4: painel(4), p5: painel(5), sub: EL[".sub"].textContent, ctl: EL[".ctl"].innerHTML });
}

for (const j of F.D.jogos) {
  padrao({ jogo: j.i });
  const a = F.somar(F.filtrar());
  saida.jogos.push({ jogo: j.i, ...resumo(a), info: painelInfo(), dialogo: dialogoInfo() });
}

saida.jogosRenda = [];
for (const j of F.D.jogos) {
  padrao({ jogo: j.i, metrica: "ren" });
  const a = F.somar(F.filtrar());
  saida.jogosRenda.push({ jogo: j.i, n: a.n, rb: a.rb, info: painelInfo() });
}

padrao({});
for (const ord of Object.keys(F.OR))
  for (const dir of [1, -1]) {
    Object.assign(F.est, { ord, dir });
    saida.ordem.push({ ord, dir, ids: F.jogosOrdenados().map((j) => j.i), valores: F.jogosOrdenados().map((j) => (ord === "d" ? j.d + " " + j.h : j[ord])) });
  }
padrao({});

const estado = () => ({ fase: F.est.fase, clubes: F.est.clubes.slice(), como: F.est.como, rodadas: F.est.rodadas.slice(), estadios: F.est.estadios.slice(), dias: F.est.dias.slice(), horas: F.est.horas.slice(), res: F.est.res, jogo: F.est.jogo, metrica: F.est.metrica, rank: F.est.rank, ord: F.est.ord, dir: F.est.dir, n: F.filtrar().length, dialogo: fdOn(), nFiltros: F.nFiltros(), temFiltro: F.temFiltro() });
const idc = (curto) => F.D.clubes.find((c) => c.curto === curto).id;
const cor = idc("Corinthians"), pal = idc("Palmeiras"), san = idc("Santos"), cap = idc("Capivariano");
const jogo1 = F.D.jogos[0].i;
const jogoCor = F.D.jogos.find((j) => j.m === cor).i;
const passos = [
  ["clube", cor], ["clube", pal], ["clube", cor], ["clube", cor], ["clube", san], ["como", null, "v"], ["como", null, "mv"], ["como", null, "m"],
  ["jogo", jogoCor], ["jogo", jogoCor], ["jogo", jogoCor], ["clube", pal], ["limpar"],
  ["fase", null, "2"], ["clube", cap], ["fase", null, "0"], ["clube", cap], ["limpar"],
  ["f-rod", null, "9"], ["f-rod", null, "10"], ["f-rod", null, "9"], ["f-dia", null, "7"], ["f-dia", null, "6"], ["f-hora", null, "20:30"], ["f-est", null, F.OPC.est[0].v], ["f-res", null, "1"], ["f-res", null, "0"], ["f-limpar"],
  ["f-res", null, "1"], ["jogo", jogo1], ["f-res", null, "2"], ["limpar"],
  ["metrica", null, "ren"], ["rank", null, "vis"], ["ord", null, "pu"], ["ord", null, "pu"], ["ord", null, "d"],
];
const jg3 = F.D.jogos[3];
passos.push(
  ["jogo", jg3.i], ["fase", null, String(jg3.f === 1 ? 1 : 2)],
  ["jogo", jg3.i], ["f-rod", null, String(jg3.r)],
  ["jogo", jg3.i], ["f-dia", null, String(jg3.dw)],
  ["jogo", jg3.i], ["f-hora", null, jg3.h],
  ["jogo", jg3.i], ["f-est", null, jg3.e],
  ["jogo", jg3.i], ["f-res", null, jg3.rl < 0 ? "1" : "2"],
  ["limpar"],
  ["clube", jg3.m], ["jogo", jg3.i], ["como", null, "mv"], ["limpar"],
  ["jogo", jg3.i], ["como", null, "v"], ["como", null, "m"], ["limpar"],
);
saida.passosLibera = { primeiro: passos.length - 21, jogo: jg3.i };
for (const [a, id, v] of passos) {
  F.acao(a, id === undefined ? null : id, v === undefined ? null : v);
  saida.acoes.push({ passo: [a, id || null, v || null], estado: estado() });
}
F.acao("limpar", null, null);
F.acao("metrica", null, "ing");
F.acao("rank", null, "pub");
F.acao("como", null, "m");
Object.assign(F.est, { ord: "d", dir: 1 });

padrao({});
F.acao("filtros", null, null);
saida.tecla.push({ abriuFiltros: fdOn(), conteudo: EL[".fd"].innerHTML.indexOf("<h2>Filtros") >= 0 });
saida.tecla.push({ outraTecla: F.tecla("x", false), aindaAberto: fdOn() });
saida.tecla.push({ escape: F.tecla("Escape", false), fechado: !fdOn() });
padrao({ clubes: [cor, pal], jogo: jogoCor });
saida.tecla.push({ antes: estado(), tratou: F.tecla("Escape", false), depois: estado() });
saida.tecla.push({ antes: estado(), tratou: F.tecla("Backspace", false), depois: estado() });
saida.tecla.push({ antes: estado(), tratou: F.tecla("Escape", false), depois: estado() });
const ajudaAbrir = F.tecla("?", false);
const ajudaAberta = EL[".aj"].classes.has("on");
const fecharComEscape = F.tecla("Escape", false);
saida.tecla.push({ abrir: ajudaAbrir, aberta: ajudaAberta, fechou: fecharComEscape, fechada: !EL[".aj"].classes.has("on"), hcomCtrl: F.tecla("h", true) });
F.acao("filtros", null, null);
saida.tecla.push({ qAbertoComFiltros: F.tecla("?", false), ajudaFechada: !EL[".aj"].classes.has("on") });
F.acao("f-fechar", null, null);
padrao({});

for (const [nome, f] of [["todos", {}], ["corinthians", { clubes: [cor] }], ["corinthians e palmeiras", { clubes: [cor, pal] }], ["jogo1", { jogo: jogo1 }], ["vazio", { fase: 2, clubes: [cap] }]]) {
  padrao(f);
  const a = F.somar(F.filtrar());
  saida.kpi[nome] = { html: F.kpisHtml(a), sub: F.descricao(), fmt: F.KP.map((k) => { const x = F.fmtKpi(k, k.v(a)); return [k.k, x.f(x.n), x.pre, x.suf, F.corKpi(k, a)]; }) };
  saida.cascata.push({ nome, itens: F.cascataItens(a).map((i) => ({ n: i.n, v: i.v, de: i.de, ate: i.ate, tipo: i.tipo, cor: i.cor })) });
}
padrao({});

saida.cores = { kpiPadrao: F.KP.map((k) => [k.k, k.c]), cat: F.D.cat.map((c) => [c.n, c.c]) };
saida.descricoes = [
  {},
  { fase: 1 },
  { clubes: [cor] },
  { clubes: [cor, pal] },
  { clubes: [cor, pal, san] },
  { clubes: [cor, pal, san, cap] },
  { clubes: [cor], como: "v" },
  { clubes: [cor, pal], como: "mv" },
  { rodadas: [1, 2, 9] },
  { rodadas: [3] },
  { dias: [6, 7] },
  { horas: ["20:30"] },
  { horas: ["16:00", "20:30"] },
  { horas: ["15:00", "16:00", "17:00", "18:15"] },
  { estadios: [F.OPC.est[0].v] },
  { estadios: [F.OPC.est[0].v, F.OPC.est[1].v] },
  { res: 1 },
  { res: 2, fase: 2 },
  { jogo: jogo1 },
].map((f) => { padrao(f); return { filtros: f, texto: F.descricao(), n: F.filtrar().length }; });
padrao({});

saida.cliques = [];
{
  padrao({});
  F.atualizar({ semAnimar: true });
  const snap = () => { const e = estado(); return { fase: e.fase, clubes: e.clubes, como: e.como, rodadas: e.rodadas, estadios: e.estadios, dias: e.dias, horas: e.horas, res: e.res, jogo: e.jogo, n: e.n, dialogo: e.dialogo }; };
  const rotuloDe = (tag) => {
    if (!tag) return null;
    const html = [EL[".ctl"].innerHTML, EL[".fd"].innerHTML, painel(1), painel(4), painel(5)].find((h) => h.indexOf(tag) >= 0);
    if (!html) return null;
    const i = html.indexOf(tag);
    return semTags(decod(html.slice(i, html.indexOf("</button>", i))));
  };
  const reg = (rot, tag, dentro) => {
    const antes = snap();
    const rotulo = rotuloDe(tag);
    clicar(tag, dentro);
    saida.cliques.push({ rot, act: tag ? atributo(tag, "data-act") : null, v: tag ? atributo(tag, "data-v") : null, id: tag ? atributo(tag, "data-id") : null, rotulo, antes, depois: snap() });
  };
  const ctl = () => EL[".ctl"].innerHTML;
  const fd = () => EL[".fd"].innerHTML;
  for (const v of [1, 2, 0]) reg("fase " + v, achar(ctl(), "fase", v), false);
  reg("abre filtros", achar(ctl(), "filtros"), false);
  for (const act of ["f-rod", "f-dia", "f-hora", "f-est"]) {
    const valores = botoes(fd()).filter((t) => atributo(t, "data-act") === act).map((t) => atributo(t, "data-v"));
    for (const v of valores) {
      reg(act + " " + v + " liga", achar(fd(), act, v), true);
      reg(act + " " + v + " desliga", achar(fd(), act, v), true);
    }
  }
  for (const v of [1, 2, 0]) reg("f-res " + v, achar(fd(), "f-res", v), true);
  const ids = botoes(fd()).filter((t) => atributo(t, "data-act") === "clube" && !/ off/.test(atributo(t, "class") || "")).map((t) => atributo(t, "data-id"));
  for (const id of ids) {
    reg("clube " + id + " liga", achar(fd(), "clube", undefined, id), true);
    reg("clube " + id + " desliga", achar(fd(), "clube", undefined, id), true);
  }
  reg("clube liga p/ como", achar(fd(), "clube", undefined, ids[0]), true);
  for (const v of ["v", "mv", "m"]) reg("como " + v + " na janela", achar(fd(), "como", v), true);
  reg("clube desliga p/ como", achar(fd(), "clube", undefined, ids[0]), true);
  reg("clique fora da janela", null, false);
  reg("ranking liga", achar(EL[".p4"].innerHTML, "clube", undefined, ids[1]), false);
  reg("ranking liga 2", achar(EL[".p4"].innerHTML, "clube", undefined, ids[2]), false);
  reg("ranking desliga", achar(EL[".p4"].innerHTML, "clube", undefined, ids[1]), false);
  reg("limpar do cabeçalho", achar(ctl(), "limpar"), false);
  const idJogo = atributo(botoes(EL[".p5"].innerHTML).find((t) => atributo(t, "data-act") === "jogo"), "data-id");
  reg("jogo liga", achar(EL[".p5"].innerHTML, "jogo", undefined, idJogo), false);
  reg("jogo desliga", achar(EL[".p5"].innerHTML, "jogo", undefined, idJogo), false);
  reg("filtros de novo", achar(ctl(), "filtros"), false);
  reg("limpar tudo da janela", achar(fd(), "f-limpar"), true);
  reg("pronto fecha", achar(fd(), "f-fechar"), true);
  for (const v of ["ren", "ing"]) reg("rosca " + v, achar(painel(1), "metrica", v), false);
  for (const v of ["ren", "liq", "vis", "pub"]) reg("ranking medida " + v, achar(painel(4), "rank", v), false);
  for (const v of ["pu", "pu", "d"]) reg("lista ordem " + v, achar(painel(5), "ord", v), false);
  padrao({});
}
saida.acoesVistas = [...acoesVistas].sort();

saida.tipHtml = { completo: F.tipHtml("Título||@*A::1\nB::2||Parágrafo||~Nota"), escapado: F.tipHtml('<b>x</b> & "y"') };
saida.mi = [0, 99, 100, 99999, 100000, 123456, 9995000, 9994900, 10000000, 79012345, 99999999, 100000000, 4473000380, -5000, -1350380].map((v) => [v, F.mi(v), F.reais(v)]);
saida.descricao = F.descricao();
saida.opc = { rod: F.OPC.rod, dia: F.OPC.dia, hora: F.OPC.hora, est: F.OPC.est };
saida.papel = F.PAPEL;
console.log(JSON.stringify(saida));
