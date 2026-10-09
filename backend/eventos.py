"""Configura y escribe los registros: stderr para diagnóstico, stdout para resultados JSON."""

import logging
import sys
import time


def configurar_logging(nivel="WARNING"):
    """Configura solo el logger del CLI; una repetición no duplica sus eventos."""
    logger = logging.getLogger("backend.cli")
    logger.setLevel(nivel)
    logger.propagate = False
    # Solo se reemplaza el handler creado aquí; no se altera el logger raíz.
    for handler in list(logger.handlers):
        if getattr(handler, "_backend_cli", False):
            logger.removeHandler(handler)
            handler.close()
    handler = logging.StreamHandler(sys.stderr)
    handler._backend_cli = True
    formato = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formato.converter = time.gmtime
    handler.setFormatter(formato)
    logger.addHandler(handler)
    return logger


def registrar_resultado(logger, operacion, resultado):
    """Resume estados y cantidades sin volcar IP, MAC ni texto recibido."""
    if operacion == "descubrir":
        estado = resultado["estado"]
        if estado in ("observacion_correcta", "sin_entradas"):
            nivel = logging.INFO
        elif estado == "observacion_parcial":
            nivel = logging.WARNING
        else:
            nivel = logging.ERROR
        logger.log(nivel, "operacion=descubrir estado=%s entradas=%d errores=%d",
                   estado, len(resultado["entradas"]), len(resultado["errores"]))
    elif operacion == "arp":
        contexto = resultado.get("consulta_contexto", {}).get("estado")
        if contexto is not None and contexto != "contexto_correcto":
            estado, nivel = contexto, logging.ERROR
        elif resultado["errores"]:
            estado, nivel = "interpretacion_con_errores", logging.WARNING
        elif not resultado["entradas"]:
            estado, nivel = "sin_entradas", logging.INFO
        else:
            estado, nivel = "interpretacion_correcta", logging.INFO
        logger.log(nivel, "operacion=arp estado=%s entradas=%d errores=%d",
                   estado, len(resultado["entradas"]), len(resultado["errores"]))
    else:
        estado = resultado["estado"]
        if estado in ("respuesta_valida", "contexto_correcto", "diagnostico_con_datos"):
            nivel = logging.INFO
        elif estado == "sin_respuesta":
            nivel = logging.WARNING
        else:
            nivel = logging.ERROR
        logger.log(nivel, "operacion=%s estado=%s", operacion, estado)
