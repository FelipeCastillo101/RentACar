from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from contextlib import nullcontext
from django.core import mail
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIRequestFactory
from transbank.common.integration_type import IntegrationType
from transbank.error.transbank_error import TransbankError

from .guest_access import crear_token_pago_invitado, validar_token_pago_invitado
from .views import (
    WebpayConfigurationError,
    comprobante_pdf,
    confirmar_pago_transbank,
    datos_reserva,
    enviar_confirmacion,
    opciones_webpay,
)


class WebpayOptionsTests(SimpleTestCase):
    @override_settings(
        WEBPAY_COMMERCE_CODE='commerce-test',
        WEBPAY_API_KEY='api-key-test',
        WEBPAY_ENV='INTEGRATION',
    )
    def test_usa_credenciales_configuradas_en_modo_integracion(self):
        opciones = opciones_webpay()

        self.assertEqual(opciones.commerce_code, 'commerce-test')
        self.assertEqual(opciones.api_key, 'api-key-test')
        self.assertIs(opciones.integration_type, IntegrationType.TEST)

    @override_settings(
        WEBPAY_COMMERCE_CODE='commerce-test',
        WEBPAY_API_KEY='api-key-test',
        WEBPAY_ENV='PRODUCTION',
    )
    def test_modo_produccion_se_activa_explicita_y_solamente(self):
        opciones = opciones_webpay()

        self.assertIs(opciones.integration_type, IntegrationType.LIVE)

    @override_settings(
        WEBPAY_COMMERCE_CODE='',
        WEBPAY_API_KEY='',
        WEBPAY_ENV='INTEGRATION',
    )
    def test_falla_claramente_si_faltan_credenciales(self):
        with self.assertRaises(WebpayConfigurationError):
            opciones_webpay()

    @override_settings(
        WEBPAY_COMMERCE_CODE='commerce-test',
        WEBPAY_API_KEY='api-key-test',
        WEBPAY_ENV='UNKNOWN',
    )
    def test_rechaza_un_modo_desconocido(self):
        with self.assertRaises(WebpayConfigurationError):
            opciones_webpay()


@override_settings(WEBPAY_FRONTEND_URL='https://rentcar.example')
class WebpayReturnTests(SimpleTestCase):
	def setUp(self):
		self.client = Client(enforce_csrf_checks=True)

	def test_webpay_post_callback_sin_csrf_redirige_a_resultado(self):
		respuesta = self.client.post(
			reverse('webpay_return'),
			{'token_ws': 'token-prueba'},
		)

		self.assertEqual(respuesta.status_code, 302)
		self.assertEqual(
			respuesta['Location'],
			'https://rentcar.example/resultado-pago?token_ws=token-prueba',
		)

	def test_callback_preserva_el_codigo_de_orden_cancelada(self):
		respuesta = self.client.post(
			reverse('webpay_return'),
			{'TBK_ORDEN_COMPRA': 'orden-42'},
		)

		self.assertEqual(
			respuesta['Location'],
			'https://rentcar.example/resultado-pago?TBK_ORDEN_COMPRA=orden-42',
		)


class GuestPaymentAccessTests(SimpleTestCase):
	def test_token_solo_da_acceso_a_su_reserva(self):
		token = crear_token_pago_invitado(42)

		self.assertTrue(validar_token_pago_invitado(token, 42))
		self.assertFalse(validar_token_pago_invitado(token, 43))
		self.assertFalse(validar_token_pago_invitado('token-invalido', 42))


