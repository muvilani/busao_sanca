"use strict";

(() => {
  const normalizar = valor => String(valor ?? "").normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

  const similaridade = (consulta, nome) => {
    if (!consulta || !nome) return 0;
    if (consulta === nome) return 1;
    if (nome.startsWith(consulta)) return .94;
    if (nome.includes(consulta)) return .88;
    const q = new Set(consulta.split(" ")), n = new Set(nome.split(" "));
    if ([...q].every(token => n.has(token))) return .84;
    const matriz = Array.from({length: consulta.length + 1}, (_, i) => [i]);
    for (let j = 1; j <= nome.length; j++) matriz[0][j] = j;
    for (let i = 1; i <= consulta.length; i++) for (let j = 1; j <= nome.length; j++) {
      matriz[i][j] = Math.min(
        matriz[i - 1][j] + 1,
        matriz[i][j - 1] + 1,
        matriz[i - 1][j - 1] + (consulta[i - 1] === nome[j - 1] ? 0 : 1),
      );
    }
    return 1 - matriz[consulta.length][nome.length] / Math.max(consulta.length, nome.length);
  };

  const chaveParada = (parada, fallback) => Number.isInteger(parada?.id_parada) && parada.id_parada > 0
    ? {chave: `id:${parada.id_parada}`, confiavel: true}
    : {chave: `ocorrencia:${fallback}`, confiavel: false};

  function segmentos(dataset) {
    const saida = [];
    for (const linha of dataset?.linhas || []) {
      if (!linha || typeof linha !== "object") continue;
      const catalogo = linha.catalogo || {};
      if (catalogo.codigo === "54" || linha.cobertura?.completa_no_escopo_solicitado === false) continue;
      const variantes = new Map((linha.horarios?.variantes || []).map(v => [v.id_viagem, v]));
      const direcoes = new Map((linha.horarios?.direcoes || []).map(d => [d.id_direcao, d]));
      for (const itinerario of linha.itinerarios || []) {
        const variante = variantes.get(itinerario.id_viagem), direcao = direcoes.get(variante?.id_direcao);
        const paradas = itinerario.paradas;
        if (!variante || !direcao || !Array.isArray(paradas) || paradas.length < 2) continue;
        if (paradas.some((parada, indice) => !Number.isInteger(parada?.ordem)
          || (indice > 0 && paradas[indice - 1].ordem >= parada.ordem)
          || !normalizar(parada.nome))) continue;
        saida.push({
          linha,
          catalogo,
          codigo: String(catalogo.codigo ?? ""),
          itinerario,
          variante,
          direcao,
          paradas: paradas.map((parada, indice) => ({
            ...chaveParada(parada, `${catalogo.codigo}:${itinerario.id_viagem}:${indice}`),
            chave_nome: normalizar(parada.nome),
            nome: parada.nome,
            parada,
            indice,
          })),
        });
      }
    }
    return saida;
  }

  function sugerir(dataset, consulta, limite = 8) {
    const q = normalizar(consulta), agrupados = new Map();
    for (const segmento of segmentos(dataset)) for (const registro of segmento.paradas) {
      const id = registro.parada.id_parada;
      const rotulo = registro.confiavel ? `${registro.nome} · parada ${id}` : registro.nome;
      if (!agrupados.has(registro.chave)) agrupados.set(registro.chave, {
        chave: registro.chave, nome: registro.nome, rotulo, id_parada: id, ocorrencias: 0,
      });
      agrupados.get(registro.chave).ocorrencias++;
    }
    return [...agrupados.values()].map(item => ({
      ...item,
      score: q ? Math.max(similaridade(q, normalizar(item.nome)), similaridade(q, normalizar(item.rotulo))) : .1,
    })).filter(item => !q || item.score >= .52)
      .sort((a, b) => b.score - a.score || b.ocorrencias - a.ocorrencias || normalizar(a.nome).localeCompare(normalizar(b.nome)))
      .slice(0, limite);
  }

  function resolver(dataset, valor) {
    const opcoes = sugerir(dataset, valor, 20), texto = String(valor ?? "").trim(), q = normalizar(texto);
    if (!texto) return {chaves: new Set(), opcoes};
    const exatas = opcoes.filter(item => item.chave === texto || normalizar(item.rotulo) === q || normalizar(item.nome) === q);
    if (exatas.length) return {chaves: new Set(exatas.map(item => item.chave)), opcoes};
    if (!opcoes.length || opcoes[0].score < .52) return {chaves: new Set(), opcoes};
    return {chaves: new Set(opcoes.filter(item => item.score >= opcoes[0].score - .12).map(item => item.chave)), opcoes};
  }

  function partidas(linha, tripId, data) {
    const saidas = [];
    for (const direcao of linha.horarios?.direcoes || []) for (const servico of direcao.servicos || []) {
      if (data && (data < servico.vigencia_inicio || data > servico.vigencia_fim)) continue;
      for (const partida of servico.partidas || []) if (partida.id_viagem === tripId) saidas.push({
        saida_terminal: partida.saida, id_servico: servico.id_servico,
        descricao_servico: servico.descricao, vigencia_inicio: servico.vigencia_inicio,
        vigencia_fim: servico.vigencia_fim, horario_passagem_confirmado: false,
      });
    }
    return [...new Map(saidas.map(item => [`${item.saida_terminal}|${item.id_servico}|${item.descricao_servico}`, item])).values()]
      .sort((a, b) => (a.saida_terminal || "").localeCompare(b.saida_terminal || ""));
  }

  function montarPerna(segmento, inicio, fim, data) {
    const embarque = segmento.paradas[inicio], desembarque = segmento.paradas[fim];
    const listaPartidas = partidas(segmento.linha, segmento.itinerario.id_viagem, data);
    const servicos = [...new Map(listaPartidas.map(item => [String(item.id_servico), {
      id_servico: item.id_servico, descricao: item.descricao_servico,
    }])).values()];
    return {
      codigo_linha: segmento.codigo, nome_linha: segmento.catalogo.nome,
      sentido: segmento.direcao.descricao, destino_variante: segmento.variante.destino,
      sequencia_variante: segmento.variante.sequencia ?? segmento.variante.sequencia_origem,
      embarque: embarque.parada, desembarque: desembarque.parada,
      chave_embarque: embarque.chave, chave_desembarque: desembarque.chave,
      id_viagem: segmento.itinerario.id_viagem,
      geometria_confirmada: segmento.itinerario.geometria?.validacao?.extremidades_compativeis !== false,
      paradas_intermediarias: Math.max(0, fim - inicio - 1), paradas_percorridas: fim - inicio,
      servicos, partidas: listaPartidas,
    };
  }

  function planejar(dataset, origem, destino, data, limite = 8) {
    const ro = resolver(dataset, origem), rd = resolver(dataset, destino);
    const base = {sugestoes: {origem: ro.opcoes, destino: rd.opcoes}, resultados: []};
    if (!ro.chaves.size || !rd.chaves.size) return {...base, status: "sem_rota", motivo: "Não encontrei paradas suficientemente semelhantes aos locais informados."};
    if ([...ro.chaves].some(chave => rd.chaves.has(chave))) return {...base, status: "origem_destino_iguais", motivo: "Origem e destino representam a mesma parada."};

    const trechos = segmentos(dataset), diretos = [], conexoes = [];
    for (const trecho of trechos) {
      const origens = trecho.paradas.filter(p => ro.chaves.has(p.chave));
      const destinos = trecho.paradas.filter(p => rd.chaves.has(p.chave));
      for (const o of origens) for (const d of destinos) if (o.indice < d.indice) {
        const perna = montarPerna(trecho, o.indice, d.indice, data);
        diretos.push({tipo: "direto", status: perna.geometria_confirmada ? "candidata" : "candidata_nao_verificada", conexoes: 0, ...perna});
      }
    }
    for (const primeiro of trechos) for (const o of primeiro.paradas.filter(p => ro.chaves.has(p.chave))) {
      for (const transferencia of primeiro.paradas.slice(o.indice + 1)) {
        if (!transferencia.confiavel || ro.chaves.has(transferencia.chave) || rd.chaves.has(transferencia.chave)) continue;
        for (const segundo of trechos) {
          if (segundo.itinerario.id_viagem === primeiro.itinerario.id_viagem) continue;
          const embarques = segundo.paradas.filter(p => p.confiavel && p.chave === transferencia.chave);
          const destinos = segundo.paradas.filter(p => rd.chaves.has(p.chave));
          for (const e of embarques) for (const d of destinos) if (e.indice < d.indice) {
            const p1 = montarPerna(primeiro, o.indice, transferencia.indice, data);
            const p2 = montarPerna(segundo, e.indice, d.indice, data);
            conexoes.push({
              tipo: "conexao", status: "candidata_nao_verificada", conexoes: 1,
              transferencia: transferencia.parada, paradas_ate_transferencia: p1.paradas_percorridas,
              paradas_percorridas: p1.paradas_percorridas + p2.paradas_percorridas,
              pernas: [p1, p2],
              aviso_conexao: "Conexão estrutural pelo mesmo identificador de parada; tempo de transferência, tarifa e espera não foram confirmados.",
            });
          }
        }
      }
    }
    const unicosDiretos = [...new Map(diretos.map(item => [`${item.id_viagem}|${item.chave_embarque}|${item.chave_desembarque}`, item])).values()];
    const unicasConexoes = [...new Map(conexoes.map(item => [[item.pernas[0].id_viagem, item.pernas[1].id_viagem, item.pernas[0].chave_embarque, item.transferencia.id_parada, item.pernas[1].chave_desembarque].join("|"), item])).values()];
    const encontrados = [...unicosDiretos, ...unicasConexoes].sort((a, b) => {
      const a1 = a.tipo === "conexao" ? a.pernas[0] : a, b1 = b.tipo === "conexao" ? b.pernas[0] : b;
      const a2 = a.tipo === "conexao" ? a.pernas[1] : {}, b2 = b.tipo === "conexao" ? b.pernas[1] : {};
      return a.conexoes - b.conexoes || a.paradas_percorridas - b.paradas_percorridas
        || a1.paradas_percorridas - b1.paradas_percorridas || a1.codigo_linha.localeCompare(b1.codigo_linha)
        || String(a1.sentido || "").localeCompare(String(b1.sentido || ""))
        || (a1.sequencia_variante || 0) - (b1.sequencia_variante || 0)
        || String(a2.codigo_linha || "").localeCompare(String(b2.codigo_linha || ""));
    }).slice(0, Math.max(0, limite));
    if (!encontrados.length) return {...base, status: "sem_rota", motivo: "Não encontrei uma sequência válida, direta ou com uma conexão confirmável, entre as paradas informadas."};
    return {...base, status: "sucesso", motivo: "", resultados: encontrados};
  }

  window.BusaoPlanner = {normalizar, sugerir, planejar};
})();
