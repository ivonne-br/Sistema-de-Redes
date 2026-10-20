"""Compara asociaciones ARP en la memoria retenida; no confirma conectividad."""

from uuid import NAMESPACE_URL, uuid5


def comparar_presencia_arp(registros, *, id_ejecucion, id_contexto,
                          vigencia_s=90, ausencias=3):
    """Reconstruye estados y eventos del tramo, sin conservar estado adicional.

    Identidad contextual: IPv4 y MAC resuelta; no identidad física de equipo.
    Los eventos son una vista de la ventana retenida, con IDs deterministas para
    que consultar dos veces no produzca eventos nuevos. Al perder la referencia
    por retención/capacidad se establece una nueva base, sin inventar reapariciones.
    """
    for nombre, valor in (("vigencia_s", vigencia_s), ("ausencias", ausencias)):
        if type(valor) is not int or valor <= 0:
            raise ValueError(f"{nombre} debe ser un entero positivo.")
    tramo = [r for r in registros if id_contexto is not None
             and r["observacion"].get("id_ejecucion") == id_ejecucion
             and r["observacion"].get("id_contexto") == id_contexto]
    asociaciones, eventos, vistos = {}, [], set()
    referencia = None
    anterior = None
    ultimo = None

    def evento(tipo, clave, observacion):
        identificador = f"arp:{id_ejecucion}:{id_contexto}:{observacion['id_observacion']}:{clave}:{tipo}"
        eventos.append({
            "id_evento": str(uuid5(NAMESPACE_URL, identificador)),
            "tipo": tipo, "ipv4": clave[0], "mac": clave[1],
            "id_observacion": observacion["id_observacion"],
            "ciclo": observacion["ciclo"],
            "fin_captura": observacion.get("fin_captura"),
        })

    for registro in tramo:
        o = registro["observacion"]
        ciclo = o["ciclo"]
        if o["id_observacion"] in vistos or (anterior is not None and ciclo <= anterior):
            continue
        vistos.add(o["id_observacion"])
        salto = anterior is not None and ciclo != anterior + 1
        if (ultimo is not None and ultimo["antiguedad_s"] is not None
                and registro["antiguedad_s"] is not None
                and ultimo["antiguedad_s"] - registro["antiguedad_s"] >= vigencia_s):
            salto = True  # Una pausa prolongada rompe la continuidad aunque no falte un número.
        anterior = ciclo
        ultimo = registro
        utilizable = (o["fuente"] == "cache_arp_sysctl_macos"
                      and o["estado"] in ("observacion_correcta", "observacion_parcial")
                      and registro["antiguedad_s"] is not None)
        completa = utilizable and o["estado"] == "observacion_correcta"
        inicial = referencia is None
        if utilizable and inicial:
            referencia = o["id_observacion"]
        presentes = {(e["ipv4"], e["mac"]) for e in o["entradas"]
                     if utilizable and e.get("categoria") == "vecino" and e["mac"] is not None}
        incompletas = {e["ipv4"] for e in o["entradas"]
                      if utilizable and e.get("categoria") == "vecino" and e["mac"] is None}
        for clave in sorted(presentes):
            if clave not in asociaciones:
                asociaciones[clave] = {
                    "ipv4": clave[0], "mac": clave[1],
                    "id_primera_observacion": o["id_observacion"],
                    "ausencia_emitida": False,
                }
                evento("referencia_inicial" if inicial else "primera_observacion", clave, o)
            dato = asociaciones[clave]
            if dato["ausencia_emitida"]:
                evento("reaparicion", clave, o)
            dato.update(estado="observado", ausencias_consecutivas=0,
                        ausencia_emitida=False, id_ultima_observacion=o["id_observacion"],
                        fin_ultima_captura=o.get("fin_captura"),
                        antiguedad_s=registro["antiguedad_s"])
        for clave, dato in asociaciones.items():
            if clave in presentes:
                continue
            if salto or not completa or clave[0] in incompletas:
                dato["ausencias_consecutivas"] = 0
            if completa and clave[0] not in incompletas:
                dato["ausencias_consecutivas"] += 1
            dato["estado"] = "indeterminado"
            if dato["ausencias_consecutivas"] >= ausencias:
                dato["estado"] = "no_observado_recientemente"
                if not dato["ausencia_emitida"]:
                    evento("ausencia_observada", clave, o)
                    dato["ausencia_emitida"] = True

    reciente = (ultimo is not None and ultimo["antiguedad_s"] is not None
                and ultimo["antiguedad_s"] < vigencia_s)
    resultado = []
    for clave in sorted(asociaciones):
        dato = dict(asociaciones[clave])
        dato.pop("ausencia_emitida")
        if not reciente or (dato["estado"] == "observado" and dato["antiguedad_s"] >= vigencia_s):
            dato["estado"] = "indeterminado"
        resultado.append(dato)
    return {
        "version_esquema": 1, "id_ejecucion": id_ejecucion, "id_contexto": id_contexto,
        "unidad": "asociaciones_ipv4_mac_en_contexto",
        "ausencias_requeridas": ausencias,
        "id_referencia_inicial": referencia,
        "id_ultimo_intento": ultimo["observacion"]["id_observacion"] if ultimo else None,
        "asociaciones": resultado, "eventos_en_memoria": eventos,
    }
