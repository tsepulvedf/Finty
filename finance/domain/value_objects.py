"""Value Objects del dominio `finance` (anillo de Dominio, Python puro).

Contendra `AccountType`, `TransactionType` y `CategorySuggestion`. Todos
inmutables: `@dataclass(frozen=True)` o enumeraciones puras de Python, sin
`TextChoices` de Django.

Se implementa en M2. Este modulo no importa Django.
"""
