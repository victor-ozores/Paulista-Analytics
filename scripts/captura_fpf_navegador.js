(async () => {
  const CFG = Object.assign({
    idCampeonato: 73,
    ano: 2026,
    idCategoria: 39,
    prefixo: 'fpf_a1_2026',
    baixar: true,
    pausaMs: 400,
    maxRodadas: 60
  }, window.__CFG_OVERRIDE || {});

  if (!location.hostname.endsWith('futebolpaulista.com.br')) {
    console.error('Abra uma pagina de futebolpaulista.com.br antes de colar este script.');
    return;
  }

  const B = '/Handlers/Competicoes/';
  const dorme = ms => new Promise(r => setTimeout(r, ms));
  const pega = async p => {
    const r = await fetch(B + p + '&_=' + Date.now());
    const tipo = r.headers.get('content-type') || '';
    if (!r.ok || tipo.indexOf('json') < 0 && tipo.indexOf('text/plain') < 0) {
      throw new Error('Resposta inesperada do portal (HTTP ' + r.status + '). Possivel bloqueio anti-robo; tente de novo depois, manualmente, em uma aba normal.');
    }
    const j = await r.json();
    await dorme(CFG.pausaMs);
    return j.Retorno;
  };
  const limpa = v => String(v == null ? '' : v).replace(/[;\r\n]/g, ' ').trim();
  const idClube = u => { const m = /CLUBE\/(\d+)\//.exec(u || ''); return m ? m[1] : ''; };
  const fnv = s => {
    let h = 0x811c9dc5;
    for (const b of new TextEncoder().encode(s)) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
    return h.toString(16).padStart(8, '0');
  };
  const baixar = (nome, texto) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' }));
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const fases = await pega(`ListarClassificacaoFases.ashx?idCampeonato=${CFG.idCampeonato}&exercicio=${CFG.ano}&idCategoria=${CFG.idCategoria}`);
  console.log('Fases:', fases.map(f => `${f.idCampeonatoFase} ${f.NomeFase}`).join(' | '));
  const csvFases = ['id_fase;nome_fase;ordem'].concat(fases.map(f => [f.idCampeonatoFase, f.NomeFase, f.Ordem].map(limpa).join(';'))).join('\n') + '\n';

  const jogos = [];
  let vazias = 0;
  for (let r = 1; r <= CFG.maxRodadas; r++) {
    const ret = await pega(`ListarTabela.ashx?IdCampeonato=${CFG.idCampeonato}&Ano=${CFG.ano}&Rodada=${r}`);
    const lista = (ret && ret.listTabela) || [];
    if (!lista.length) {
      vazias++;
      if (vazias >= 2 && jogos.length) break;
      continue;
    }
    vazias = 0;
    lista.forEach(x => jogos.push([x.IdJogo, x.Numero, x.Rodada, x.Fase, x.Grupo, x.Data, x.Horario, idClube(x.EscudoMandante), x.NomePopularMandante, x.ResultadoMandante, idClube(x.EscudoVisitante), x.NomePopularVisitante, x.ResultadoVisitante, x.Estadio, x.Municipio, x.Adiado ? 1 : 0]));
  }
  jogos.sort((a, b) => a[1] - b[1]);
  const csvJogos = ['id_jogo;numero;rodada;fase;grupo;data;horario;id_clube_mandante;mandante;gols_mandante;id_clube_visitante;visitante;gols_visitante;estadio;municipio;adiado']
    .concat(jogos.map(l => l.map(limpa).join(';'))).join('\n') + '\n';

  const cls = ['fase;grupo;pos;id_clube;clube;nome_oficial;pontos;jogos;vitorias;empates;derrotas;gols_pro;gols_contra;saldo;vp;dp;amarelos;vermelhos;faltas;atualizado'];
  for (const f of fases) {
    const rows = await pega(`ListarClassificacaoTabela.ashx?IdCampeonato=${CFG.idCampeonato}&IdCampeonatoFase=${f.idCampeonatoFase}&exercicio=${CFG.ano}&idCategoria=${CFG.idCategoria}`);
    const arr = Array.isArray(rows) ? rows : Object.values(rows || {});
    arr.forEach(c => cls.push([c.NomeFase, c.NomeGrupo, c.Classificacao, c.IdClube, c.NomePopularClube, c.NomeOficialClube, c.Pontos, c.Jogados, c.Vitorias, c.Empates, c.Derrota, c.GolsPro, c.GolsContra, c.SaldoGols, c.VitoriasPenaltis, c.DerrotasPenaltis, c.CartoesAmarelos, c.CartoesVermelhos, c.TotalFaltas, c.UltimaSincronizacao].map(limpa).join(';')));
  }
  const csvClass = cls.join('\n') + '\n';

  console.log(`Jogos: ${jogos.length} | hash ${fnv(csvJogos)} | ${new TextEncoder().encode(csvJogos).length} bytes`);
  console.log(`Classificacao: ${cls.length - 1} linhas | hash ${fnv(csvClass)} | ${new TextEncoder().encode(csvClass).length} bytes`);
  console.log(`Fases: ${fases.length} linhas | hash ${fnv(csvFases)}`);
  if (CFG.baixar) {
    baixar(`${CFG.prefixo}_jogos.csv`, csvJogos);
    await dorme(600);
    baixar(`${CFG.prefixo}_classificacao.csv`, csvClass);
    await dorme(600);
    baixar(`${CFG.prefixo}_fases.csv`, csvFases);
    console.log('3 arquivos baixados. Mova para data/referencia/ do projeto.');
  }
  return { jogos: csvJogos, classificacao: csvClass, fases: csvFases };
})();
