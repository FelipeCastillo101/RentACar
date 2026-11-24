import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import date
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.mail.message import BadHeaderError
from django.db import IntegrityError, transaction
from django.utils import timezone
from smtplib import SMTPException
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.auth import MAX_AGE_SEGUNDOS, generar_token
from core.permissions import EsAdmin, EsStaff, es_trabajador
from fleet.models import Trabajador

from .models import CuentaCliente, Cliente, DocumentoCliente, LicenciaConducir
from .serializers import ClienteSerializer

logger = logging.getLogger(__name__)
CODIGO_TRABAJADOR_TTL = 10 * 60
CODIGO_TRABAJADOR_MAX_INTENTOS = 5
CODIGO_TRABAJADOR_ESPERA_REENVIO = 60


def datos_cliente(cliente):
    licencia_vencimiento = cliente.licencia_vencimiento
    return {
        'id': cliente.id,
        'tipo_documento': cliente.tipo_documento,
        'numero_documento': cliente.numero_documento,
        'correo': cliente.correo,
        'nombre': cliente.nombre,
        'apellido': cliente.apellido,
        'telefono': cliente.telefono,
        'fecha_nacimiento': cliente.fecha_nacimiento.isoformat() if cliente.fecha_nacimiento else None,
        'licencia': cliente.licencia,
        'licencia_vencimiento': licencia_vencimiento.isoformat() if licencia_vencimiento else None,
    }


def datos_trabajador(trabajador):
    return {
        'id': trabajador.id,
        'correo': trabajador.correo,
        'nombre': f'{trabajador.nombre} {trabajador.apellido}',
        'rol': trabajador.rol,
        'sucursal': trabajador.sucursal.nombre if trabajador.sucursal_id else None,
    }


def respuesta_sesion_cliente(cliente, status_code=status.HTTP_200_OK):
    return Response({
        'token': generar_token({'t': 'cliente', 'id': cliente.id}),
        'expires_in': MAX_AGE_SEGUNDOS,
        'tipo': 'cliente',
        'cliente': datos_cliente(cliente),
    }, status=status_code)


def clave_codigo_trabajador(challenge_id):
    return f'rentcar:staff-code:{challenge_id}'


def hash_codigo_trabajador(challenge_id, code):
    mensaje = f'{challenge_id}:{code}'.encode()
    return hmac.new(
        settings.SECRET_KEY.encode(),
        mensaje,
        hashlib.sha256,
    ).hexdigest()


def enviar_codigo_trabajador(trabajador):
    cooldown_key = f'rentcar:staff-code-cooldown:{trabajador.pk}'
    if not cache.add(cooldown_key, True, timeout=CODIGO_TRABAJADOR_ESPERA_REENVIO):
        return None

    challenge_id = secrets.token_urlsafe(32)
    code = f'{secrets.randbelow(1_000_000):06d}'
    cache.set(
        clave_codigo_trabajador(challenge_id),
        {
            'worker_id': trabajador.pk,
            'code_hash': hash_codigo_trabajador(challenge_id, code),
            'attempts': 0,
            'expires_at': time.time() + CODIGO_TRABAJADOR_TTL,
        },
        timeout=CODIGO_TRABAJADOR_TTL,
    )
    correo = EmailMessage(
        subject='Código de verificación para Rentacar',
        body=(
            f'Hola {trabajador.nombre},\n\n'
            f'Tu código de verificación es: {code}\n'
            'Este código vence en 10 minutos y solo puede usarse una vez.'
        ),
        to=[trabajador.correo],
    )
    try:
        enviado = correo.send(fail_silently=False)
        if not enviado:
            raise OSError('El backend de correo no aceptó el mensaje.')
    except (BadHeaderError, OSError, SMTPException):
        cache.delete(clave_codigo_trabajador(challenge_id))
        cache.delete(cooldown_key)
        raise
    return challenge_id


def validar_codigo_trabajador(challenge_id, code):
    clave = clave_codigo_trabajador(challenge_id)
    estado = cache.get(clave)
    if estado is None or estado['expires_at'] <= time.time():
        cache.delete(clave)
        return None, 'expired'
    if not re.fullmatch(r'\d{6}', code or ''):
        return None, 'invalid'
    if not hmac.compare_digest(
        estado['code_hash'],
        hash_codigo_trabajador(challenge_id, code),
    ):
        estado['attempts'] += 1
        if estado['attempts'] >= CODIGO_TRABAJADOR_MAX_INTENTOS:
            cache.delete(clave)
            return None, 'blocked'
        restante = max(1, int(estado['expires_at'] - time.time()))
        cache.set(clave, estado, timeout=restante)
        return None, 'invalid'

    cache.delete(clave)
    cache.delete(f'rentcar:staff-code-cooldown:{estado["worker_id"]}')
    return estado['worker_id'], None


