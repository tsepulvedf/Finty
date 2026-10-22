/*
 * Tests de format.js con el runner de Node (`node --test frontend/tests/js/`).
 * Los corre core/tests/test_frontend_js.py cuando Node esta instalado.
 */
import assert from "node:assert/strict";
import { afterEach, describe, test } from "node:test";

import { balance, currencyCode, money, signedMoney } from "../../static/finty/js/format.js";

const MINUS = "−";

function inLanguage(lang) {
  globalThis.document = { documentElement: { lang } };
}

afterEach(() => {
  delete globalThis.document;
});

describe("signedMoney: el cero no lleva signo", () => {
  for (const lang of ["es", "en"]) {
    test(`en ${lang}, cero en COP y en USD se muestra sin + ni ${MINUS}`, () => {
      inLanguage(lang);
      for (const zero of ["0", "0.00", 0, "-0.00"]) {
        assert.equal(signedMoney(zero, "COP"), money(0, "COP"));
        assert.equal(signedMoney(zero, "USD"), money(0, "USD"));
        assert.equal(signedMoney(zero, "COP", "income"), money(0, "COP"));
        assert.equal(signedMoney(zero, "COP", "expense"), money(0, "COP"));
      }
    });
  }

  test("en espanol, $ 0 y no + $ 0", () => {
    inLanguage("es");
    assert.equal(signedMoney("0.00", "COP"), "$ 0");
  });

  test("un monto distinto de cero si lleva signo", () => {
    inLanguage("es");
    assert.equal(signedMoney("3100000.00", "COP"), "+ $ 3.100.000");
    assert.equal(signedMoney("-38000.00", "COP"), `${MINUS} $ 38.000`);
    assert.equal(signedMoney("38000.00", "COP", "expense"), `${MINUS} $ 38.000`);
    assert.equal(signedMoney("0.01", "USD", "income").startsWith("+ "), true);
  });
});

describe("currencyCode: el codigo solo cuando el simbolo no lo dice", () => {
  test("en espanol el peso se aclara con COP; en ingles ya lo muestra money()", () => {
    inLanguage("es");
    assert.equal(currencyCode("29900", "COP"), "COP");
    inLanguage("en");
    assert.equal(currencyCode("29900", "COP"), "");
    assert.equal(currencyCode("10", "USD"), "USD");
  });
});

describe("money y balance", () => {
  test("COP sin decimales en espanol y USD con dos", () => {
    inLanguage("es");
    assert.equal(money("38000.00", "COP"), "$ 38.000");
    assert.equal(money("10", "USD"), "US$ 10,00");
  });

  test("en ingles el peso es COP y el dolar $", () => {
    inLanguage("en");
    assert.equal(money("10", "USD"), "$ 10.00");
    assert.match(money("38000", "COP"), /^COP\s38,000$/);
  });

  test("un saldo negativo lleva el menos tipografico; el cero, nada", () => {
    inLanguage("es");
    assert.equal(balance("-5000", "COP"), `${MINUS} $ 5.000`);
    assert.equal(balance("0", "COP"), "$ 0");
  });
});
