# Teste mobile do Busão Sanca

## O que já foi automatizado

A suíte abre o pacote sintético em Edge, Chrome ou Chromium headless nos
viewports Android 412×915 e iPhone 390×844, além das respectivas orientações
horizontal 915×412 e 844×390. Ela verifica busca de linha e parada, seleção,
data, geolocalização simulada, rotas direta e com conexão, estados vazios e de
erro, foco programático, ausência de overflow e erros JavaScript não tratados.

Isso comprova o comportamento automatizado do navegador, não o funcionamento
em aparelho físico, o teclado virtual, prompts reais de permissão, VoiceOver,
TalkBack, gestos ou diferenças dos navegadores móveis.

## Preparação local segura

Na raiz do repositório, gere e sirva somente o pacote sintético:

```powershell
uv run --locked python preparar_publicacao.py
uv run --locked python -m http.server 8000 --directory publicacao/dist --bind 127.0.0.1
```

Abra `http://127.0.0.1:8000` no computador. Mantenha o terminal visível e
encerre o servidor com `Ctrl+C` ao terminar. Não copie `web/dados.json` para o
pacote e não troque `127.0.0.1` por `0.0.0.0` sem uma decisão explícita de
segurança de rede.

## Android físico por USB

Se Android SDK/ADB e a autorização USB já estiverem configurados, é possível
encaminhar a porta sem expor o servidor à rede:

```powershell
adb reverse tcp:8000 tcp:8000
```

No Android, abra `http://localhost:8000`. Ao final, remova o encaminhamento e
encerre o servidor:

```powershell
adb reverse --remove tcp:8000
```

Não instale drivers, habilite depuração USB ou aceite autorizações do aparelho
automaticamente. Essas ações dependem do responsável pelo dispositivo.

## iPhone físico

O iPhone não oferece equivalente geral ao `adb reverse`. Use apenas uma rota
privada HTTPS, VPN ou proxy reverso que já esteja aprovada e configurada pelo
responsável. Não abra firewall, roteador, túnel público ou hospedagem durante
este teste. Um servidor HTTP na LAN pode ajudar a revisar layout manualmente,
mas não é uma evidência confiável para geolocalização, que depende de contexto
seguro e permissões do Safari.

## Checklist em cada aparelho

1. Confirmar que o aviso “Demonstração sintética” aparece e que não há nomes ou
   horários reais.
2. Testar retrato e paisagem, zoom e fonte ampliada, sem corte lateral.
3. Buscar D1 e uma linha inexistente; abrir itinerário e retornar.
4. Buscar “Praça Exemplo”, selecionar a parada e mudar a data para fora da
   vigência.
5. Testar geolocalização permitida, negada e indisponível sem registrar as
   coordenadas.
6. Planejar Terminal Fictício → Bairro Exemplo e Terminal Fictício → Jardim
   Inventado; testar Inverter, Limpar e origem igual ao destino.
7. Navegar por teclado externo, TalkBack ou VoiceOver quando disponível;
   conferir ordem de foco, nomes dos controles e mensagens anunciadas.
8. Testar rede lenta, recarregamento e suspensão/retomada.
9. Registrar aparelho, sistema, navegador, orientação, resultado e capturas
   que contenham apenas dados sintéticos.

## Registro de problema

Para cada falha, anote passos mínimos, resultado esperado e observado,
aparelho, versão do sistema/navegador, orientação e se houve permissão de
localização. Não anexe localização real, dataset privado, resposta bruta da
fonte nem dados pessoais.