@api_view(['POST'])
@permission_classes([AllowAny])
def iniciar_sesion_google(request):
    id_token = request.data.get('credential')
    if not isinstance(id_token, str) or not id_token.strip():
        return Response(
            {'detail': 'Falta la credencial de Google.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not settings.GOOGLE_CLIENT_ID:
        return Response(
            {'detail': 'El inicio con Google no está configurado en el servidor.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        respuesta = requests.get(
            'https://oauth2.googleapis.com/tokeninfo',
            params={'id_token': id_token},
            timeout=5,
        )
        respuesta.raise_for_status()
        identidad = respuesta.json()
    except requests.RequestException:
        return Response(
            {'detail': 'No fue posible verificar la identidad con Google.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except ValueError:
        return Response(
            {'detail': 'Google devolvió una respuesta de identidad inválida.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if (
        identidad.get('aud') != settings.GOOGLE_CLIENT_ID
        or identidad.get('email_verified') not in (True, 'true')
        or not identidad.get('sub')
        or not identidad.get('email')
    ):
        return Response(
            {'detail': 'La credencial de Google no es válida para esta aplicación.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    email = identidad['email'].strip().lower()
    nombre_completo = identidad.get('name', '').strip().split()
    nombre_google = identidad.get('given_name') or (
        nombre_completo[0] if nombre_completo else ''
    )
    apellido_google = identidad.get('family_name') or ' '.join(nombre_completo[1:])
    cuenta = CuentaCliente.objects.filter(
        proveedor='GOOGLE',
        proveedor_usuario_id=identidad['sub'],
    ).select_related('cliente').first()
    try:
        with transaction.atomic():
            cliente = (
                cuenta.cliente
                if cuenta
                else Cliente.objects.filter(correo__iexact=email).first()
            )
            if cliente is None:
                cliente = Cliente.objects.create(
                    correo=email,
                    nombre=(nombre_google or 'Cliente')[:70],
                    apellido=(apellido_google or 'Google')[:70],
                    fecha_registro=timezone.now(),
                    activo=True,
                )
            else:
                cambios = []
                if nombre_google and cliente.nombre != nombre_google:
                    cliente.nombre = nombre_google[:70]
                    cambios.append('nombre')
                if apellido_google and cliente.apellido != apellido_google:
                    cliente.apellido = apellido_google[:70]
                    cambios.append('apellido')
                if cliente.correo != email:
                    cliente.correo = email
                    cambios.append('correo')
                if cambios:
                    cliente.save(update_fields=cambios)
            if cuenta is None:
                CuentaCliente.objects.create(
                    cliente=cliente,
                    proveedor='GOOGLE',
                    proveedor_usuario_id=identidad['sub'],
                    correo_proveedor=email,
                    vinculada_at=timezone.now(),
                )
            if not cliente.activo:
                return Response(
                    {'detail': 'La cuenta está desactivada. Contacta con la empresa.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
    except IntegrityError:
        return Response(
            {'detail': 'No se pudo vincular la cuenta de Google. Vuelve a intentarlo.'},
            status=status.HTTP_409_CONFLICT,
        )
    return respuesta_sesion_cliente(cliente)


@api_view(['POST'])
@permission_classes([AllowAny])
def iniciar_sesion(request):
    correo = (request.data.get('correo') or '').strip()
    password = request.data.get('password') or ''
    if not correo or not password:
        return Response(
            {'detail': 'Correo y contraseña son obligatorios para trabajadores.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    trabajador = Trabajador.objects.filter(correo__iexact=correo, activo=True).first()
    if trabajador is not None and check_password(password, trabajador.password_hash):
        try:
            challenge_id = enviar_codigo_trabajador(trabajador)
        except (BadHeaderError, OSError, SMTPException):
            logger.exception(
                'No se pudo enviar el código de acceso al trabajador %s',
                trabajador.pk,
            )
            return Response(
                {'detail': 'No se pudo enviar el código de verificación. Intenta nuevamente.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if challenge_id is None:
            return Response(
                {'detail': 'Espera un minuto antes de solicitar otro código.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return Response({
            'challenge_id': challenge_id,
            'expires_in': CODIGO_TRABAJADOR_TTL,
        })

    return Response(
        {'detail': 'Credenciales de trabajador incorrectas. Los clientes deben ingresar con Google.'},
        status=status.HTTP_401_UNAUTHORIZED,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def verificar_codigo_trabajador(request):
    challenge_id = request.data.get('challenge_id')
    code = request.data.get('code')
    if (
        not isinstance(challenge_id, str)
        or not challenge_id
        or len(challenge_id) > 128
        or not isinstance(code, str)
    ):
        return Response(
            {'detail': 'El código de verificación es obligatorio.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    worker_id, error = validar_codigo_trabajador(challenge_id, code)
    if error == 'expired':
        return Response(
            {'detail': 'El código venció. Inicia sesión nuevamente para recibir otro.'},
            status=status.HTTP_410_GONE,
        )
    if error == 'blocked':
        return Response(
            {'detail': 'Se agotaron los intentos. Inicia sesión nuevamente para recibir otro código.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if error:
        return Response(
            {'detail': 'El código de verificación no es válido.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    trabajador = Trabajador.objects.filter(pk=worker_id, activo=True).first()
    if trabajador is None:
        return Response(
            {'detail': 'La cuenta de trabajador no existe o está desactivada.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return Response({
        'token': generar_token({
            't': 'trabajador',
            'id': trabajador.id,
            'rol': trabajador.rol,
        }),
        'expires_in': MAX_AGE_SEGUNDOS,
        'tipo': 'trabajador',
        'rol': trabajador.rol,
        'usuario': datos_trabajador(trabajador),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def registro_cliente(request):
    return Response(
        {'detail': 'Para crear una cuenta de cliente, continúa con Google.'},
        status=status.HTTP_405_METHOD_NOT_ALLOWED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cerrar_sesion(request):
    return Response({'detail': 'Sesión cerrada.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def yo(request):
    usuario = request.user
    if es_trabajador(usuario):
        return Response({'tipo': 'trabajador', 'rol': usuario.rol, 'usuario': datos_trabajador(usuario)})
    return Response({'tipo': 'cliente', 'cliente': datos_cliente(usuario)})


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all().order_by('apellido', 'nombre')
    serializer_class = ClienteSerializer

    def get_permissions(self):
        if self.action == 'registrar_o_buscar':
            return [EsStaff()]
        return [EsAdmin()]

    @action(detail=False, methods=['post'])
    def registrar_o_buscar(self, request):
        tipo = str(request.data.get('tipo_documento') or 'RUT').upper()
        numero = str(request.data.get('numero_documento') or '').strip()
        pais = str(request.data.get('pais_emision') or 'CHILE').strip().upper()
        if tipo not in {'RUT', 'PASAPORTE', 'OTRO'} or not numero:
            return Response(
                {'numero_documento': 'Indica el tipo y número de documento del cliente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        documento = DocumentoCliente.objects.filter(
            tipo_documento=tipo,
            numero_documento__iexact=numero,
        ).select_related('cliente').first()
        if documento:
            return Response(datos_cliente(documento.cliente))

        datos = request.data.copy()
        datos['correo'] = str(datos.get('correo') or '').strip().lower()
        datos['nombre'] = str(datos.get('nombre') or '').strip()
        datos['apellido'] = str(datos.get('apellido') or '').strip()
        datos.pop('tipo_documento', None)
        datos.pop('numero_documento', None)
        datos.pop('licencia', None)
        datos.pop('licencia_vencimiento', None)
        serializer = self.get_serializer(data=datos)
        serializer.is_valid(raise_exception=True)
        licencia = str(request.data.get('licencia') or '').strip()
        vencimiento = request.data.get('licencia_vencimiento')
        if not licencia or not vencimiento:
            return Response(
                {'licencia': 'La licencia y su vencimiento son obligatorios para una reserva presencial.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            vence = date.fromisoformat(vencimiento)
        except (TypeError, ValueError):
            return Response(
                {'licencia_vencimiento': 'Usa el formato de fecha YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if vence <= timezone.localdate():
            return Response(
                {'licencia_vencimiento': 'La licencia debe estar vigente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                cliente = serializer.save(fecha_registro=timezone.now())
                DocumentoCliente.objects.create(
                    cliente=cliente,
                    tipo_documento=tipo,
                    numero_documento=numero,
                    pais_emision=pais,
                    es_principal=True,
                )
                LicenciaConducir.objects.create(
                    cliente=cliente,
                    numero_licencia=licencia,
                    pais_emision='Chile',
                    fecha_vencimiento=vence,
                )
        except IntegrityError:
            return Response(
                {'detail': 'El documento, correo o licencia ya está registrado.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(datos_cliente(cliente), status=status.HTTP_201_CREATED)
