// Transporte HTTP: recibe señales de cancelación y entrega resúmenes ARP a las vistas, sin calcular métricas.
export async function consultarResumen(signal) {
  const respuesta = await fetch('/api/v1/arp/resumen', { signal, cache: 'no-store' })
  if (!respuesta.ok) throw new Error(`La API respondió HTTP ${respuesta.status}.`)
  const cuerpo = await respuesta.json()
  if (cuerpo.version_esquema !== 1 || !cuerpo.monitoreo || !cuerpo.datos?.calidad
      || !cuerpo.datos?.vecinos || !Array.isArray(cuerpo.datos?.presencia?.asociaciones)
      || !Array.isArray(cuerpo.datos?.presencia?.eventos_en_memoria)) {
    throw new Error('La API devolvió un formato no compatible.')
  }
  return cuerpo
}
