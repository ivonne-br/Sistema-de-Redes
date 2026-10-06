# Representar y validar los tiempos de sonda => objeto de configuración

"""Parámetros y validación de la sonda individual."""

from dataclasses import dataclass 

@dataclass(frozen=True)
class ConfiguracionSonda:
    espera_ms: int = 1000
    limite_proceso_s: int = 5

    def __post_init__(self):
        if type(self.espera_ms) is not int:
            raise TypeError("espera_ms debe ser un número entero.")

        if type(self.limite_proceso_s) is not int:
            raise TypeError("limite_proceso_s debe ser un número entero.")

        if self.espera_ms <= 0:
            raise ValueError("espera_ms debe ser mayor que cero.")

        if self.limite_proceso_s <= 0:
            raise ValueError("limite_proceso_s debe ser mayor que cero.")

        if self.limite_proceso_s * 1000 <= self.espera_ms:
            raise ValueError(
                "El límite del proceso debe ser mayor "
                "que la espera de respuesta."
            )