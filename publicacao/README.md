# Pacote de publicação seguro

Esta pasta prepara uma prévia estática sem copiar o dataset privado de
`web/dados.json` ou qualquer conteúdo de `saida/`.

Execute na raiz do repositório:

```powershell
python preparar_publicacao.py
python -m http.server 8000 --directory publicacao/dist --bind 127.0.0.1
```

O comando copia somente os assets explicitamente permitidos pelo script e
publica `dados.demo.json` como `dist/dados.json`. O fixture é inteiramente
sintético, usa identificadores reservados para demonstração e não representa
linhas, locais, itinerários, calendário ou horários reais.

`publicacao/dist/` é ignorado pelo Git. O diretório serve para revisão local ou
para alimentar futuramente um processo de publicação autorizado; este script
não faz deploy, não acessa rede e não modifica o repositório separado `site`.
