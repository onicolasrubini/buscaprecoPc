"""
Monitor de preços de peças de PC (Kabum, Pichau, Terabyte, etc.)

Como funciona:
1. Lê os produtos em items.json (nome, link, preço alvo, seletor CSS opcional).
2. Abre cada link com um navegador headless (Playwright) e tenta extrair o preço.
3. Compara com o histórico salvo em history.json.
4. Se o preço caiu, ou bateu no alvo, manda um e-mail.
5. Salva o novo preço no histórico (o workflow do GitHub Actions faz o commit disso).

Sites como a Kabum carregam o preço via JavaScript, por isso usamos um navegador
headless em vez de apenas requests/BeautifulSoup — é mais lento, mas funciona em
qualquer uma das três lojas.

IMPORTANTE — leia antes de usar:
- Scraping de sites de terceiros pode violar os Termos de Uso deles. Use com
  moderação (o agendamento padrão já é de poucas vezes por dia) e por sua conta.
- A extração do preço é heurística: se a loja mudar o layout, pode parar de
  funcionar. Quando isso acontecer, ajuste o `selector` do item em items.json
  (veja instruções no README.md) ou me avise para eu ajustar o script.
"""

import json
import os
import re
import smtplib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from playwright.sync_api import sync_playwright

ITEMS_FILE = Path("items.json")
HISTORY_FILE = Path("history.json")

PRICE_RE = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*,\d{2}")


def parse_price(text: str) -> float | None:
    """Converte 'R$ 3.499,90' -> 3499.90"""
    match = PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group(0).replace("R$", "").strip()
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def extract_price(page, selector: str) -> float | None:
    """Tenta extrair o preço da página. Usa o seletor CSS se fornecido,
    senão tenta um JSON-LD (schema.org) e, por fim, cai para uma heurística
    de texto (primeiro valor 'R$ ...' visível na página)."""

    if selector:
        try:
            el = page.locator(selector).first
            el.wait_for(timeout=8000)
            price = parse_price(el.inner_text())
            if price:
                return price
        except Exception:
            pass  # cai para os métodos abaixo

    # 1) JSON-LD (schema.org/Product -> offers -> price)
    try:
        scripts = page.locator("script[type='application/ld+json']")
        count = scripts.count()
        for i in range(count):
            try:
                data = json.loads(scripts.nth(i).inner_text())
            except Exception:
                continue
            candidates = data if isinstance(data, list) else [data]
            for c in candidates:
                offers = c.get("offers") if isinstance(c, dict) else None
                if isinstance(offers, dict) and offers.get("price"):
                    try:
                        return float(str(offers["price"]).replace(",", "."))
                    except ValueError:
                        pass
    except Exception:
        pass

    # 2) Heurística de texto: primeiro "R$ ..." visível no corpo da página
    try:
        body_text = page.locator("body").inner_text()
        price = parse_price(body_text)
        if price:
            return price
    except Exception:
        pass

    return None


def load_items() -> list[dict]:
    if not ITEMS_FILE.exists():
        print("items.json não encontrado.", file=sys.stderr)
        return []
    return json.loads(ITEMS_FILE.read_text(encoding="utf-8"))


def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {}


def save_history(history: dict) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def send_email(subject: str, body: str) -> None:
    user = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASS")
    to = os.environ.get("EMAIL_TO", user)
    host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("EMAIL_SMTP_PORT", "465"))

    if not user or not password:
        print("EMAIL_USER/EMAIL_PASS não configurados — pulando envio de e-mail.")
        print(f"[e-mail que seria enviado]\n{subject}\n{body}")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL(host, port) as server:
        server.login(user, password)
        server.sendmail(user, [to], msg.as_string())


def main() -> None:
    items = load_items()
    history = load_history()
    alerts = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            locale="pt-BR",
        )

        for item in items:
            name = item["name"]
            url = item["url"]
            target = float(item["target_price"])
            selector = item.get("selector", "")

            print(f"Verificando: {name}")
            page = context.new_page()
            price = None
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)  # dá tempo do JS renderizar o preço
                price = extract_price(page, selector)
            except Exception as e:
                print(f"  Erro ao carregar/ler a página: {e}", file=sys.stderr)
            finally:
                page.close()

            if price is None:
                print(f"  Não consegui identificar o preço de '{name}'. "
                      f"Talvez precise de um selector específico no items.json.")
                continue

            print(f"  Preço encontrado: R$ {price:.2f}")
            record = history.get(name, {"history": []})
            last_price = record["history"][-1]["price"] if record["history"] else None
            record["history"].append({
                "price": price,
                "date": datetime.now(timezone.utc).isoformat(),
            })
            history[name] = record

            hit_target = price <= target
            dropped = last_price is not None and price < last_price

            if hit_target or dropped:
                alerts.append({
                    "name": name, "url": url, "price": price,
                    "target": target, "last_price": last_price,
                    "hit_target": hit_target,
                })

        browser.close()

    save_history(history)

    if alerts:
        lines = ["Atualização do monitor de preços de peças de PC:\n"]
        for a in alerts:
            lines.append(f"- {a['name']}")
            lines.append(f"  Preço atual: R$ {a['price']:.2f} (alvo: R$ {a['target']:.2f})")
            if a["last_price"] is not None:
                lines.append(f"  Última verificação: R$ {a['last_price']:.2f}")
            if a["hit_target"]:
                lines.append("  >>> Bateu no preço alvo! <<<")
            lines.append(f"  Link: {a['url']}\n")
        body = "\n".join(lines)
        send_email("Monitor de preços: atualização de preço", body)
        print("E-mail de alerta enviado.")
    else:
        print("Nenhuma queda de preço ou preço-alvo atingido nesta verificação.")


if __name__ == "__main__":
    main()
