"""Periodo mensual `AAAA-MM` (anillo de Dominio, Python puro)."""
import re
from dataclasses import dataclass
from datetime import date

from domain.exceptions import InvalidPeriodError

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")
MONTHS_PER_YEAR = 12


@dataclass(frozen=True, order=True)
class Period:
    """Un mes calendario. Ordenable, inmutable y comparable por valor."""

    year: int
    month: int

    def __post_init__(self):
        if not 1 <= self.month <= MONTHS_PER_YEAR or not 1 <= self.year <= 9999:
            raise InvalidPeriodError()

    @classmethod
    def parse(cls, text):
        """`"2026-10"` → `Period(2026, 10)`. Cualquier otra forma es invalida."""
        match = _PERIOD_RE.match(text.strip()) if isinstance(text, str) else None
        if match is None:
            raise InvalidPeriodError()
        return cls(int(match.group(1)), int(match.group(2)))

    @classmethod
    def of(cls, day):
        """Periodo al que pertenece una fecha."""
        return cls(day.year, day.month)

    def shift(self, months):
        """Periodo desplazado `months` meses (negativo hacia atras)."""
        index = self.year * MONTHS_PER_YEAR + (self.month - 1) + months
        return Period(index // MONTHS_PER_YEAR, index % MONTHS_PER_YEAR + 1)

    def previous(self, count):
        """Los `count` periodos anteriores, del mas antiguo al mas reciente."""
        return tuple(self.shift(-offset) for offset in range(count, 0, -1))

    def window(self, size):
        """`size` periodos que terminan en este, del mas antiguo a este."""
        return self.previous(size - 1) + (self,)

    @property
    def start(self):
        """Primer dia del mes."""
        return date(self.year, self.month, 1)

    @property
    def end(self):
        """Primer dia del mes siguiente (limite exclusivo)."""
        return self.shift(1).start

    def __str__(self):
        return f"{self.year:04d}-{self.month:02d}"
