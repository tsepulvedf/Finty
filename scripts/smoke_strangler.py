"""Demostracion real por Nginx. Crea un usuario de prueba y una cuenta."""
import argparse
from datetime import datetime
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--fallback", action="store_true", help="Ejecutar tras detener Flask")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    def call(path, method="GET", data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Token " + token
        req = Request(base + path, method=method, headers=headers,
                      data=None if data is None else json.dumps(data).encode())
        try:
            response = urlopen(req, timeout=20)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, response.headers

    assert call("/api/v1/health/")[:2] == (200, {"status": "ok", "version": "v1"})
    suggestion = {"description": "almuerzo", "amount": "25000.00", "currency": "COP", "type": "expense"}
    assert call("/api/v2/categorization/", "POST", suggestion)[0] == 401
    status, auth, _ = call("/api/v1/auth/register/", "POST", {
        "email": f"taller-{uuid4().hex}@example.com", "password": "Taller02-" + uuid4().hex,
        "display_name": "Demostracion Taller 02",
    })
    assert status == 201, (status, auth)
    token = auth["token"]
    status, result, headers = call("/api/v2/categorization/", "POST", suggestion, token)
    if args.fallback:
        assert status == 503, (status, result)
    else:
        assert status == 200 and result["category_name"] == "Alimentación", (status, result)
        assert headers["X-Finty-Service"] == "flask-categorization"
        assert call("/api/v2/categorization/", "POST", {**suggestion, "amount": "0"}, token)[0] == 400
    status, account, _ = call("/api/v1/accounts/", "POST", {
        "name": "Cuenta Taller 02", "type": "bank", "initial_balance": "100000.00", "currency": "COP",
    }, token)
    assert status == 201, (status, account)
    status, movement, _ = call("/api/v1/transactions/", "POST", {
        "account_id": account["id"], "amount": "25000.00", "type": "expense",
        "description": "almuerzo", "occurred_on": datetime.now(ZoneInfo("America/Bogota")).date().isoformat(),
    }, token)
    assert status == 201, (status, movement)
    assert movement["category_name"] == "Alimentación"
    assert movement["categorization_source"] == "rule"
    assert movement["categorization_confidence"] == (0.20 if args.fallback else 0.75)
    status, updated, _ = call(f'/api/v1/accounts/{account["id"]}/', token=token)
    assert status == 200 and updated["balance"] == "75000.00", (status, updated)
    assert call(f'/api/v1/transactions/{movement["id"]}/', "DELETE", token=token)[0] == 204
    assert call(f'/api/v1/accounts/{account["id"]}/', "DELETE", token=token)[0] == 204
    print("OK: Nginx, autenticacion, rutas v1/v2, clasificacion y balance" + (" con respaldo local" if args.fallback else " remoto"))
    print("La cuenta y el movimiento se eliminaron; queda un usuario de prueba sin datos financieros.")


if __name__ == "__main__":
    main()
