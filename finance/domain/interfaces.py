"""Contratos abstractos del dominio `finance` (anillo de Dominio, Python puro).

Define la ABC `Categorizer`. Los services dependen de esta abstraccion;
`finance/infra/categorizers.py` la implementa (M4). Esa inversion es lo que
sostiene el principio de inversion de dependencias: `finance/domain/` no importa
nada de `finance/infra/` (ARCHITECTURE.md 8, fila DIP).

Este modulo no importa Django.
"""
from abc import ABC, abstractmethod


class Categorizer(ABC):
    """Clasifica una transaccion y devuelve una categoria sugerida.

    **Interfaz de un solo metodo, y es ISP aplicado.** No se obliga a un
    `MockCategorizer` a implementar configuracion de API, timeouts ni reintentos
    que no usa; tampoco a `RuleBasedCategorizer`, que solo consulta un
    diccionario en memoria. Cada implementacion resuelve internamente lo que su
    mecanismo necesite, y ninguna carga con los metodos de las demas.

    El contrato declarado en `categorize()` es lo que hace sustituibles a las
    implementaciones entre si (LSP): el Service puede recibir cualquiera de las
    tres sin una sola linea de codigo condicional.
    """

    @abstractmethod
    def categorize(self, description, amount, transaction_type):
        """Sugiere una categoria para una transaccion.

        Args:
            description: texto libre que describe el movimiento.
            amount: `Money` con el monto de la transaccion.
            transaction_type: miembro de `TransactionType`.

        Returns:
            Un `CategorySuggestion` valido.

        **Contrato que toda implementacion debe cumplir.** Es lo que sostiene el
        LSP: quien recibe un `Categorizer` programa contra estas cuatro reglas y
        no contra ninguna implementacion concreta.

        1. **Siempre** devuelve un `CategorySuggestion` valido. Nunca `None`,
           nunca una cadena, nunca un diccionario.
        2. **Nunca** propaga excepciones. Si el mecanismo subyacente falla —se
           cae el proveedor externo, expira el timeout, no hay red— la
           implementacion lo resuelve internamente y devuelve una sugerencia con
           confianza reducida. Quien la invoca no necesita un `try/except` ni
           saber que ocurrio.
        3. Es **idempotente** respecto a la entrada: dentro de una misma
           implementacion, la misma entrada produce la misma salida.
        4. **No persiste nada** ni produce efectos de lado observables. Ni
           escribe en base de datos, ni muta sus argumentos, ni lleva contadores
           internos que alteren respuestas posteriores.
        """
