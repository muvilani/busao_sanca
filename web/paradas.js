"use strict";

/* Índice local de paradas e interface de proximidade. Nenhuma localização é armazenada ou enviada. */
(function () {
  const R = 6371000;
  const normalizar = texto => String(texto ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const escape = valor => String(valor ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const coordenadaValida = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
  function distancia(a, b) {
    const rad = x => x * Math.PI / 180, dp = rad(b.latitude - a.latitude), dl = rad(b.longitude - a.longitude);
    const h = Math.sin(dp / 2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dl / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function construirIndice(dataset) {
    const mapa = new Map();
    (dataset.linhas || []).forEach(linha => {
      const h = linha.horarios || {}, codigo = String(linha.catalogo?.codigo ?? h.linha?.codigo ?? "");
      const variantes = new Map((h.variantes || []).map(v => [String(v.id_viagem), v]));
      const direcoes = new Map((h.direcoes || []).map(d => [String(d.id_direcao), d]));
      (linha.itinerarios || []).forEach(it => {
        const variante = variantes.get(String(it.id_viagem)) || {}, direcao = direcoes.get(String(variante.id_direcao)) || {};
        const partidas = (direcao.servicos || []).flatMap(servico => (servico.partidas || []).filter(p => String(p.id_viagem) === String(it.id_viagem)).map(p => ({saida: p.saida, servico: servico.descricao, id_viagem: p.id_viagem})));
        (it.paradas || []).forEach((p, posicao) => {
          const chave = p.id_parada != null ? `id:${p.id_parada}` : `ocorrencia:${codigo}:${it.id_viagem}:${posicao}`;
          if (!mapa.has(chave)) mapa.set(chave, {chave, id_parada: p.id_parada, nome: p.nome || "Parada sem nome", latitude: p.latitude, longitude: p.longitude, atendimentos: [], linhas: []});
          const atendimento = {codigo_linha: codigo, nome_linha: h.linha?.nome || linha.catalogo?.nome || "", sentido: direcao.descricao || "", destino: variante.destino || "", variante: variante.sequencia_origem, id_viagem: it.id_viagem, ordem: posicao + 1, partidas};
          const item = mapa.get(chave);
          if (!item.atendimentos.some(a => a.codigo_linha === atendimento.codigo_linha && a.id_viagem === atendimento.id_viagem)) item.atendimentos.push(atendimento);
          if (!item.linhas.includes(codigo)) item.linhas.push(codigo);
        });
      });
    });
    return {paradas: [...mapa.values()].sort((a, b) => normalizar(a.nome).localeCompare(normalizar(b.nome)))};
  }
  function proximas(indice, latitude, longitude, limite = 8) {
    if (!coordenadaValida(latitude, longitude)) throw new Error("Localização inválida.");
    return indice.paradas.filter(p => coordenadaValida(p.latitude, p.longitude)).map(p => ({...p, distancia_metros: distancia({latitude, longitude}, p)})).sort((a, b) => a.distancia_metros - b.distancia_metros).slice(0, limite);
  }
  function buscar(indice, termo, limite = 8) {
    const q = normalizar(termo);
    return indice.paradas.filter(p => !q || normalizar(`${p.nome} ${p.id_parada}`).includes(q)).slice(0, limite);
  }
  function mapaLink(p) {
    return coordenadaValida(p.latitude, p.longitude) ? `<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${p.latitude}&mlon=${p.longitude}#map=18/${p.latitude}/${p.longitude}">abrir no mapa</a>` : "";
  }
  function renderizarConsulta(p) {
    const alvo = document.querySelector("#consulta-parada");
    if (!alvo) return;
    if (!p) { alvo.innerHTML = ""; return; }
    const atendimentos = [...p.atendimentos].sort((a, b) => `${a.codigo_linha}${a.sentido}`.localeCompare(`${b.codigo_linha}${b.sentido}`));
    alvo.innerHTML = `<h3>${escape(p.nome)}</h3><p class="meta">Identificação da parada: ${escape(p.id_parada ?? "não disponível")} · ${mapaLink(p) || "coordenada não disponível"}</p>${atendimentos.length ? atendimentos.map(a => `<article class="atendimento-parada"><strong>Linha ${escape(a.codigo_linha)} · ${escape(a.nome_linha)}</strong><br><span>Sentido: ${escape(a.sentido || "não informado")} · Destino: ${escape(a.destino || "não informado")}</span><br><span class="meta">Variante ${escape(a.variante ?? "não informada")} · parada ${a.ordem} · viagem ${escape(a.id_viagem)}</span><p><strong>Partidas oficiais na origem:</strong> ${a.partidas.length ? a.partidas.map(p => escape(p.saida)).join(" · ") : "não disponíveis"}</p><p class="aviso">Esses horários são saídas na origem da viagem, não horários de passagem nesta parada.</p></article>`).join("") : '<p class="aviso">Nenhuma linha/horário validado associado a esta parada.</p>'}`;
    alvo.scrollIntoView({behavior: "smooth", block: "nearest"});
  }
  function init(dataset) {
    const indice = construirIndice(dataset), status = document.querySelector("#localizacao-status"), lista = document.querySelector("#paradas-proximas"), busca = document.querySelector("#busca-parada"), sugestoes = document.querySelector("#sugestoes-parada");
    const mostrar = resultados => { lista.innerHTML = resultados.length ? resultados.map(p => `<button class="parada-card" type="button" data-chave="${escape(p.chave)}"><strong>${escape(p.nome)}</strong><span>${p.distancia_metros == null ? `${p.linhas.length} linha(s)` : `${Math.round(p.distancia_metros)} m em linha reta`} · ${escape(p.linhas.join(", "))}</span></button>`).join("") : '<p class="aviso">Nenhuma parada encontrada.</p>'; lista.querySelectorAll("[data-chave]").forEach(btn => btn.addEventListener("click", () => renderizarConsulta(indice.paradas.find(p => p.chave === btn.dataset.chave)))); };
    const atualizarSugestoes = () => { sugestoes.innerHTML = buscar(indice, busca.value, 12).map(p => `<option value="${escape(p.nome)}"></option>`).join(""); };
    busca.addEventListener("input", () => { atualizarSugestoes(); mostrar(buscar(indice, busca.value)); });
    document.querySelector("#usar-localizacao").addEventListener("click", () => {
      if (!navigator.geolocation) { status.textContent = "Este navegador não oferece geolocalização. Use a busca manual."; return; }
      status.textContent = "Solicitando localização…";
      navigator.geolocation.getCurrentPosition(pos => { status.textContent = "Localização usada somente nesta tela; distância em linha reta."; mostrar(proximas(indice, pos.coords.latitude, pos.coords.longitude)); }, err => { const motivos = {1: "Permissão negada.", 2: "Localização indisponível.", 3: "Tempo esgotado."}; status.textContent = `${motivos[err.code] || "Não foi possível obter a localização."} Use a busca manual.`; }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 60000});
    });
    atualizarSugestoes();
    mostrar([]);
    return indice;
  }
  window.BusaoStops = {construirIndice, coordenadaValida, distancia, proximas, buscar, init, renderizarConsulta};
})();
