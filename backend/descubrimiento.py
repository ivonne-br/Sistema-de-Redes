"""Observación de ARP: interpreta texto y compone un diccionario de observación de arp."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from ipaddress import IPv4Interface
from uuid import uuid4

from backend.arp import crear_contexto_arp, interpretar_tabla_arp, clasificar_entradas_arp


def normalizar_contexto_observacion(contexto):
    """Valida y copia el contexto; calcula máscara y subred sin confiar en ellas."""
    if not isinstance(contexto, dict):
        raise ValueError("El contexto debe ser un diccionario.")
    if not isinstance(contexto.get("ipv4_local"), str):
        raise ValueError("El contexto requiere ipv4_local con prefijo.")
    normalizado = crear_contexto_arp(
        contexto.get("interfaz"), contexto["ipv4_local"], contexto.get("gateway"),
    )
    normalizado["mascara"] = str(IPv4Interface(normalizado["ipv4_local"]).netmask)
    for campo in ("subred", "mascara"):
        if campo in contexto and contexto[campo] != normalizado[campo]:
            raise ValueError(f"El campo {campo} no coincide con la IPv4 local.")
    return normalizado


def resumir_observacion_arp(entradas, errores, contexto_disponible):
    """Cuenta filas observadas; nunca interpreta el total como equipos disponibles."""
    categorias = dict(sorted(Counter(e["categoria"] for e in entradas).items())) if contexto_disponible else None
    incompletas = sum(e["mac"] is None for e in entradas)
    return {
        "entradas": len(entradas),
        "errores": len(errores),
        "por_categoria": categorias,
        "vecinos_candidatos": categorias.get("vecino", 0) if categorias is not None else None,
        "resolucion_mac": {"resuelta": len(entradas) - incompletas, "incompleta": incompletas},
    }


def observar_arp(texto, *, contexto=None, consulta_contexto=None):
    """Interpreta texto y compone una observación; exige contexto manual o consulta."""
    if not isinstance(texto, str):
        raise TypeError("El texto ARP debe ser una cadena.")
    if (contexto is None) == (consulta_contexto is None):
        raise ValueError("Indica un contexto manual o una consulta de contexto, exclusivamente.")
    tabla = interpretar_tabla_arp(texto)
    return observar_tabla_arp(tabla, contexto=contexto, consulta_contexto=consulta_contexto)


def observar_tabla_arp(tabla, *, contexto=None, consulta_contexto=None,
                       fuente="texto_arp_stdin", inicio_captura=None, fin_captura=None):
    """Clasifica una tabla ya interpretada: sirve tanto para stdin como para sysctl."""
    if (contexto is None) == (consulta_contexto is None):
        raise ValueError("Indica un contexto manual o una consulta de contexto, exclusivamente.")
    inicio = datetime.now(timezone.utc).isoformat()
    consulta = deepcopy(consulta_contexto)
    if consulta is None:
        fuente_contexto = "manual"
        contexto = normalizar_contexto_observacion(contexto)
    else:
        fuente_contexto = "contexto_ipv4_macos"
        if not isinstance(consulta, dict):
            raise ValueError("La consulta de contexto debe ser un diccionario.")
        estado_contexto = consulta.get("estado")
        if estado_contexto == "contexto_correcto":
            contexto = normalizar_contexto_observacion(consulta.get("contexto"))
            consulta["contexto"] = deepcopy(contexto)
        elif estado_contexto in ("sin_ruta", "sin_ipv4", "error_recoleccion", "error_interpretacion"):
            if consulta.get("contexto") is not None:
                raise ValueError("Una consulta fallida no puede aportar un contexto válido.")
            contexto = None
        else:
            raise ValueError("Estado de consulta de contexto desconocido.")

    entradas = deepcopy(tabla["entradas"])
    errores = deepcopy(tabla["errores"])
    if contexto is not None:
        entradas = clasificar_entradas_arp(
            entradas, contexto["interfaz"], contexto["ipv4_local"], contexto["gateway"],
        )
    if contexto is None:
        estado = "error_contexto"
    elif errores:
        estado = "observacion_parcial" if entradas else "error_interpretacion"
    elif entradas:
        estado = "observacion_correcta"
    else:
        estado = "sin_entradas"
    resumen = resumir_observacion_arp(entradas, errores, contexto is not None)
    return {
        "version_esquema": 1,
        "id_observacion": str(uuid4()),
        "fuente": fuente,
        "inicio_procesamiento": inicio,
        "fin_procesamiento": datetime.now(timezone.utc).isoformat(),
        "momento_captura_origen": None,
        **({"inicio_captura": inicio_captura, "fin_captura": fin_captura}
           if inicio_captura is not None else {}),
        "estado": estado,
        "fuente_contexto": fuente_contexto,
        "contexto": contexto,
        "consulta_contexto": consulta,
        "entradas": entradas,
        "errores": errores,
        "resumen": resumen,
    }
