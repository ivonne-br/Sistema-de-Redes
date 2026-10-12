// Transporte HTTP: recibe señales de cancelación y entrega resúmenes ARP o conectividad a las vistas, sin calcular métricas.
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

export async function consultarConectividad(signal) {
  const respuesta = await fetch('/api/v1/conectividad', { signal, cache: 'no-store' })
  if (!respuesta.ok) throw new Error(`La API de conectividad respondió HTTP ${respuesta.status}.`)
  const cuerpo = await respuesta.json()
  if (cuerpo.version_esquema !== 1 || typeof cuerpo.datos?.estado !== 'string'
      || !Array.isArray(cuerpo.datos?.destinos)
      || cuerpo.datos.destinos.some(d => !d || !d.rtt_ms || typeof d.calidad !== 'string')) {
    throw new Error('La API de conectividad devolvió un formato no compatible.')
  }
  return cuerpo
}
