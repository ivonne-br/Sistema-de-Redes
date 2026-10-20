"""Permisos temporales, preparación, envío único y verificación de cambios.

Entradas: sesión privada del monitor, adaptador y decisión explícita de la API.
Salidas: resumen sin secretos para Vue. Planes y ajustes viven solo en RAM;
MonitoreoRouter serializa solicitudes y comprueba contexto antes de cada petición.
"""
from copy import deepcopy
import secrets

from backend.router_adaptadores import mac, texto_panel


class AdministracionRouter:
    def __init__(self, reloj):
        self.reloj = reloj

    def estado(self, sesion):
        permiso = sesion.get('administracion')
        if permiso and self.reloj() >= permiso['vence']:
            sesion.pop('administracion', None)
            permiso = None
        if not permiso:
            return {'autorizada': False}
        plan = permiso.get('plan')
        if plan and self.reloj() >= plan['vence']:
            permiso.pop('plan', None)
        return {'autorizada': True, 'restante_s': max(0, permiso['vence'] - self.reloj()),
                'resultado': deepcopy(permiso.get('resultado'))}

    def actuar(self, sesion, adaptador, accion, datos, propias=()):
        """Nunca concede escritura a partir del permiso de lectura por sí solo."""
        self.estado(sesion)
        if accion == 'finalizar':
            sesion.pop('administracion', None)
            return {'autorizada': False}
        if accion == 'autorizar':
            if set(datos) != {'confirmado'} or datos['confirmado'] is not True:
                raise ValueError('Confirma el permiso administrativo temporal.')
            adaptador.comprobar()
            sesion['administracion'] = {'vence': min(sesion['vence'], self.reloj() + 300)}
            return self.estado(sesion)
        permiso = sesion.get('administracion')
        if not permiso:
            raise PermissionError('Autoriza la administración durante cinco minutos.')
        if accion == 'cancelar':
            permiso.pop('plan', None)
            return {'estado': 'cancelado'}
        usuario = adaptador.comprobar()
        if accion == 'consultar':
            salida = {'identidad': getattr(adaptador, 'identidad', {}), 'wifi': None, 'bloqueo': None, 'avisos': []}
            for tipo in ('wifi', 'bloqueo'):
                try:
                    actual = adaptador.leer(tipo)
                    if tipo == 'wifi':
                        salida[tipo] = [{'banda': b, 'nombre': actual.get('wifi_ssid' + s),
                                         'activa': actual['wifi_network_onoff' + s] == '1'}
                                        for b, s in (('2.4', ''), ('5', '_5g'))]
                    else:
                        salida[tipo] = actual
                except ValueError as error:
                    salida['avisos'].append(str(error))
            return salida
        if accion == 'preparar':
            # Un nuevo plan sustituye al anterior; no acumula contraseñas o confirmaciones.
            permiso.pop('plan', None)
            if permiso.get('resultado', {}).get('estado') in ('incierto', 'aceptado_sin_verificar'):
                raise ValueError('Comprueba primero el resultado pendiente; no se repetirá automáticamente.')
            operacion = datos.get('operacion')
            tipo = 'wifi' if operacion in ('nombre', 'password') else 'bloqueo'
            if operacion not in ('nombre', 'password', 'bloquear', 'desbloquear'):
                raise ValueError('Operación no compatible.')
            actual = adaptador.leer(tipo)
            esperado = deepcopy(actual)
            if tipo == 'wifi':
                if set(datos) != {'operacion', 'banda', 'valor'} or datos['banda'] not in ('2.4', '5'):
                    raise ValueError('Selecciona una banda y un cambio.')
                sufijo = '_5g' if datos['banda'] == '5' else ''
                if actual['wifi_network_onoff' + sufijo] != '1':
                    raise ValueError('La banda está apagada; no se encenderá automáticamente.')
                valor = datos['valor']
                if not isinstance(valor, str) or not valor.strip() or any(ord(c) < 32 or ord(c) > 126 for c in valor):
                    raise ValueError('Usa caracteres visibles sin acentos para este panel.')
                texto_panel(valor)
                if operacion == 'nombre':
                    if len(valor.encode('utf-8')) > 32:
                        raise ValueError('El nombre admite hasta 32 caracteres.')
                    campo = 'wifi_ssid' + sufijo
                    resumen = f'Cambiar el nombre de {actual[campo]} ({datos["banda"]} GHz) a {valor}.'
                else:
                    if not 8 <= len(valor) <= 63:
                        raise ValueError('La contraseña Wi-Fi debe tener entre 8 y 63 caracteres.')
                    campo = 'wifi_password' + sufijo
                    resumen = f'Cambiar la contraseña Wi-Fi de {actual["wifi_ssid" + sufijo]} ({datos["banda"]} GHz).'
                if actual[campo] == valor:
                    raise ValueError('El valor ya está configurado; no hay un cambio que enviar.')
                esperado[campo] = valor
                efecto = 'Los equipos de esa banda pueden desconectarse. Reconéctalos con el nombre y la contraseña nuevos. Guarda esos datos antes de confirmar.'
            else:
                if set(datos) != {'operacion', 'mac'}:
                    raise ValueError('Selecciona el dispositivo por su dirección MAC.')
                objetivo = mac(datos['mac'])
                encontrados = [f for f in actual['lista'] if mac(f['macfilter_mac']) == objetivo]
                if operacion == 'bloquear':
                    if not propias:
                        raise ValueError('No se pudo identificar esta computadora en DHCP para evitar bloquearla. Revisa el panel del router.')
                    if objetivo in propias:
                        raise ValueError('No se permite bloquear la computadora que administra la red.')
                    if encontrados:
                        raise ValueError('Ya existe una regla para ese dispositivo.')
                    if actual['activo'] == '0' and actual['lista']:
                        raise ValueError('Hay reglas inactivas: activarlas afectaría otros equipos. Revísalas en el panel.')
                    if len(actual['lista']) >= 16:
                        raise ValueError('Usa el panel para revisar la capacidad de esta lista.')
                    esperado['lista'].append({'macfilter_name': 'Equipo', 'macfilter_mac': objetivo})
                    resumen = f'Bloquear el acceso Wi-Fi de {objetivo}.'
                else:
                    if actual['activo'] != '1' or not encontrados:
                        raise ValueError('No hay una restricción activa compatible para retirar.')
                    esperado['lista'] = [f for f in actual['lista'] if mac(f['macfilter_mac']) != objetivo]
                    resumen = f'Retirar el bloqueo Wi-Fi de {objetivo}.'
                esperado['activo'] = '1'
                efecto = 'La regla afecta al acceso Wi-Fi de esa dirección. No apaga el equipo ni controla Ethernet. Retirarla no garantiza que el dispositivo se reconecte.'
            plan = {'id': secrets.token_urlsafe(24), 'vence': min(permiso['vence'], self.reloj() + 60),
                    'tipo': tipo, 'antes': actual, 'despues': esperado, 'resumen': resumen, 'efecto': efecto}
            permiso['plan'] = plan
            return {k: plan[k] for k in ('id', 'resumen', 'efecto')} | {'restante_s': plan['vence'] - self.reloj()}
        if accion == 'confirmar':
            if set(datos) != {'id', 'confirmado'} or datos['confirmado'] is not True:
                raise ValueError('Confirma el cambio concreto mostrado.')
            resultado = permiso.get('resultado')
            if resultado and resultado['id'] == datos['id']:
                return deepcopy(resultado)
            plan = permiso.get('plan')
            if not plan or datos['id'] != plan['id'] or self.reloj() >= plan['vence']:
                raise ValueError('La confirmación caducó o corresponde a otro cambio. Prepáralo de nuevo.')
            actual = adaptador.leer(plan['tipo'])
            if not mismos_ajustes(plan['tipo'], actual, plan['antes']):
                permiso.pop('plan', None)
                raise ValueError('La configuración cambió después de preparar el cambio. Revísala otra vez.')
            # Consume antes del primer POST; una respuesta perdida nunca causa otro envío.
            permiso.pop('plan')
            resultado = {'id': plan['id'], 'estado': 'incierto', 'resumen': plan['resumen']}
            permiso['resultado'] = resultado
            permiso['verificacion'] = {'tipo': plan['tipo'], 'despues': plan['despues']}
            try:
                aceptado = adaptador.escribir(plan['tipo'], plan['despues'], usuario)
                resultado['estado'] = 'aceptado_sin_verificar' if aceptado else 'rechazado'
            except Exception:
                pass
            self._verificar(permiso, adaptador)
            return deepcopy(resultado)
        if accion == 'verificar':
            self._verificar(permiso, adaptador)
            return deepcopy(permiso.get('resultado')) or {'estado': 'sin_operacion'}
        raise ValueError('Acción no compatible.')

    def _verificar(self, permiso, adaptador):
        """Solo GET: compara todos los ajustes conservados, sin mostrar contraseñas."""
        prueba = permiso.get('verificacion')
        if not prueba:
            return
        try:
            if mismos_ajustes(prueba['tipo'], adaptador.leer(prueba['tipo']), prueba['despues']):
                permiso['resultado']['estado'] = 'verificado'
                permiso.pop('verificacion', None)
        except Exception:
            pass


def mismos_ajustes(tipo, primero, segundo):
    """El orden y las mayúsculas de una lista MAC no cambian sus restricciones."""
    if tipo == 'wifi':
        return primero == segundo
    def reglas(config):
        return sorted((mac(f['macfilter_mac']), f['macfilter_name']) for f in config['lista'])
    return primero['activo'] == segundo['activo'] and reglas(primero) == reglas(segundo)
