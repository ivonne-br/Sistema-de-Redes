// Transporte HTTP: recibe señales de cancelación y entrega estado del servicio y resúmenes y observaciones de ARP, ICMP o DNS/HTTPS a las vistas, sin calcular métricas.
export async function consultarObservaciones(signal) {
  const respuesta = await fetch('/api/v1/observaciones', { signal, cache: 'no-store' })
  if (!respuesta.ok) throw new Error(`No se pudieron consultar las observaciones (HTTP ${respuesta.status}).`)
  const cuerpo = await respuesta.json()
  const d = cuerpo.datos
  if (cuerpo.version_esquema !== 1 || !d || !Array.isArray(d.evidencia)
    || (d.principal != null && ['estado', 'titulo', 'explicacion', 'orientacion', 'fuente'].some(c => typeof d.principal[c] !== 'string'))
    || (d.nombres != null && ['estado', 'titulo', 'explicacion', 'orientacion'].some(c => typeof d.nombres[c] !== 'string'))
    || (d.incidencias != null && (typeof d.incidencias.mensaje !== 'string' || !Array.isArray(d.incidencias.eventos)
      || d.incidencias.eventos.some(e => !e || typeof e.id !== 'string' || typeof e.descripcion !== 'string')))
    || (d.tiempos_respuesta != null && (!Array.isArray(d.tiempos_respuesta)
      || d.tiempos_respuesta.some(f => !f || typeof f.mensaje !== 'string'
        || (f.estado === 'comparable' && (!Number.isFinite(f.anterior?.promedio_ms) || !Number.isFinite(f.reciente?.promedio_ms))))))
    || (d.recorrido != null && (!Array.isArray(d.recorrido.evidencia)
      || ['estado', 'titulo', 'explicacion', 'orientacion'].some(c => typeof d.recorrido[c] !== 'string')))
    || ['estado', 'titulo', 'explicacion', 'orientacion', 'limite'].some(c => typeof d[c] !== 'string')
    || (d.comparacion != null && (typeof d.comparacion.mensaje !== 'string'
      || !d.comparacion.reciente || !d.comparacion.anterior))) throw new Error('Las observaciones llegaron en un formato que no podemos mostrar.')
  return cuerpo
}

export async function consultarEstado(signal) {
  const respuesta = await fetch('/api/v1/estado', { signal, cache: 'no-store' })
  if (!respuesta.ok) throw new Error(`La API respondió HTTP ${respuesta.status}.`)
  const cuerpo = await respuesta.json()
  if (cuerpo.version_esquema !== 1 || typeof cuerpo.monitoreo?.estado !== 'string') {
    throw new Error('La API devolvió un estado no compatible.')
  }
  return cuerpo
}

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

export async function consultarWeb(signal) {
  const respuesta = await fetch('/api/v1/web', { signal, cache: 'no-store' })
  if (!respuesta.ok) throw new Error(`La API DNS/HTTPS respondió HTTP ${respuesta.status}.`)
  const cuerpo = await respuesta.json()
  if (cuerpo.version_esquema !== 1 || typeof cuerpo.datos?.estado !== 'string'
      || !Array.isArray(cuerpo.datos?.resultados)
      || cuerpo.datos.resultados.some(r => !r || !['dns', 'https'].includes(r.tipo)
        || typeof r.estado !== 'string' || typeof r.destino !== 'string'
        || !Array.isArray(r.direcciones))) {
    throw new Error('La API DNS/HTTPS devolvió un formato no compatible.')
  }
  return cuerpo
}
