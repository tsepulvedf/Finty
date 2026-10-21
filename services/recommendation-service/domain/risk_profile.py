"""`RiskProfile`: cuestionario de 5 preguntas (ARCHITECTURE.md §6.6).

Cada respuesta vale de 1 a 3, de la opcion mas prudente a la mas tolerante al
riesgo. La suma (5 a 15) determina el tipo:

    5 a 8    conservative
    9 a 11   moderate
    12 a 15  aggressive
"""
from dataclasses import dataclass

from domain.exceptions import InvalidRiskAnswerError
from domain.value_objects import RiskProfileType

# Orden estable de las preguntas; tambien es el de la respuesta HTTP.
QUESTIONS = (
    "investment_horizon",  # 1 menos de 1 año · 2 de 1 a 3 años · 3 mas de 3 años
    "loss_reaction",       # si cae un 10%: 1 retiro todo · 2 espero · 3 aporto mas
    "experience",          # 1 ninguna · 2 ahorro o CDT · 3 fondos o acciones
    "income_stability",    # 1 inestables · 2 algo estables · 3 muy estables
    "goal",                # 1 proteger el capital · 2 crecer con moderacion · 3 maximizar
)
MIN_ANSWER = 1
MAX_ANSWER = 3

# Limite superior (incluido) de cada tipo, en orden.
SCORE_RANGES = (
    (8, RiskProfileType.CONSERVATIVE),
    (11, RiskProfileType.MODERATE),
    (15, RiskProfileType.AGGRESSIVE),
)


@dataclass(frozen=True)
class RiskProfile:
    """Respuestas del cuestionario; el puntaje y el tipo se derivan de ellas."""

    answers: tuple  # ((pregunta, puntaje), ...) en el orden de QUESTIONS

    @classmethod
    def from_answers(cls, answers):
        """Valida un `{pregunta: puntaje}` con las cinco preguntas."""
        ordered = []
        for question in QUESTIONS:
            value = answers.get(question)
            if isinstance(value, bool) or not isinstance(value, int) or not MIN_ANSWER <= value <= MAX_ANSWER:
                raise InvalidRiskAnswerError(
                    f"La respuesta a '{question}' debe ser 1, 2 o 3."
                )
            ordered.append((question, value))
        return cls(tuple(ordered))

    @property
    def score(self):
        return sum(value for _, value in self.answers)

    @property
    def profile_type(self):
        for upper, profile_type in SCORE_RANGES:
            if self.score <= upper:
                return profile_type
        raise InvalidRiskAnswerError()
