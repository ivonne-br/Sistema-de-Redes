"""Calidad y recuentos contextuales de ARP sobre copias, sin consultar fuentes."""
# Separar el último intento de la última lectura utilizable del mismo tramo, y su antigüedad.

def evaluar_calidad_arp(registros, *, id_ejecucion, vigencia_s, id_contexto=None):
    """Separa el último intento de la última lectura utilizable del mismo tramo.

    Una lectura parcial aporta evidencia positiva, pero nunca confirma ausencias.
    La antigüedad parte del fin de la consulta, no de la presencia de un vecino.
    Sin referencia monotónica conocida no se atribuye vigencia al dato.
    """
    if type(vigencia_s) is not int or vigencia_s <= 0:
        raise ValueError("vigencia_s debe ser un entero positivo.")
    if id_contexto is not None and (not isinstance(id_contexto, str) or not id_contexto.strip()):
        raise ValueError("id_contexto debe ser una cadena no vacía o None.")
    registros = [r for r in registros if r["observacion"].get("id_ejecucion") == id_ejecucion]
    actual = registros[-1]["observacion"].get("id_contexto") if registros else None
    seleccionado = actual if id_contexto is None else id_contexto
    tramo = [r for r in registros if r["observacion"].get("id_contexto") == seleccionado]
    ultimo = tramo[-1]["observacion"] if tramo else None
    utilizable = next((r for r in reversed(tramo)
                       if seleccionado is not None
                       and r["observacion"]["estado"] in ("observacion_correcta", "observacion_parcial")
                       and r["observacion"]["fuente"] == "cache_arp_sysctl_macos"
                       and r["antiguedad_s"] is not None), None)
    edad = utilizable["antiguedad_s"] if utilizable else None
    estado = ultimo["estado"] if ultimo else None
    calidad_fuente = {
        "observacion_correcta": "completa",
        "observacion_parcial": "parcial",
    }.get(estado, "error_fuente" if ultimo else "no_disponible")
    return {
        "version_esquema": 1,
        "id_ejecucion": id_ejecucion,
        "id_contexto": seleccionado,
        "es_contexto_actual": seleccionado == actual if registros else None,
        "id_ultimo_intento": ultimo["id_observacion"] if ultimo else None,
        "estado_ultimo_intento": estado,
        "calidad_fuente": calidad_fuente,
        "id_ultima_utilizable": utilizable["observacion"]["id_observacion"] if utilizable else None,
        "estado_ultima_utilizable": utilizable["observacion"]["estado"] if utilizable else None,
        "antiguedad_s": edad,
        "referencia_antiguedad": "fin_consulta_arp" if utilizable else None,
        "vigencia_s": vigencia_s,
        "vigencia": "no_disponible" if edad is None else (
            "vigente" if edad < vigencia_s else "desactualizado"),
    }


def resumir_vecinos_arp(registros, *, id_ejecucion, vigencia_s, id_contexto=None):
    """Une recuento y calidad de la misma instantánea, sin sumar ciclos.

    Cuenta filas clasificadas como vecino, incluidas MAC incompletas; no deduce
    identidades de dispositivos ni fusiona filas por IPv4 o MAC. Una lectura
    parcial aporta solo las filas interpretables. Cero no confirma ausencia.
    """
    calidad = evaluar_calidad_arp(
        registros, id_ejecucion=id_ejecucion, vigencia_s=vigencia_s,
        id_contexto=id_contexto,
    )
    observacion = next((r["observacion"] for r in reversed(registros)
                        if calidad["id_ultima_utilizable"] is not None
                        and r["observacion"].get("id_ejecucion") == id_ejecucion
                        and r["observacion"].get("id_contexto") == calidad["id_contexto"]
                        and r["observacion"]["id_observacion"] == calidad["id_ultima_utilizable"]), None)
    cantidad = None
    resolucion = None
    if observacion is not None:
        cantidad = observacion["resumen"]["vecinos_candidatos"]
        incompletas = sum(e["categoria"] == "vecino" and e["mac"] is None
                         for e in observacion["entradas"])
        resolucion = {"resuelta": cantidad - incompletas, "incompleta": incompletas}
    return {
        "calidad": calidad,
        "vecinos": {
            "unidad": "filas_arp_categoria_vecino",
            "cantidad": cantidad,
            "resolucion_mac": resolucion,
            "id_observacion": calidad["id_ultima_utilizable"],
            "estado_observacion": calidad["estado_ultima_utilizable"],
            "es_ultimo_intento": (calidad["id_ultima_utilizable"] == calidad["id_ultimo_intento"]
                                   if observacion is not None else None),
            "fuente": observacion["fuente"] if observacion else None,
            "inicio_captura": observacion.get("inicio_captura") if observacion else None,
            "fin_captura": observacion.get("fin_captura") if observacion else None,
        },
    }
