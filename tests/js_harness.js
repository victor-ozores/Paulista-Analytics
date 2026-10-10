const vm = require("vm");
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
const bloco = /<script>([\s\S]*)<\/script>/.exec(html);
if (!bloco) throw new Error("sem <script>");

function stub(sobre) {
  const f = function () {};
  return new Proxy(f, {
    get(t, k) {
      if (sobre && Object.prototype.hasOwnProperty.call(sobre, k)) return sobre[k];
      if (k === Symbol.toPrimitive) return () => "";
      if (k === "then") return undefined;
      return stub();
    },
    set() {
      return true;
    },
    apply() {
      return stub();
    },
    construct() {
      return stub();
    },
  });
}

const raiz = stub({
  clientWidth: 1920,
  clientHeight: 1080,
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1920, height: 1080 }),
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
});
const ctx = {
  document: { getElementById: (id) => (id === "vsx" ? raiz : stub()), createElement: () => stub(), addEventListener() {} },
  location: { search: process.argv[3] === "sem-debug" ? "" : "?debug" },
  performance: { now: () => 0 },
  requestAnimationFrame() {},
  setTimeout: () => 0,
  clearTimeout() {},
  navigator: {},
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
vm.runInContext(bloco[1], ctx);

const V = ctx.__vsx;
if (!V) {
  console.log(JSON.stringify({ semGancho: true }));
  process.exit(0);
}
const saida = {};
const ids = V.D.clubes.map((c) => c.id);

saida.pares = [];
for (const a of ids)
  for (const b of ids) {
    if (a === b) continue;
    const A = V.CL[a], B = V.CL[b];
    const c = V.contagem(A, B), d = V.decisor(A, B), r = V.resumo(A, B);
    saida.pares.push({ a, b, ga: c.ga, gb: c.gb, emp: c.emp, tot: c.tot, dec: d ? { f: d.f.id, k: d.k } : null, criterios: r.criterios, fase1: r.fase1, confronto: r.confronto });
  }

saida.jornada = {};
for (const c of V.D.clubes) {
  const h = V.jornada(c);
  saida.jornada[c.id] = { letras: [...h.matchAll(/class="jc ([VED])"/g)].map((m) => m[1]).join(""), tips: (h.match(/data-tip=/g) || []).length };
}

saida.campo = {};
saida.layout = { jogos: 0, itens: 0, colide: 0, golsTotal: 0, golsSemTexto: 0, sobrepostos: [], foraDaFaixa: [] };
saida.times = { semEscudo: [], semFaixa: [], semNomeNoTooltip: 0, eventos: 0 };
saida.tips = { total: 0, vazios: 0, cartoesComMotivo: 0, cartoesComMotivoEsperado: 0, golsSemTexto: 0 };
for (const j of V.D.jogos) {
  const m = V.CL[j.m], v = V.CL[j.v];
  const svg = V.campo(j);
  const grupos = svg.split('<g class="mk-pop"').slice(1);
  let marcasM = 0, marcasV = 0;
  grupos.forEach((g) => {
    const n = +/data-n="(\d+)"/.exec(g)[1];
    const usaM = g.indexOf('href="#vxcm"') >= 0, usaV = g.indexOf('href="#vxcv"') >= 0;
    if (usaM && !usaV) marcasM += n;
    else if (usaV && !usaM) marcasV += n;
    else saida.times.semEscudo.push(j.n);
  });
  const esp = [0, 0];
  j.ev.filter((e) => e[3] !== null && e[2] !== 3).forEach((e) => esp[e[1]]++);
  saida.campo[j.i] = { marcasM, marcasV, esperadoM: esp[0], esperadoV: esp[1], grupos: grupos.length };
  if (svg.indexOf(m.curto + " · mandante") < 0 || svg.indexOf(v.curto + " · visitante") < 0 || svg.indexOf("Gols: " + j.gm) < 0 || svg.indexOf("Gols: " + j.gv) < 0) saida.times.semFaixa.push(j.n);

  const L = V.layoutCampo(j);
  saida.layout.jogos++;
  for (const it of L.itens) {
    saida.layout.itens++;
    if (it.colide) saida.layout.colide++;
    if (it.gol) {
      saida.layout.golsTotal++;
      if (!it.tx) saida.layout.golsSemTexto++;
    }
    const y0 = it.lado === 0 ? L.S : L.yB0, y1 = it.lado === 0 ? L.yA1 : L.yB0 + L.LH;
    for (const r of it.rs) if (r[0] < 0 || r[1] > L.W || r[2] < y0 || r[3] > y1) saida.layout.foraDaFaixa.push({ jogo: j.n, r });
  }
  for (let a = 0; a < L.itens.length; a++)
    for (let b = a + 1; b < L.itens.length; b++) {
      const A = L.itens[a], B = L.itens[b];
      if (A.lado !== B.lado) continue;
      for (const r of A.rs) for (const s of B.rs) if (r[0] < s[1] && r[1] > s[0] && r[2] < s[3] && r[3] > s[2]) saida.layout.sobrepostos.push({ jogo: j.n, a: A.e[3], b: B.e[3] });
    }

  for (const e of j.ev) {
    const t = V.tipEv(j, e);
    saida.tips.total++;
    saida.times.eventos++;
    if (!t || t.split("||").length < 2) saida.tips.vazios++;
    const nomeTime = (e[1] === 0 ? m : v).curto;
    if (t.indexOf("Time::" + nomeTime) < 0 && t.indexOf("Gol vale para::" + nomeTime) < 0) saida.times.semNomeNoTooltip++;
    if ("avs".indexOf(e[0]) >= 0 && e[7] >= 0) {
      saida.tips.cartoesComMotivoEsperado++;
      if (t.indexOf("Motivo: " + V.D.mot[e[7]]) >= 0) saida.tips.cartoesComMotivo++;
    }
    if ("gpfc".indexOf(e[0]) >= 0 && t.indexOf(e[5]) < 0) saida.tips.golsSemTexto++;
  }
}

saida.linhas = V.LIN.map((l) => l[0]);
saida.rotulos = V.LIN.map((l) => l[1]);
saida.compEstrutura = { linhas: 0, ok: 0, falhas: [], grupos: 0, gruposComTip: 0 };
for (const a of ids)
  for (const b of ids) {
    if (a === b) continue;
    const A = V.CL[a], B = V.CL[b];
    const h = V.comparativo(A, B);
    const dados = [...h.matchAll(/class="lin([^"]*)" data-tip="([^"]*)"/g)];
    saida.compEstrutura.grupos += (h.match(/class="gt"/g) || []).length;
    saida.compEstrutura.gruposComTip += (h.match(/class="gt"[^>]*data-tip=/g) || []).length;
    dados.forEach((m, i) => {
      saida.compEstrutura.linhas++;
      const sec = m[2].replace(/&quot;/g, '"').replace(/&amp;/g, "&").split("||");
      const linhas = sec[1] && sec[1][0] === "@" ? sec[1].slice(1).split("\n") : [];
      const dir = V.LIN[i][3], va = A[V.LIN[i][0]], vb = B[V.LIN[i][0]];
      const lideres = linhas.filter((l) => l[0] === "*").length;
      const esperado = dir !== 0 && va !== vb ? 1 : 0;
      const ok = sec.length === 4 && linhas.length === 2 && linhas[0].replace("*", "").indexOf(A.curto + "::") === 0 && linhas[1].replace("*", "").indexOf(B.curto + "::") === 0 && lideres === esperado && sec[3][0] === "~" && sec[0] === V.DEF[V.LIN[i][0]][0];
      if (ok) saida.compEstrutura.ok++;
      else if (saida.compEstrutura.falhas.length < 5) saida.compEstrutura.falhas.push({ par: A.curto + " x " + B.curto, linha: V.LIN[i][0], sec });
    });
  }

saida.tipHtml = {
  completo: V.tipHtml("Título||@*A::1\nB::2||Parágrafo||~Nota"),
  escapado: V.tipHtml("<b>x</b> & \"y\""),
};
saida.placar = { jogos: 0, falhas: [] };
for (const j of V.D.jogos) {
  const h = V.placarJogo(j), m = V.CL[j.m], v = V.CL[j.v];
  saida.placar.jogos++;
  const ok = h.indexOf(m.curto) >= 0 && h.indexOf(v.curto) >= 0 && h.indexOf("<b>" + j.gm + "</b>") >= 0 && h.indexOf("<b>" + j.gv + "</b>") >= 0 && h.indexOf("Árbitro::") >= 0 && h.indexOf("Público::") >= 0 && (j.pm === null || h.indexOf("Pênaltis::") >= 0);
  if (!ok && saida.placar.falhas.length < 5) saida.placar.falhas.push(j.n);
}

const erros = [];
try {
  for (let i = 0; i < ids.length; i++)
    for (let k = i + 1; k < ids.length; k++) {
      V.abrirVS(ids[i], ids[k], null);
      V.est.tab = "conf";
      V.mostrarTab(false);
      V.est.tab = "comp";
      V.mostrarTab(false);
    }
  for (const j of V.D.jogos) V.abrirVS(j.m, j.v, j.i);
  V.voltar();
  V.atualizarSel();
  V.est.aba = "jogos";
  V.est.filtro = 0;
  V.listaJogos();
  V.atalhos();
  V.filtros();
} catch (e) {
  erros.push(String(e && e.stack ? e.stack : e).slice(0, 600));
}
saida.listaDuelo = {};
for (const f of [0, 1, 2, 3, 4]) {
  V.est.filtro = f;
  saida.listaDuelo[f] = { filtros: V.filtros(), lista: V.listaJogos() };
}
V.est.filtro = 0;
saida.atalhosDuelo = V.atalhos();
saida.paineisSel = V.D.clubes.map((c) => ({ id: c.id, html: V.painelSel(c, "a", false) }));
saida.erros = erros;

const pal = V.D.clubes.find((c) => c.curto === "Palmeiras").id, nov = V.D.clubes.find((c) => c.curto === "Novorizontino").id;
const por = V.D.clubes.find((c) => c.curto === "Portuguesa").id, cor = V.D.clubes.find((c) => c.curto === "Corinthians").id;
saida.confrontoDireto = { palNov: V.confronto(V.CL[pal], V.CL[nov]), porCor: V.confronto(V.CL[por], V.CL[cor]) };
V.abrirVS(pal, nov, null);
V.est.tela = "vs";
V.pz.els = { ca: stub(), cb: stub(), foco: stub() };
V.pz.x = V.pz.y = V.pz.tx = V.pz.ty = V.pz.o = V.pz.to = 0;
V.pz.sig = "";
V.alvoPz({ clientX: 1920, clientY: 0 });
saida.alvoCanto = { tx: V.pz.tx, ty: V.pz.ty, to: V.pz.to };
const ida = [], idaO = [];
for (let i = 0; i < 120; i++) {
  V.tick(16);
  ida.push(V.pz.x);
  idaO.push(V.pz.o);
}
V.alvoPz({ clientX: 960, clientY: 900 });
saida.alvoPainel = { tx: V.pz.tx, ty: V.pz.ty, to: V.pz.to };
const volta = [], voltaO = [];
for (let i = 0; i < 200; i++) {
  V.tick(16);
  volta.push(V.pz.x);
  voltaO.push(V.pz.o);
}
saida.pzIda = ida;
saida.pzVolta = volta;
saida.pzIdaO = idaO;
saida.pzVoltaO = voltaO;
V.alvoPz({ clientX: 100, clientY: 270 });
saida.alvoEsquerda = { tx: V.pz.tx, ty: V.pz.ty, to: V.pz.to };

V.fx.P.length = 0;
V.passos(1500);
saida.brasas = V.fx.P.length;
saida.cfgBrasas = V.CFG.brasas;
console.log(JSON.stringify(saida));
