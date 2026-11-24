import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from core.settings import load_workspace_env
from .dashboard import rango_periodo
from .policies import calcular_devolucion
from .serializers import CancelacionSerializer
from .views import CancelacionViewSet, ReservaViewSet
from .correos import (
    destinatarios_staff,
    notificar_cliente_cancelacion_cerrada_sin_reembolso,
    notificar_cliente_reembolso,
)
from .views import guardar_comprobante_reembolso


class CargaEnvTests(SimpleTestCase):
    def test_carga_valores_entre_comillas_y_respeta_el_entorno_existente(self):
        variable_existente = 'RENTCAR_TEST_ENV_EXISTENTE'
        variable_nueva = 'RENTCAR_TEST_ENV_NUEVA'

        with patch.dict(os.environ, {variable_existente: 'sistema'}, clear=False):
            os.environ.pop(variable_nueva, None)
            with TemporaryDirectory() as directorio:
                archivo_env = Path(directorio) / '.env'
                archivo_env.write_text(
                    f'{variable_existente}=archivo\n{variable_nueva}="valor con espacios"\n',
                    encoding='utf-8',
                )

                load_workspace_env(archivo_env)

            self.assertEqual(os.environ[variable_existente], 'sistema')
            self.assertEqual(os.environ[variable_nueva], 'valor con espacios')


class DashboardPeriodosTests(SimpleTestCase):
    def test_calcula_periodos_completos_desde_una_fecha_de_referencia(self):
        referencia = date(2026, 11, 23)

        self.assertEqual(rango_periodo('dia', referencia), (
            date(2026, 11, 23), date(2026, 11, 24),
        ))
        self.assertEqual(rango_periodo('semana', referencia), (
            date(2026, 11, 23), date(2026, 11, 30),
        ))
        self.assertEqual(rango_periodo('mes', referencia), (
            date(2026, 11, 1), date(2026, 12, 1),
        ))
        self.assertEqual(rango_periodo('trimestre', referencia), (
            date(2026, 10, 1), date(2027, 1, 1),
        ))
        self.assertEqual(rango_periodo('semestre', referencia), (
            date(2026, 7, 1), date(2027, 1, 1),
        ))
        self.assertEqual(rango_periodo('anio', referencia), (
            date(2026, 1, 1), date(2027, 1, 1),
        ))

    def test_rechaza_periodos_desconocidos(self):
        with self.assertRaises(ValueError):
            rango_periodo('decada', date(2026, 11, 23))


class DashboardEndpointTests(SimpleTestCase):
    def test_solo_personal_puede_consultar_el_dashboard(self):
        request = APIRequestFactory().get('/api/reservas/dashboard/')
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))

        response = ReservaViewSet.as_view({'get': 'dashboard'})(request)

        self.assertEqual(response.status_code, 403)

    def test_rechaza_periodos_y_fechas_invalidos(self):
        for parametros in (
            {'periodo': 'decada', 'fecha': '2026-11-23'},
            {'periodo': 'mes', 'fecha': 'fecha-invalida'},
        ):
            request = APIRequestFactory().get('/api/reservas/dashboard/', parametros)
            force_authenticate(
                request,
                user=SimpleNamespace(is_authenticated=True, rol='asistente'),
            )

            response = ReservaViewSet.as_view({'get': 'dashboard'})(request)

            self.assertEqual(response.status_code, 400)


class IdempotenciaCancelacionTests(SimpleTestCase):
    def test_reintento_devuelve_la_solicitud_activa_sin_crear_otra(self):
        reserva = SimpleNamespace(
            pk=42,
            codigo='RC-000042',
            cliente_id=7,
            estado='CANCELACION_EN_PROCESO',
        )
        solicitud = SimpleNamespace(id=19)
        serializador_nuevo = MagicMock()
        serializador_nuevo.validated_data = {'reserva': reserva}
        serializador_existente = MagicMock()
        serializador_existente.data = {'id': solicitud.id, 'estado': 'PENDIENTE'}
        request = APIRequestFactory().post(
            '/api/cancelaciones/',
            {'codigo_reserva': reserva.codigo},
            format='json',
        )
        force_authenticate(
            request,
            user=SimpleNamespace(id=reserva.cliente_id, is_authenticated=True),
        )

        with (
            patch('bookings.views.Reserva.objects.filter') as buscar_reserva,
            patch('bookings.views.Cancelacion.objects.filter') as buscar_cancelacion,
            patch.object(
                CancelacionViewSet,
                'get_serializer',
                side_effect=(serializador_nuevo, serializador_existente),
            ) as obtener_serializador,
        ):
            buscar_reserva.return_value.first.return_value = reserva
            buscar_cancelacion.return_value.order_by.return_value.first.return_value = solicitud

            response = CancelacionViewSet.as_view({'post': 'create'})(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['solicitud_preexistente'])
        self.assertEqual(response.data['estado'], 'PENDIENTE')
        self.assertEqual(obtener_serializador.call_count, 2)


