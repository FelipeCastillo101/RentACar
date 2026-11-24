import re
from types import SimpleNamespace
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from core.auth import MAX_AGE_SEGUNDOS, leer_token
from .views import (
    enviar_codigo_trabajador,
    iniciar_sesion,
    validar_codigo_trabajador,
    verificar_codigo_trabajador,
)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SECRET_KEY='staff-otp-test-secret',
)
class VerificacionTrabajadorTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.trabajador = SimpleNamespace(
            pk=12,
            id=12,
            nombre='Ana',
            apellido='Perez',
            correo='ana@example.com',
            password_hash='hash-de-prueba',
            rol='admin',
            sucursal_id=None,
        )
        self.factory = APIRequestFactory()

    def tearDown(self):
        cache.clear()

    def test_codigo_enviado_es_de_un_solo_uso_y_llega_por_correo(self):
        challenge_id = enviar_codigo_trabajador(self.trabajador)
        codigo = re.search(
            r'Tu código de verificación es: (\d{6})',
            mail.outbox[0].body,
        ).group(1)

        self.assertEqual(mail.outbox[0].to, ['ana@example.com'])
        self.assertEqual(
            validar_codigo_trabajador(challenge_id, codigo),
            (12, None),
        )
        self.assertEqual(
            validar_codigo_trabajador(challenge_id, codigo),
            (None, 'expired'),
        )

    def test_codigo_bloquea_el_reto_despues_de_cinco_intentos(self):
        challenge_id = enviar_codigo_trabajador(self.trabajador)
        codigo_correcto = re.search(
            r'Tu código de verificación es: (\d{6})',
            mail.outbox[0].body,
        ).group(1)
        codigo_incorrecto = '000000' if codigo_correcto != '000000' else '000001'

        for _ in range(4):
            self.assertEqual(
                validar_codigo_trabajador(challenge_id, codigo_incorrecto)[1],
                'invalid',
            )

        self.assertEqual(
            validar_codigo_trabajador(challenge_id, codigo_incorrecto),
            (None, 'blocked'),
        )

    def test_limita_el_reenvio_del_codigo(self):
        self.assertIsNotNone(enviar_codigo_trabajador(self.trabajador))
        self.assertIsNone(enviar_codigo_trabajador(self.trabajador))
        self.assertEqual(len(mail.outbox), 1)

    def test_acceso_de_personal_exige_codigo_antes_de_emitir_token_de_una_hora(self):
        with (
            patch('users.views.Trabajador.objects.filter') as buscar_trabajador,
            patch('users.views.check_password', return_value=True),
        ):
            buscar_trabajador.return_value.first.return_value = self.trabajador
            respuesta_login = iniciar_sesion(self.factory.post(
                '/api/auth/login/',
                {'correo': self.trabajador.correo, 'password': 'clave-de-prueba'},
                format='json',
            ))
            self.assertNotIn('token', respuesta_login.data)
            codigo = re.search(
                r'Tu código de verificación es: (\d{6})',
                mail.outbox[0].body,
            ).group(1)

            respuesta_codigo = verificar_codigo_trabajador(self.factory.post(
                '/api/auth/verify-code/',
                {
                    'challenge_id': respuesta_login.data['challenge_id'],
                    'code': codigo,
                },
                format='json',
            ))

        payload = leer_token(respuesta_codigo.data['token'])
        self.assertEqual(payload['t'], 'trabajador')
        self.assertEqual(payload['id'], self.trabajador.id)
        self.assertEqual(respuesta_codigo.data['expires_in'], MAX_AGE_SEGUNDOS)
