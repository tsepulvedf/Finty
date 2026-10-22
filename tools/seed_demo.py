"""Usuarios de demostracion para la sustentacion (E2-M9b), por la API.

    python tools/seed_demo.py                                  # contra http://localhost
    python tools/seed_demo.py --base-url http://3.95.100.48    # contra la EC2

Crea (o completa) dos usuarios con datos realistas, siempre por la API publica a
traves del Gateway; nunca escribe en las bases:

- **demo-free@finty.co** (plan Free): dos cuentas y dos meses de movimientos.
- **demo-premium@finty.co** (plan Premium): tres cuentas (una en dolares), seis
  meses de movimientos con gastos fijos y un pico de gasto en el mes actual, el
  pago simulado de Premium, perfil de riesgo y un plan de inversion. Con eso se
  ven insights, gastos recurrentes y recomendaciones.

**Idempotente:** si el usuario existe, ingresa; una cuenta se busca por nombre;
un movimiento se identifica por cuenta, fecha, tipo, monto y descripcion, y solo
se crea si falta. Correrlo dos veces seguidas no duplica nada. Correrlo otro dia
puede agregar los movimientos del mes en curso que ya tengan fecha.

La contrasena es `DEMO_PASSWORD` (por defecto `Finty-Demo-2026`). Solo usa la
biblioteca estandar: corre en la EC2 sin instalar nada.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date

DEFAULT_PASSWORD = "Finty-Demo-2026"


class Api:
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def call(self, method, path, body=None, expect=(200, 201, 204)):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json", "Accept-Language": "es"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        for attempt in range(60):
            request = urllib.request.Request(self.base_url + "/api/v1" + path, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    text = response.read().decode("utf-8")
                    return response.status, json.loads(text) if text else None
            except urllib.error.HTTPError as error:
                text = error.read().decode("utf-8", errors="replace")
                if error.code == 429 or error.code >= 502:
                    time.sleep(1 if error.code >= 502 else 0.5)
                    continue
                try:
                    body_out = json.loads(text) if text else None
                except ValueError:
                    body_out = text
                if error.code in expect:
                    return error.code, body_out
                raise SystemExit(f"{method} {path} -> {error.code}: {text[:300]}")
        raise SystemExit(f"{method} {path}: el Gateway sigue limitando o caido")

    def all_pages(self, path):
        results, page = [], 1
        while True:
            separator = "&" if "?" in path else "?"
            _, body = self.call("GET", f"{path}{separator}page={page}")
            results.extend(body["results"])
            if not body.get("next"):
                return results
            page += 1


def month_day(months_ago, day, today):
    """El dia `day` del mes `months_ago` meses atras; `None` si aun no llega."""
    index = today.year * 12 + today.month - 1 - months_ago
    year, month = index // 12, index % 12 + 1
    candidate = date(year, month, day)
    return candidate if candidate <= today else None


def ensure_user(base_url, email, password, name, stats):
    api = Api(base_url)
    status, body = api.call("POST", "/auth/login/", {"email": email, "password": password}, expect=(200, 400, 401))
    if status == 200:
        stats["usuarios existentes"] += 1
    else:
        status, body = api.call("POST", "/auth/register/", {"email": email, "password": password, "display_name": name},
                                expect=(201, 400))
        if status != 201:
            raise SystemExit(f"No se pudo crear {email} ni ingresar con DEMO_PASSWORD: {body}")
        stats["usuarios creados"] += 1
    return Api(base_url, body["token"])


def ensure_account(api, name, kind, currency, opening, stats):
    for account in api.all_pages("/accounts/"):
        if account["name"] == name:
            stats["cuentas existentes"] += 1
            return account
    _, account = api.call("POST", "/accounts/", {"name": name, "type": kind, "currency": currency, "initial_balance": opening})
    stats["cuentas creadas"] += 1
    return account


def key(account_id, occurred_on, kind, amount, description):
    return (str(account_id), str(occurred_on), kind, f"{float(amount):.2f}", description)


def ensure_transactions(api, account, wanted, stats):
    existing = {
        key(t["account"], t["occurred_on"], t["type"], t["amount"], t["description"])
        for t in api.all_pages(f"/transactions/?account_id={account['id']}")
    }
    for item in wanted:
        k = key(account["id"], item["occurred_on"], item["type"], item["amount"], item["description"])
        if k in existing:
            stats["movimientos existentes"] += 1
            continue
        body = {"account_id": account["id"], **item}
        body["occurred_on"] = str(item["occurred_on"])
        api.call("POST", "/transactions/", body)
        existing.add(k)
        stats["movimientos creados"] += 1


def monthly(today, months, items):
    """Repite `items` (dia, tipo, monto, descripcion, categoria) en los ultimos `months` meses."""
    out = []
    for back in range(months - 1, -1, -1):
        for day, kind, amount, description, category in items(back):
            on = month_day(back, day, today)
            if on is None:
                continue
            item = {"type": kind, "amount": amount, "occurred_on": on, "description": description}
            if category:
                item["category_name"] = category
            out.append(item)
    return out


def seed_premium(base_url, password, today, stats):
    api = ensure_user(base_url, "demo-premium@finty.co", password, "Andrés Restrepo", stats)
    bank = ensure_account(api, "Bancolombia Ahorros", "bank", "COP", "8000000.00", stats)
    cash = ensure_account(api, "Efectivo", "cash", "COP", "400000.00", stats)
    usd = ensure_account(api, "Cuenta en dólares", "bank", "USD", "1500.00", stats)

    def bank_items(back):
        shopping = "690000.00" if back == 0 else "210000.00"    # pico de gasto en el mes actual
        return [
            (1, "income", "4200000.00", "Salario", "Salario"),
            (2, "expense", "1650000.00", "Arriendo apartamento", "Vivienda"),
            (3, "expense", "44900.00", "Netflix", "Entretenimiento"),
            (4, "expense", "120000.00", "Gimnasio Bodytech", "Salud"),
            (5, "expense", "185000.00", "Plan celular y hogar Claro", "Servicios públicos"),
            (6, "expense", "380000.00", "Mercado en el Éxito", None),
            (7, "expense", shopping, "Ropa y zapatos", "Compras"),
        ]

    def cash_items(back):
        return [
            (3, "expense", "18000.00", "Almuerzo corrientazo", None),
            (5, "expense", "12500.00", "Uber al trabajo", None),
        ]

    def usd_items(back):
        return [(4, "income", "350.00", "Proyecto freelance", "Freelance")] if back in (1, 3, 5) else []

    ensure_transactions(api, bank, monthly(today, 6, bank_items), stats)
    ensure_transactions(api, cash, monthly(today, 6, cash_items), stats)
    ensure_transactions(api, usd, monthly(today, 6, usd_items), stats)

    _, me = api.call("GET", "/subscriptions/me/")
    if not me["premium"]:
        api.call("POST", "/subscriptions/checkout/", {"plan": "PREMIUM"})
        stats["suscripciones activadas"] += 1
    status, _ = api.call("GET", "/recommendations/risk-profile/", expect=(200, 404))
    if status == 404:
        api.call("PUT", "/recommendations/risk-profile/",
                 {"investment_horizon": 2, "loss_reaction": 2, "experience": 3, "income_stability": 2, "goal": 2})
        stats["perfiles de riesgo"] += 1
    _, plans = api.call("GET", "/investment-plans/")
    if plans["count"] == 0:
        api.call("POST", "/investment-plans/",
                 {"instrument_type": "collective_investment_fund", "monthly_contribution": "500000", "horizon_months": 36})
        stats["planes de inversion"] += 1


def seed_free(base_url, password, today, stats):
    api = ensure_user(base_url, "demo-free@finty.co", password, "Laura Gómez", stats)
    bank = ensure_account(api, "Davivienda Ahorros", "bank", "COP", "2500000.00", stats)
    cash = ensure_account(api, "Efectivo", "cash", "COP", "150000.00", stats)

    def bank_items(back):
        return [
            (1, "income", "2600000.00", "Salario", "Salario"),
            (2, "expense", "950000.00", "Arriendo habitación", "Vivienda"),
            (4, "expense", "26900.00", "Spotify", "Entretenimiento"),
            (6, "expense", "240000.00", "Mercado en D1", None),
        ]

    def cash_items(back):
        return [(5, "expense", "9800.00", "Bus y TransMilenio", None)]

    ensure_transactions(api, bank, monthly(today, 2, bank_items), stats)
    ensure_transactions(api, cash, monthly(today, 2, cash_items), stats)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Usuarios de demostracion de Finty, por la API.")
    parser.add_argument("--base-url", default=os.environ.get("FINTY_BASE_URL", "http://localhost"))
    args = parser.parse_args(argv)
    password = os.environ.get("DEMO_PASSWORD", DEFAULT_PASSWORD)
    stats = {k: 0 for k in (
        "usuarios creados", "usuarios existentes", "cuentas creadas", "cuentas existentes",
        "movimientos creados", "movimientos existentes", "suscripciones activadas",
        "perfiles de riesgo", "planes de inversion",
    )}
    today = date.today()
    seed_free(args.base_url, password, today, stats)
    seed_premium(args.base_url, password, today, stats)
    print(f"seed-demo contra {args.base_url}")
    for name, value in stats.items():
        print(f"  {name}: {value}")
    print("  usuarios: demo-free@finty.co (Free) y demo-premium@finty.co (Premium)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
