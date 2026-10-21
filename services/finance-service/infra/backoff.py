"""Espera creciente entre reintentos del relay."""


class Backoff:
    """Duplica la espera en cada fallo, hasta `maximum`; `reset()` vuelve al inicio."""

    def __init__(self, initial=1.0, maximum=30.0):
        self._initial = initial
        self._maximum = maximum
        self._current = initial

    def next_delay(self):
        """Espera para este fallo; la del siguiente sera el doble."""
        delay = self._current
        self._current = min(self._current * 2, self._maximum)
        return delay

    def reset(self):
        self._current = self._initial
