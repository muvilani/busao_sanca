"use strict";

(() => {
  const verificacoes = [];
  const erros = [];
  const registrar = (nome, valor) => verificacoes.push({nome, ok: Boolean(valor)});
  window.addEventListener("error", evento => erros.push(String(evento.error || evento.message)));
  window.addEventListener("unhandledrejection", evento => erros.push(String(evento.reason)));

  const esperar = async (condicao, tentativas = 100) => {
    for (let tentativa = 0; tentativa < tentativas; tentativa++) {
      if (condicao()) return true;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    return false;
  };
  const evento = tipo => new Event(tipo, {bubbles: true});
  const definirGeolocalizacao = valor => Object.defineProperty(
    navigator,
    "geolocation",
    {configurable: true, value: valor},
  );

  window.addEventListener("load", async () => {
    try {
      registrar("carregamento", await esperar(() => document.querySelector("#estado")?.textContent.includes("Demonstração sintética")));
      const modo = new URLSearchParams(location.search).get("modo") || "vertical";

      const buscaLinha = document.querySelector("#busca");
      buscaLinha.value = "D1";
      buscaLinha.dispatchEvent(evento("input"));
      registrar("busca_linha", document.querySelector("#lista")?.textContent.includes("Linha Demonstração"));
      buscaLinha.value = "linha inexistente";
      buscaLinha.dispatchEvent(evento("input"));
      registrar("estado_vazio_linha", document.querySelector("#lista")?.textContent.includes("Nenhuma linha encontrada"));
      buscaLinha.value = "";
      buscaLinha.dispatchEvent(evento("input"));

      const buscaParada = document.querySelector("#busca-parada");
      buscaParada.value = "praca exemplo";
      buscaParada.dispatchEvent(evento("input"));
      const parada = [...document.querySelectorAll(".parada-card")].find(item => item.textContent.includes("Praça Exemplo"));
      registrar("busca_manual_parada", Boolean(parada));
      parada?.click();
      registrar("selecao_parada", document.querySelector("#consulta-parada")?.textContent.includes("Linha D1"));
      buscaParada.value = "parada inexistente";
      buscaParada.dispatchEvent(evento("input"));
      registrar("estado_vazio_parada", document.querySelector("#paradas-proximas")?.textContent.includes("Nenhuma parada"));

      const data = document.querySelector("#data");
      data.value = "2031-01-01";
      data.dispatchEvent(evento("change"));
      registrar("mudanca_data", document.querySelector("#consulta-parada")?.textContent.includes("nenhuma partida com vigência compatível"));

      definirGeolocalizacao({
        getCurrentPosition: sucesso => sucesso({coords: {latitude: 0, longitude: 0}}),
      });
      document.querySelector("#usar-localizacao").click();
      registrar("geolocalizacao_permitida", document.querySelector("#localizacao-status")?.textContent.includes("somente nesta tela") && document.querySelectorAll(".parada-card").length > 0);

      definirGeolocalizacao({
        getCurrentPosition: (_sucesso, falha) => falha({code: 1}),
      });
      document.querySelector("#usar-localizacao").click();
      registrar("geolocalizacao_negada", document.querySelector("#localizacao-status")?.textContent.includes("Permissão negada"));

      definirGeolocalizacao(undefined);
      document.querySelector("#usar-localizacao").click();
      registrar("geolocalizacao_indisponivel", document.querySelector("#localizacao-status")?.textContent.includes("não oferece geolocalização"));

      const origem = document.querySelector("#origem-rota"), destino = document.querySelector("#destino-rota");
      origem.value = "Terminal Fictício";
      origem.dispatchEvent(evento("input"));
      destino.value = "Bairro Exemplo";
      destino.dispatchEvent(evento("input"));
      data.value = "2026-10-23";
      document.querySelector("#buscar-rota").click();
      registrar("rota_direta", document.querySelector("#resultados-rota")?.textContent.includes("rota direta"));
      registrar("selecao_explicita", document.querySelector("#origem-selecionada")?.textContent.includes("Terminal Fictício"));

      destino.value = "Jardim Inventado";
      destino.dispatchEvent(evento("input"));
      document.querySelector("#buscar-rota").click();
      registrar("rota_conexao", document.querySelector("#resultados-rota")?.textContent.includes("1 conexão"));
      registrar("data_no_planejador", document.querySelector("#resultados-rota")?.textContent.includes("08:00"));

      document.querySelector("#inverter-rota").click();
      registrar("inverter_rota", origem.value.includes("Jardim Inventado") && destino.value.includes("Terminal Fictício"));
      origem.value = "Praça Exemplo";
      destino.value = "Praça Exemplo";
      document.querySelector("#buscar-rota").click();
      registrar("origem_destino_iguais", document.querySelector("#resultados-rota")?.textContent.includes("mesma parada"));
      document.querySelector("#limpar-rota").click();
      registrar("limpar_rota", !origem.value && !destino.value && !document.querySelector("#resultados-rota")?.textContent);

      origem.focus();
      registrar("navegacao_teclado", document.activeElement === origem);
      registrar("viewport_responsivo", Boolean(document.querySelector('meta[name="viewport"]'))
        && matchMedia(`(orientation: ${modo === "horizontal" ? "landscape" : "portrait"})`).matches);
      registrar("sem_overflow_horizontal", document.documentElement.scrollWidth <= window.innerWidth + 1);
      registrar("navegacao_mobile", ["busca", "paradas", "planejador"].every(id => document.querySelector(`#${id}`)));
      registrar("sem_caso_real_no_demo", document.querySelector("#caso")?.hidden === true && !document.querySelector("#caso")?.textContent.trim());
    } catch (erro) {
      erros.push(String(erro?.stack || erro));
    }

    registrar("sem_erros_console", erros.length === 0);
    const falhas = verificacoes.filter(item => !item.ok);
    const resultado = document.createElement("output");
    resultado.id = "browser-test-results";
    resultado.dataset.status = falhas.length ? "falha" : "ok";
    resultado.dataset.total = String(verificacoes.length);
    resultado.dataset.falhas = falhas.map(item => item.nome).join(",");
    resultado.dataset.erros = erros.join(" | ");
    resultado.textContent = JSON.stringify(verificacoes);
    document.body.appendChild(resultado);
  });
})();
