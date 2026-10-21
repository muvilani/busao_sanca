"use strict";

const estado = document.querySelector("#estado");
const lista = document.querySelector("#lista");
const busca = document.querySelector("#busca");
const data = document.querySelector("#data");
const caso = document.querySelector("#caso");
const planejador = document.querySelector("#planejador");
let dataset = null;

const CONSULTA_REAL = {
  origem: {latitude: -22.0124426, longitude: -47.8931462},
  destino: {latitude: -22.0410217, longitude: -47.8860183},
  inicio: "17:00", fim: "18:00"
};

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

function distancia(a, b) {
  const r = 6371000, rad = x => x * Math.PI / 180;
  const dp = rad(b.latitude - a.latitude), dl = rad(b.longitude - a.longitude);
  const h = Math.sin(dp/2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dl/2) ** 2;
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(h)));
}

function renderizarPlanejador() {
  const linha = dataset?.linhas.find(x => x.horarios.linha.codigo === "34");
  if (!linha) { planejador.hidden = true; return; }
  const variantes = new Map(linha.horarios.variantes.map(v => [v.id_viagem, v]));
  const direcoes = new Map(linha.horarios.direcoes.map(d => [d.id_direcao, d]));
  const candidatos = [];
  for (const itinerario of linha.itinerarios) {
    const variante = variantes.get(itinerario.id_viagem), direcao = direcoes.get(variante?.id_direcao);
    if (!variante || !direcao) continue;
    let melhor = null;
    itinerario.paradas.slice(0, -1).forEach((embarque, indice) => itinerario.paradas.slice(indice + 1).forEach(desembarque => {
      const de = distancia(CONSULTA_REAL.origem, embarque), dd = distancia(CONSULTA_REAL.destino, desembarque);
      if (!melhor || de + dd < melhor.de + melhor.dd) melhor = {embarque, desembarque, de, dd};
    }));
    if (melhor.de > 800 || melhor.dd > 800) continue;
    const partidas = partidasDaVariante(direcao, itinerario.id_viagem).filter(p =>
      p.servico.descricao === "Dias úteis" && servicoNaVigencia(p.servico) && p.saida >= CONSULTA_REAL.inicio && p.saida <= CONSULTA_REAL.fim
    );
    candidatos.push({itinerario, variante, partidas, ...melhor});
  }
  candidatos.sort((a,b) => (b.partidas.length - a.partidas.length) || (a.de+a.dd-b.de-b.dd));
  planejador.hidden = false;
  planejador.innerHTML = `<h2>Experimento: StepWise → Rua Icaraí</h2><p><span class="selo">candidata não verificada</span></p><p>A linha 34 tem variantes em que o embarque aparece antes do desembarque. A posição exata da StepWise não foi obtida, portanto o ponto e a caminhada ainda precisam de conferência presencial.</p>${candidatos.slice(0,3).map((c,i) => `<article class="rota-exp"><h3>${i+1}. Linha 34 · ${seguro(c.variante.destino)}</h3><div class="passos"><b>A</b><div><strong>${seguro(c.embarque.nome)}</strong><br><span class="meta">${Math.round(c.de)} m em linha reta desde o centroide do CEP · parada ${c.embarque.ordem}</span></div><b>B</b><div><strong>${seguro(c.desembarque.nome)}</strong><br><span class="meta">${Math.round(c.dd)} m em linha reta até o centroide da Rua Icaraí · parada ${c.desembarque.ordem}</span></div></div><p><strong>Partidas no terminal:</strong> ${c.partidas.length ? c.partidas.map(p => seguro(p.saida)).join(" · ") : "nenhuma entre 17h e 18h no serviço rotulado “Dias úteis”"}</p><p class="aviso">Não há horário confirmado de passagem no embarque. Distâncias não são rotas reais a pé.${c.itinerario.geometria.validacao.extremidades_compativeis === false ? " A geometria desta variante é divergente." : ""}</p></article>`).join("")}<p class="atribuicao">Geocodificação pontual: Nominatim/OpenStreetMap. Dados © contribuidores do OpenStreetMap, ODbL. Precisão: origem = centroide de CEP (baixa); destino = centroide de via (aproximada).</p>`;
}