class PagoWebpayConfirmacionTests(SimpleTestCase):
    def test_recupera_transaccion_autorizada_y_guarda_metodo_webpay(self):
        reserva = SimpleNamespace(
            id=42,
            estado='PENDIENTE_PAGO',
            save=Mock(),
        )
        orden = SimpleNamespace(
            id=6,
            reserva=reserva,
            total=Decimal('122000.00'),
            estado='PENDIENTE',
            save=Mock(),
        )
        pago = SimpleNamespace(
            pk=4,
            estado_pago='PENDIENTE',
            orden=orden,
            buy_order='6-1941874f',
            save=Mock(),
        )
        respuesta_transbank = {
            'response_code': 0,
            'status': 'AUTHORIZED',
            'buy_order': pago.buy_order,
            'amount': 122000,
            'payment_type_code': 'VC',
            'authorization_code': '123456',
        }
        query = Mock()
        query.select_related.return_value.first.return_value = pago
        transaccion = Mock()
        transaccion.commit.side_effect = TransbankError('Transacción ya confirmada.')
        transaccion.status.return_value = respuesta_transbank
        request = APIRequestFactory().post(
            '/api/confirmar-pago/',
            {'token_ws': 'token-de-prueba'},
            format='json',
        )

        with (
            patch('payments.views.Pago.objects.filter', return_value=query),
            patch('payments.views.puede_acceder_pago', return_value=True),
            patch('payments.views.opciones_webpay', return_value=object()),
            patch('payments.views.Transaction', return_value=transaccion),
            patch('payments.views.transaction.atomic', return_value=nullcontext()),
            patch('payments.views.HistorialEstadoReserva.objects.create'),
            patch('payments.views.crear_documento_tributario_pendiente'),
            patch('payments.views.enviar_confirmacion', return_value=True),
            patch('payments.views.comprobante_pdf', return_value=b'%PDF-test'),
            patch('payments.views.datos_reserva', return_value={'codigo': 'RC-42'}),
        ):
            respuesta = confirmar_pago_transbank(request)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['status'], 'aprobado')
        self.assertEqual(pago.metodo_pago, 'WEBPAY')
        self.assertEqual(pago.estado_pago, 'AUTORIZADO')
        transaccion.status.assert_called_once_with('token-de-prueba')


class ComprobanteReservaTests(TestCase):
	def setUp(self):
		categoria = SimpleNamespace(nombre='SUV', monto_garantia=900000)
		modelo = SimpleNamespace(marca='Toyota', nombre_modelo='RAV4', categoria=categoria)
		vehiculo = SimpleNamespace(
			patente='ABCD12',
		)
		cliente = SimpleNamespace(
			nombre='Ana',
			apellido='Perez',
			numero_documento='11111111-1',
			tipo_documento='RUT',
			correo='ana@example.com',
			telefono='999999999',
		)
		self.reserva = SimpleNamespace(
			id=42,
			codigo='RC-000042',
			estado='CONFIRMADA',
			modelo=modelo,
			vehiculo=vehiculo,
			cliente=cliente,
			fecha_hora_retiro=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
			fecha_hora_devolucion=datetime(2026, 1, 2, 18, tzinfo=timezone.utc),
			sucursal_retiro='Sucursal Viña del Mar',
			sucursal_devolucion='Sucursal Viña del Mar',
			total=45000,
		)

	def test_resumen_incluye_datos_principales(self):
		resumen = datos_reserva(self.reserva)

		self.assertEqual(resumen['codigo_reserva'], 42)
		self.assertEqual(resumen['codigo'], 'RC-000042')
		self.assertEqual(resumen['vehiculo'], 'Toyota RAV4')
		self.assertEqual(resumen['categoria'], 'SUV')
		self.assertEqual(resumen['cliente']['tipo_documento'], 'RUT')
		self.assertEqual(resumen['cliente']['email'], 'ana@example.com')

	def test_comprobante_es_un_pdf(self):
		pdf = comprobante_pdf(self.reserva)

		self.assertTrue(pdf.startswith(b'%PDF-1.4'))
		self.assertIn(b'COMPROBANTE DE RESERVA', pdf)
		self.assertIn(b'Reserva RC-000042', pdf)
		self.assertIn(b'VEH\\315CULO', pdf)
		self.assertIn(b'factura tributaria', pdf)
		self.assertIn(b'P\\341gina 1 de 1', pdf)

	@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
	def test_confirmacion_adjunta_contrato_consentimiento_y_comprobante(self):
		mail.outbox = []
		enviar_confirmacion(self.reserva, comprobante_pdf(self.reserva))

		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].to, ['ana@example.com'])
		self.assertEqual(
			[file[0] for file in mail.outbox[0].attachments],
			[
				'contrato-RC-000042.pdf',
				'consentimiento-RC-000042.pdf',
				'comprobante-reserva-RC-000042.pdf',
			],
		)
