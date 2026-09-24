# Monitor de preços de peças de PC

Verifica automaticamente o preço de produtos na Kabum, Pichau, Terabyte (ou
qualquer outra loja) e te avisa por e-mail quando o preço cair ou bater no
valor alvo. Roda sozinho, sem precisar deixar seu PC ligado — o
[GitHub Actions](https://github.com/features/actions) executa o script para
você, de graça, no horário agendado.

## Como funciona

- `items.json` — lista dos produtos que você quer acompanhar.
- `scraper.py` — abre cada link, lê o preço e compara com o histórico.
- `history.json` — histórico de preços (gerado e atualizado automaticamente).
- `.github/workflows/monitor.yml` — agenda a execução (por padrão, 3x por dia).

## Configuração (única vez)

1. **Crie um repositório no GitHub** e suba esses arquivos nele (pode ser
   privado).
2. **Crie uma senha de app do Gmail** (não use sua senha normal):
   - Ative a verificação em duas etapas na sua conta Google.
   - Acesse [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
     e gere uma senha para "Mail".
3. No repositório, vá em **Settings → Secrets and variables → Actions** e
   adicione:
   - `EMAIL_USER` — seu e-mail do Gmail
   - `EMAIL_PASS` — a senha de app gerada no passo 2
   - `EMAIL_TO` — para qual e-mail mandar os alertas (pode ser o mesmo)
4. Edite o `items.json` com os produtos reais que você quer monitorar
   (veja o formato abaixo) e suba (`commit`/`push`) a alteração.
5. Pronto. O workflow já roda sozinho no horário definido. Para testar sem
   esperar, vá na aba **Actions** do repositório → "Monitor de preços" →
   **Run workflow**.

## Formato do `items.json`

```json
[
  {
    "name": "RTX 4070 Super Kabum",
    "url": "https://www.kabum.com.br/produto/000000/exemplo",
    "target_price": 3500.00,
    "selector": ""
  }
]
```

- `target_price`: preço em que você quer ser avisado (avisa também se o
  preço só cair, mesmo sem bater o alvo).
- `selector`: opcional. Deixe em branco — o script tenta descobrir o preço
  sozinho (via dados da página ou heurística de texto). Se ele errar o valor
  para algum produto específico, você pode fixar o elemento certo:
  1. Abra o link do produto no Chrome.
  2. Clique com o botão direito em cima do preço → **Inspecionar**.
  3. No painel que abrir, clique com o botão direito na linha destacada →
     **Copy → Copy selector**.
  4. Cole esse valor no campo `selector` do item.

## Limitações (seja realista com isso)

- **Estabilidade**: essas lojas mudam o layout de vez em quando. Se o script
  parar de achar o preço de um item, ele avisa nos logs do Actions — ajuste o
  `selector` ou peça para eu atualizar o script.
- **Termos de uso**: fazer scraping de um site pode ir contra os termos de
  uso dele. A frequência padrão (3x/dia) é propositalmente baixa; evite
  aumentar muito.
- **E-mail**: se você preferir Outlook/Yahoo em vez de Gmail, me avise —
  só muda o `EMAIL_SMTP_HOST`/`EMAIL_SMTP_PORT`.

## Rodar localmente (opcional, para testar)

```bash
pip install -r requirements.txt
playwright install chromium
EMAIL_USER=voce@gmail.com EMAIL_PASS=senha-de-app EMAIL_TO=voce@gmail.com python scraper.py
```
