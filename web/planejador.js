"use strict";

(() => {
  const normalizar = valor => String(valor ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
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
      matriz[i][j] = Math.min(matriz[i - 1][j] + 1, matriz[i][j - 1] + 1, matriz[i - 1][j - 1] + (consulta[i - 1] === nome[j - 1] ? 0 : 1));
    }
    return 1 - matriz[consulta.length][nome.length] / Math.max(consulta.length, nome.length);
  };

  function registros(dataset) {
    const saida = [];
    for (const linha of dataset?.linhas || []) {
      const catalogo = linha.catalogo || {};
      if (catalogo.codigo === "54" || linha.cobertura?.completa_no_escopo_solicitado === false) continue;
      const variantes = new Map((linha.horarios?.variantes || []).map(v => [v.id_viagem, v]));
      const direcoes = new Map((linha.horarios?.direcoes || []).map(d => [d.id_direcao, d]));
      for (const itinerario of linha.itinerarios || []) {
        const variante = variantes.get(itinerario.id_viagem), direcao = direcoes.get(variante?.id_direcao);
        if (!variante || !direcao) continue;
        for (const parada of itinerario.paradas || []) {
          const chave = normalizar(parada.nome);
          if (chave) saida.push({chave, parada, linha, catalogo, itinerario, variante, direcao});
        }
      }
    }
    return saida;
  }

  function sugerir(dataset, consulta, limite = 8) {
    const q = normalizar(consulta), agrupados = new Map();
    for (const registro of registros(dataset)) {
      if (!agrupados.has(registro.chave)) agrupados.set(registro.chave, {nome: registro.parada.nome, ocorrencias: 0});
      agrupados.get(registro.chave).ocorrencias++;
    }
    return [...agrupados.entries()].map(([chave, item]) => ({...item, score: similaridade(q, chave)}))
      .filter(item => !q || item.score >= .52).sort((a, b) => b.score - a.score || b.ocorrencias - a.ocorrencias).slice(0, limite);
  }

  function partidas(linha, tripId, data) {
    const saidas = [];
    for (const direcao of linha.horarios?.direcoes || []) for (const servico of direcao.servicos || []) {
      if (data && (data < servico.vigencia_inicio || data > servico.vigencia_fim)) continue;
      for (const partida of servico.partidas || []) if (partida.id_viagem === tripId) saidas.push({saida_terminal: partida.saida, descricao_servico: servico.descricao, horario_passagem_confirmado: false});
    }
    return [...new Map(saidas.map(item => [`${item.saida_terminal}|${item.descricao_servico}`, item])).values()].sort((a, b) => (a.saida_terminal || "").localeCompare(b.saida_terminal || ""));
  }

  function planejar(dataset, origem, destino, data) {
    const so = sugerir(dataset, origem), sd = sugerir(dataset, destino);
    if (!so.length || !sd.length || so[0].score < .52 || sd[0].score < .52) return {status: "sem_rota", motivo: "Não encontrei paradas suficientemente semelhantes aos locais informados.", sugestoes: {origem: so, destino: sd}, resultados: []};
    const nomesO = new Set(so.filter(x => x.score >= so[0].score - .12).map(x => x.nome));
    const nomesD = new Set(sd.filter(x => x.score >= sd[0].score - .12).map(x => x.nome));
    const encontrados = [];
    for (const registro of registros(dataset)) {
      if (!nomesO.has(registro.parada.nome)) continue;
      for (const destinoRegistro of registros({linhas: [registro.linha]})) {
        if (destinoRegistro.itinerario.id_viagem !== registro.itinerario.id_viagem || !nomesD.has(destinoRegistro.parada.nome)) continue;
        if (registro.parada.ordem >= destinoRegistro.parada.ordem) continue;
        const geometriaOk = registro.itinerario.geometria?.validacao?.extremidades_compativeis !== false;
        encontrados.push({tipo: "direto", status: geometriaOk ? "candidata" : "candidata_nao_verificada", codigo_linha: registro.catalogo.codigo, nome_linha: registro.catalogo.nome, sentido: registro.direcao.descricao, embarque: registro.parada, desembarque: destinoRegistro.parada, id_viagem: registro.itinerario.id_viagem, geometria_confirmada: geometriaOk, partidas: partidas(registro.linha, registro.itinerario.id_viagem, data)});
      }
    }
    const unicos = [...new Map(encontrados.map(item => [`${item.codigo_linha}|${item.id_viagem}|${item.embarque.ordem}|${item.desembarque.ordem}`, item])).values()];
    if (!unicos.length) {
      const todos = registros(dataset), conexoes = [];
      for (const primeira of todos.filter(item => nomesO.has(item.parada.nome))) for (const transferencia of todos.filter(item => item.itinerario.id_viagem === primeira.itinerario.id_viagem && item.parada.ordem > primeira.parada.ordem)) {
        if (nomesD.has(transferencia.parada.nome)) continue;
        for (const segunda of todos.filter(item => item.codigo !== primeira.codigo && item.chave === transferencia.chave)) for (const fim of todos.filter(item => item.itinerario.id_viagem === segunda.itinerario.id_viagem && nomesD.has(item.parada.nome) && item.parada.ordem > segunda.parada.ordem)) {
          conexoes.push({tipo: "conexao", status: "candidata_nao_verificada", transferencia: transferencia.parada, pernas: [
            {codigo_linha: primeira.catalogo.codigo, nome_linha: primeira.catalogo.nome, sentido: primeira.direcao.descricao, embarque: primeira.parada, desembarque: transferencia.parada, id_viagem: primeira.itinerario.id_viagem, partidas: partidas(primeira.linha, primeira.itinerario.id_viagem, data)},
            {codigo_linha: segunda.catalogo.codigo, nome_linha: segunda.catalogo.nome, sentido: segunda.direcao.descricao, embarque: segunda.parada, desembarque: fim.parada, id_viagem: segunda.itinerario.id_viagem, partidas: partidas(segunda.linha, segunda.itinerario.id_viagem, data)}
          ]});
        }
      }
      return {status: conexoes.length ? "sucesso" : "sem_rota", motivo: conexoes.length ? "" : "Não encontrei uma rota direta ou uma conexão segura para a ordem informada.", sugestoes: {origem: so, destino: sd}, resultados: conexoes.slice(0, 5)};
    }
    return {status: unicos.length ? "sucesso" : "sem_rota", motivo: unicos.length ? "" : "Não encontrei uma rota direta validada para a ordem informada.", sugestoes: {origem: so, destino: sd}, resultados: unicos};
  }

  window.BusaoPlanner = {normalizar, sugerir, planejar};
})();
