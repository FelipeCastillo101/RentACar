"""Autenticación por token firmado (sin tabla extra ni dependencias nuevas).

El token se crea con TimestampSigner de Django y guarda el tipo de cuenta:
{'t': 'cliente'|'trabajador', 'id': <id>[, 'rol': ...]} y expira a la hora.
El frontend lo envía en la cabecera:  Authorization: Token <token>
"""
import json

from django.core.signing import BadSignature, TimestampSigner
from rest_framework import authentication, exceptions

_sesor = TimestampSigner(salt='rentcar.token')
MAX_AGE_SEGUNDOS = 60 * 60


def generar_token(payload: dict) -> str:
    return _sesor.sign(json.dumps(payload, separators=(',', ':'), ensure_ascii=False))


def leer_token(token: str) -> dict:
    try:
        crudo = _sesor.unsign(token, max_age=MAX_AGE_SEGUNDOS)
    except BadSignature as error:
        raise exceptions.AuthenticationFailed('Sesión inválida o expirada; vuelve a iniciar sesión.') from error
    return json.loads(crudo)


class TokenAutenticacion(authentication.BaseAuthentication):
    keyword = 'Token'

    def authenticate(self, request):
        cabecera = request.headers.get('Authorization', '')
        if not cabecera:
            return None

        partes = cabecera.split()
        if len(partes) != 2 or partes[0] != self.keyword:
            raise exceptions.AuthenticationFailed('Cabecera Authorization inválida (usa "Token <token>").')

        datos = leer_token(partes[1])

        if datos.get('t') == 'trabajador':
            from fleet.models import Trabajador
            objeto = Trabajador.objects.filter(id=datos.get('id'), activo=True).first()
            if objeto is None:
                raise exceptions.AuthenticationFailed('Cuenta de trabajador inexistente o desactivada.')
            return (objeto, partes[1])

        if datos.get('t') == 'cliente':
            from users.models import Cliente
            objeto = Cliente.objects.filter(id=datos.get('id'), activo=True).first()
            if objeto is None:
                raise exceptions.AuthenticationFailed('Cuenta de cliente inexistente o desactivada.')
            return (objeto, partes[1])

        raise exceptions.AuthenticationFailed('Tipo de cuenta desconocido en el token.')