class PoliticaDevolucionTests(SimpleTestCase):
    def setUp(self):
        self.reserva = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        self.retiro = self.reserva + timedelta(days=20)

    def cotizar(self, ahora):
        return calcular_devolucion(
            Decimal('100000'),
            Decimal('30000'),
            self.reserva,
            self.retiro,
            ahora,
        )

    def test_retracto_dentro_de_diez_dias_y_antes_del_retiro_devuelve_total(self):
        resultado = self.cotizar(self.reserva + timedelta(days=5))

        self.assertEqual(resultado['monto_devolucion'], Decimal('100000'))
        self.assertEqual(resultado['monto_retenido'], Decimal('0'))

    def test_cotiza_retencion_por_anticipacion_y_limita_al_pago(self):
        resultado = self.cotizar(self.retiro - timedelta(hours=30))

        self.assertEqual(resultado['monto_retenido'], Decimal('30000'))
        self.assertEqual(resultado['monto_devolucion'], Decimal('70000'))

        resultado = calcular_devolucion(
            Decimal('20000'),
            Decimal('30000'),
            self.reserva,
            self.retiro,
            self.retiro + timedelta(hours=1),
        )
        self.assertEqual(resultado['monto_retenido'], Decimal('20000'))
        self.assertEqual(resultado['monto_devolucion'], Decimal('0'))


class DestinatariosStaffTests(SimpleTestCase):
    def test_busca_roles_por_la_relacion_y_solo_una_vez_por_correo(self):
        with patch('bookings.correos.Trabajador.objects.filter') as filtrar_trabajadores:
            filtrar_trabajadores.return_value.values_list.return_value.distinct.return_value = [
                'admin@example.com',
            ]

            resultado = destinatarios_staff()

        self.assertEqual(resultado, ['admin@example.com'])
        filtrar_trabajadores.assert_called_once()
        filtro_roles = filtrar_trabajadores.call_args.args[0]
        self.assertEqual(filtro_roles.connector, 'OR')
        self.assertEqual(
            set(filtro_roles.children),
            {
                ('roles__codigo__iexact', 'admin'),
                ('roles__codigo__iexact', 'asistente'),
            },
        )
        self.assertEqual(filtrar_trabajadores.call_args.kwargs, {'activo': True})


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AvisoCancelacionTests(SimpleTestCase):
    def test_informa_cierre_sin_incluir_datos_bancarios(self):
        reserva = SimpleNamespace(
            codigo='RC-000042',
            total=Decimal('30000'),
            cliente=SimpleNamespace(correo='ana@example.com'),
        )
        cancelacion = SimpleNamespace(reserva=reserva)

        mail.outbox = []
        self.assertTrue(notificar_cliente_cancelacion_cerrada_sin_reembolso(cancelacion))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['ana@example.com'])
        self.assertIn('Devolución: $0', mail.outbox[0].body)
        self.assertNotIn('cuenta', mail.outbox[0].body.lower())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_cierre_con_transferencia_incluye_monto_codigo_y_comprobante(self):
        reserva = SimpleNamespace(
            codigo='RC-000042',
            cliente=SimpleNamespace(correo='ana@example.com'),
        )
        cancelacion = SimpleNamespace(reserva=reserva)
        mail.outbox = []

        with patch(
            'bookings.correos.default_storage.open',
            mock_open(read_data=b'%PDF-1.4 comprobante'),
        ):
            enviado = notificar_cliente_reembolso(
                cancelacion, Decimal('50000'), 'TRX-123', 'reembolsos/trx.pdf',
            )

        self.assertTrue(enviado)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('$50000', mail.outbox[0].body)
        self.assertIn('TRX-123', mail.outbox[0].body)
        self.assertEqual(
            mail.outbox[0].attachments[0][0],
            'comprobante-transferencia-RC-000042.pdf',
        )


class ComprobanteReembolsoTests(SimpleTestCase):
    def test_rechaza_archivo_que_finge_ser_pdf(self):
        archivo = SimpleUploadedFile(
            'comprobante.pdf',
            b'no es un pdf',
            content_type='application/pdf',
        )

        ruta, error = guardar_comprobante_reembolso(archivo)

        self.assertIsNone(ruta)
        self.assertIn('no coincide', error)


class AutenticacionReservaTests(SimpleTestCase):
    def test_crear_reserva_rechaza_solicitud_anonima(self):
        view = ReservaViewSet.as_view({'post': 'create'})
        request = APIRequestFactory().post('/api/reservas/', {}, format='json')

        response = view(request)

        self.assertIn(response.status_code, (401, 403))


class DocumentoTitularReembolsoTests(SimpleTestCase):
    def setUp(self):
        self.serializer = CancelacionSerializer()
        self.datos = {
            'reserva': SimpleNamespace(),
            'banco_destino': 'Banco de Chile',
            'tipo_cuenta': 'vista',
            'numero_cuenta': '123456789',
            'tipo_documento_titular': 'PASAPORTE',
            'rut_titular': 'P1234567',
            'nombre_titular': 'Juan Pérez',
        }

    def test_acepta_pasaporte_como_documento_de_titular(self):
        resultado = self.serializer.validate(self.datos.copy())

        self.assertEqual(resultado['tipo_documento_titular'], 'PASAPORTE')
        self.assertEqual(resultado['rut_titular'], 'P1234567')

    def test_no_acepta_solicitud_de_devolucion_sin_documento(self):
        datos = self.datos.copy()
        datos['tipo_documento_titular'] = 'RUT'
        datos['rut_titular'] = '123'

        with self.assertRaises(ValidationError):
            self.serializer.validate(datos)
