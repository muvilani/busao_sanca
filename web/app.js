"use strict";

const estado = document.querySelector("#estado");
const lista = document.querySelector("#lista");
const busca = document.querySelector("#busca");
const data = document.querySelector("#data");
const caso = document.querySelector("#caso");
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
    caso.innerHTML = '<h2>XV de Novembro → Vila Morumbi</h2><p>A linha 34 foi selecionada para investigação porque há indício externo de passagem pela Av. Morumbi. Use as paradas abaixo para conferência manual; embarque perto da StepWise e conexão direta ainda não estão comprovados.</p>';
    renderizar();
  } catch (erro) {
    estado.classList.add("erro");
    estado.innerHTML = `<strong>Dados locais indisponíveis</strong><br><span class="meta">Execute o pipeline antes de usar. Motivo: ${seguro(erro.message)}</span>`;
  }
}

busca.addEventListener("input", renderizar);
data.addEventListener("change", renderizar);
iniciar();