function renderizarLinha(item) {
  const h = item.horarios;
  const itinerarios = new Map(item.itinerarios.map(i => [i.id_viagem, i]));
  const direcoes = h.direcoes.map(direcao => {
    const variantes = h.variantes.filter(v => v.id_direcao === direcao.id_direcao);
    return `<section class="direcao"><h3>${seguro(direcao.descricao || `Sentido ${direcao.id_direcao}`)}</h3>${variantes.map(v => {
      const partidas = partidasDaVariante(direcao, v.id_viagem).filter(p => servicoNaVigencia(p.servico));
      const itinerario = itinerarios.get(v.id_viagem);
      const horas = partidas.map(p => `<span class="hora" title="Saída na origem da viagem">${seguro(p.saida)}</span>`).join("");
      const paradas = itinerario ? itinerario.paradas.map(p => `<li>${seguro(p.nome)} <a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${p.latitude}&mlon=${p.longitude}#map=18/${p.latitude}/${p.longitude}">mapa</a></li>`).join("") : "";
      const geometriaOk = itinerario?.geometria?.validacao?.extremidades_compativeis !== false;
      return `<article class="variante"><strong>${seguro(v.destino)}</strong><p class="meta">Variante ${v.sequencia_origem} · tripId ${v.id_viagem}</p><div class="horarios">${horas || "Sem partidas na vigência selecionada."}</div><p class="aviso">Horários de saída na origem da viagem — não são previsão de chegada às paradas.</p>${!geometriaOk ? '<p class="aviso">A geometria desta variante diverge das paradas terminais; use apenas a lista de paradas.</p>' : ''}${itinerario ? `<details><summary>Ver ${itinerario.paradas.length} paradas</summary><ol class="paradas">${paradas}</ol></details>` : '<p class="aviso">Itinerário indisponível.</p>'}</article>`;
    }).join("")}</section>`;
  }).join("");
  return `<details class="linha"><summary><span class="codigo">${seguro(h.linha.codigo)}</span><span class="titulo">${seguro(h.linha.nome)}</span><span class="subtitulo">${h.variantes.length} variante(s) · ${item.itinerarios.length} itinerário(s) validados</span></summary>${direcoes}</details>`;
}

async function iniciar() {
  data.value = new Date().toLocaleDateString("en-CA");
  try {
    const resposta = await fetch("dados.json", {cache: "no-store"});
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    dataset = await resposta.json();
    if (dataset.status !== "sucesso" || !dataset.cobertura?.completa_no_escopo_solicitado) throw new Error("conjunto parcial ou inválido");
    const momento = new Date(dataset.coletado_em).toLocaleString("pt-BR");
    estado.innerHTML = `<strong>Dados validados no escopo selecionado</strong><br><span class="meta">Coleta: ${seguro(momento)} · ${dataset.linhas.length} linha(s). A operação municipal completa não foi confirmada.</span>`;
    caso.hidden = false;
    caso.innerHTML = '<h2>XV de Novembro → Vila Morumbi</h2><p>A análise encontrou uma ligação candidata pela linha 34, com embarque antes do desembarque. Ela permanece não verificada porque a coordenada exata da StepWise não foi obtida.</p>';
    renderizar();
  } catch (erro) {
    estado.classList.add("erro");
    estado.innerHTML = `<strong>Dados locais indisponíveis</strong><br><span class="meta">Execute o pipeline antes de usar. Motivo: ${seguro(erro.message)}</span>`;
  }
}

busca.addEventListener("input", renderizar);
data.addEventListener("change", renderizar);
iniciar();
