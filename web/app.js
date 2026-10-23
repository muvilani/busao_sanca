"use strict";

const estado = document.querySelector("#estado");
const lista = document.querySelector("#lista");
const busca = document.querySelector("#busca");
const data = document.querySelector("#data");
const caso = document.querySelector("#caso");
const planejador = document.querySelector("#planejador");
let dataset = null;

const seguro = (valor) => String(valor ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const normalizar = (texto) => String(texto ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function partidasDaVariante(direcao, tripId) {
  return direcao.servicos.flatMap(servico => servico.partidas
    .filter(item => item.id_viagem === tripId)
    .map(item => ({...item, servico})));
}

function servicoNaVigencia(servico) {
  if (!data.value) return true;
  return data.value >= servico.vigencia_inicio && data.value <= servico.vigencia_fim;
}

function renderizar() {
  if (!dataset) return;
  const termo = normalizar(busca.value);
  const linhas = dataset.linhas.filter(item => {
    const h = item.horarios;
    const destinos = h.variantes.map(v => v.destino).join(" ");
    return normalizar(`${h.linha.codigo} ${h.linha.nome} ${destinos}`).includes(termo);
  });
  lista.innerHTML = linhas.map(renderizarLinha).join("") || '<p class="painel">Nenhuma linha encontrada neste conjunto local.</p>';
  renderizarPlanejador();
}

function renderizarLinha(item) {
  const h = item.horarios;
  const itinerarios = new Map(item.itinerarios.map(i => [i.id_viagem, i]));
  const direcoes = h.direcoes.map(direcao => {
    const variantes = h.variantes.filter(v => v.id_direcao === direcao.id_direcao);
    return `<section class="direcao"><h3>${seguro(direcao.descricao || `Sentido ${direcao.id_direcao}`)}</h3>${variantes.map(v => {
      const partidas = partidasDaVariante(direcao, v.id_viagem).filter(p => servicoNaVigencia(p.servico));
      const itinerario = itinerarios.get(v.id_viagem);
      const primeira = itinerario?.paradas?.[0];
      const coordenadaValida = primeira && Number.isFinite(primeira.latitude) && Number.isFinite(primeira.longitude) && primeira.latitude >= -90 && primeira.latitude <= 90 && primeira.longitude >= -180 && primeira.longitude <= 180;
      const mapaOrigem = coordenadaValida ? ` <a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${primeira.latitude}&mlon=${primeira.longitude}#map=18/${primeira.latitude}/${primeira.longitude}">abrir no mapa</a>` : "";
      const origemHtml = primeira?.nome ? `<p class="origem-viagem"><strong>Primeira parada cadastrada:</strong> ${seguro(primeira.nome)}${mapaOrigem}<br><span class="meta">O ponto oficial de partida não foi confirmado pela fonte.</span></p>` : `<p class="origem-viagem"><strong>Origem da viagem:</strong> não identificada no itinerário.</p>`;
      const horas = `${origemHtml}${partidas.map(p => `<span class="hora" title="Saída na origem da viagem">${seguro(p.saida)}</span>`).join("")}`;
      const paradas = itinerario ? itinerario.paradas.map(p => `<li>${seguro(p.nome)} <a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${p.latitude}&mlon=${p.longitude}#map=18/${p.latitude}/${p.longitude}">mapa</a></li>`).join("") : "";
      const geometriaOk = itinerario?.geometria?.validacao?.extremidades_compativeis !== false;
      return `<article class="variante"><strong>${seguro(v.destino)}</strong><p class="meta">Variante ${v.sequencia_origem} · tripId ${v.id_viagem}</p><div class="horarios">${horas || "Sem partidas na vigência selecionada."}</div><p class="aviso">Horários de saída na origem da viagem — não são previsão de chegada às paradas.</p>${!geometriaOk ? '<p class="aviso">A geometria desta variante diverge das paradas terminais; use apenas a lista de paradas.</p>' : ''}${itinerario ? `<details><summary>Ver ${itinerario.paradas.length} paradas</summary><ol class="paradas">${paradas}</ol></details>` : '<p class="aviso">Itinerário indisponível.</p>'}</article>`;
    }).join("")}</section>`;
  }).join("");
  return `<details class="linha"><summary><span class="codigo">${seguro(h.linha.codigo)}</span><span class="titulo">${seguro(h.linha.nome)}</span><span class="subtitulo">${h.variantes.length} variante(s) · ${item.itinerarios.length} itinerário(s) validados</span></summary>${direcoes}</details>`;
}

let rotaAtual = null;

function preencherSugestoes(input, lista) {
  if (!window.BusaoPlanner || !dataset) return;
  lista.innerHTML = window.BusaoPlanner.sugerir(dataset, input.value)
    .map(item => `<option value="${seguro(item.rotulo)}"></option>`).join("");
}

function partidasRota(perna) {
  return perna.partidas.length
    ? perna.partidas.map(p => `${seguro(p.saida_terminal)} (${seguro(p.descricao_servico)})`).join(" · ")
    : "não disponíveis na vigência selecionada";
}

function pernaRota(perna, indice) {
  const prefixo = indice === null ? "" : `<strong>Trecho ${indice + 1}</strong><br>`;
  return `<p>${prefixo}<strong>Linha ${seguro(perna.codigo_linha)} · ${seguro(perna.nome_linha)}</strong><br>
    Sentido: ${seguro(perna.sentido)}<br>
    Embarque: ${seguro(perna.embarque.nome)}<br>
    Desembarque: ${seguro(perna.desembarque.nome)}<br>
    Percurso no itinerário: ${seguro(perna.paradas_percorridas)} parada(s)<br>
    Partidas oficiais na origem: ${partidasRota(perna)}</p>`;
}

function renderizarResultadoRota() {
  const alvo = document.querySelector("#resultados-rota");
  if (!alvo || !rotaAtual) return;
  if (rotaAtual.status !== "sucesso") {
    alvo.innerHTML = `<p class="aviso">${seguro(rotaAtual.motivo)}</p>`;
    return;
  }
  alvo.innerHTML = `<h3>Alternativas encontradas</h3>${rotaAtual.resultados.map(item => {
    if (item.tipo === "conexao") return `<article class="resultado-rota rota-conexao">
      <span class="selo">1 conexão · candidata não verificada</span>
      <p>Troca estrutural na parada compartilhada <strong>${seguro(item.transferencia.nome)}</strong>.</p>
      ${item.pernas.map((perna, indice) => pernaRota(perna, indice)).join("")}
      <p class="aviso">${seguro(item.aviso_conexao)} Horários são partidas na origem das viagens, não previsões de passagem.</p>
    </article>`;
    return `<article class="resultado-rota">
      <span class="selo">${item.status === "candidata_nao_verificada" ? "direta · geometria não verificada" : "rota direta"}</span>
      ${pernaRota(item, null)}
      <p class="aviso">Horários são partidas na origem da viagem, não previsões de chegada ou passagem na parada.</p>
    </article>`;
  }).join("")}`;
}

function atualizarSelecaoRota(input, alvo) {
  if (!input.value.trim()) {
    alvo.textContent = input.id === "origem-rota" ? "Nenhuma origem selecionada." : "Nenhum destino selecionado.";
    return;
  }
  const opcoes = window.BusaoPlanner.sugerir(dataset, input.value, 1);
  alvo.textContent = opcoes.length ? `Seleção: ${opcoes[0].rotulo}` : "Nenhuma parada correspondente selecionada.";
}

function renderizarPlanejador() {
  if (!dataset || !window.BusaoPlanner) return;
  const origem = document.querySelector("#origem-rota"), destino = document.querySelector("#destino-rota");
  const buscar = document.querySelector("#buscar-rota"), sugestoesOrigem = document.querySelector("#sugestoes-origem"), sugestoesDestino = document.querySelector("#sugestoes-destino");
  const inverter = document.querySelector("#inverter-rota"), limpar = document.querySelector("#limpar-rota");
  const origemSelecionada = document.querySelector("#origem-selecionada"), destinoSelecionado = document.querySelector("#destino-selecionado");
  if (!origem || !destino || !buscar || buscar.dataset.pronto) return;
  buscar.dataset.pronto = "true";
  const executar = () => {
    rotaAtual = window.BusaoPlanner.planejar(dataset, origem.value, destino.value, data.value);
    renderizarResultadoRota();
  };
  origem.addEventListener("input", () => {
    preencherSugestoes(origem, sugestoesOrigem);
    atualizarSelecaoRota(origem, origemSelecionada);
  });
  destino.addEventListener("input", () => {
    preencherSugestoes(destino, sugestoesDestino);
    atualizarSelecaoRota(destino, destinoSelecionado);
  });
  buscar.addEventListener("click", executar);
  inverter.addEventListener("click", () => {
    [origem.value, destino.value] = [destino.value, origem.value];
    atualizarSelecaoRota(origem, origemSelecionada);
    atualizarSelecaoRota(destino, destinoSelecionado);
    if (origem.value && destino.value) executar();
  });
  limpar.addEventListener("click", () => {
    origem.value = "";
    destino.value = "";
    rotaAtual = null;
    document.querySelector("#resultados-rota").innerHTML = "";
    atualizarSelecaoRota(origem, origemSelecionada);
    atualizarSelecaoRota(destino, destinoSelecionado);
    origem.focus();
  });
}

async function iniciar() {
  data.value = new Date().toLocaleDateString("en-CA");
  try {
    const resposta = await fetch("dados.json", {cache: "no-store"});
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    dataset = await resposta.json();
    if (dataset.status !== "sucesso" || !Array.isArray(dataset.linhas)) throw new Error("conjunto inválido");
    const dataFonte = dataset.coletado_em || dataset.consolidado_em;
    const instante = dataFonte ? new Date(dataFonte) : null;
    const momento = instante && !Number.isNaN(instante.getTime()) ? instante.toLocaleString("pt-BR") : "data não informada";
    const cobertura = dataset.cobertura?.completa === true || dataset.cobertura?.completa_no_escopo_solicitado === true;
    const indisponiveis = dataset.classificacao?.com_falhas || [];
    const sintetico = dataset.demonstracao?.sintetico === true;
    const aviso = sintetico
      ? "Demonstração sintética — não representa linhas ou horários reais"
      : cobertura
        ? "Dados validados no escopo selecionado"
        : "Dados locais parciais; linhas indisponíveis não são exibidas";
    estado.innerHTML = `<strong>${aviso}</strong><br><span class="meta">Coleta: ${seguro(momento)} · ${dataset.linhas.length} linha(s). A operação municipal completa não foi confirmada.${indisponiveis.length ? ` Linhas com falha: ${seguro(indisponiveis.join(", "))}.` : ""}</span>`;
    caso.hidden = true;
    caso.innerHTML = "";
    if (window.BusaoStops) window.BusaoStops.init(dataset);
    renderizar();
  } catch (erro) {
    estado.classList.add("erro");
    estado.innerHTML = `<strong>Dados locais indisponíveis</strong><br><span class="meta">Execute o pipeline antes de usar. Motivo: ${seguro(erro.message)}</span>`;
  }
}

busca.addEventListener("input", renderizar);
data.addEventListener("change", () => {
  renderizar();
  const origem = document.querySelector("#origem-rota"), destino = document.querySelector("#destino-rota");
  if (dataset && rotaAtual && origem?.value && destino?.value) {
    rotaAtual = window.BusaoPlanner.planejar(dataset, origem.value, destino.value, data.value);
    renderizarResultadoRota();
  }
});
iniciar();
