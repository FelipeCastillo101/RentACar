import logging
import uuid
from decimal import Decimal, InvalidOperation
from smtplib import SMTPException
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.message import BadHeaderError
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from transbank.common.integration_type import IntegrationType
from transbank.error.transbank_error import TransbankError
from transbank.webpay.webpay_plus.transaction import Transaction
from transbank.common.options import WebpayOptions

from bookings.models import HistorialEstadoReserva, Reserva
from core.documentos import (
    consentimiento_lineas,
    contrato_lineas,
    fecha_documento,
    pdf_desde_lineas,
    pesos_documento,
)
from core.permissions import EsStaff, es_trabajador
from .guest_access import validar_token_pago_invitado

from .models import DocumentoTributario, OrdenCompra, Pago
from .serializers import PagoSerializer


logger = logging.getLogger(__name__)

def datos_reserva(reserva):
    modelo = reserva.modelo
    orden = getattr(reserva, 'ordencompra', None)
    detalle_orden = [
        {
            'descripcion': detalle.descripcion,
            'cantidad': str(detalle.cantidad),
            'precio_unitario': str(detalle.precio_unitario),
            'subtotal': str(detalle.subtotal),
        }
        for detalle in orden.detalles.all()
    ] if orden else []
    registro_contrato = getattr(reserva, 'contrato_set', None)
    aceptacion = (
        registro_contrato.filter(aceptado=True)
        .select_related('contrato_version')
        .order_by('-fecha_aceptacion')
        .first()
        if registro_contrato is not None
        else None
    )
    return {
        'reserva_id': reserva.id,
        'codigo': reserva.codigo,
        'codigo_reserva': reserva.id,
        'estado': reserva.estado,
        'codigo_orden': orden.codigo_orden if orden else None,
        'detalle_orden': detalle_orden,
        'subtotal': str(orden.subtotal if orden else getattr(reserva, 'subtotal', reserva.total)),
        'descuento': str(orden.descuento if orden else getattr(reserva, 'descuento', 0)),
        'vehiculo': f'{modelo.marca} {modelo.nombre_modelo}',
        'patente': reserva.vehiculo.patente,
        'categoria': modelo.categoria.nombre,
        'fecha_hora_retiro': reserva.fecha_hora_retiro.isoformat(),
        'fecha_hora_devolucion': reserva.fecha_hora_devolucion.isoformat(),
        'sucursal_retiro': str(reserva.sucursal_retiro),
        'sucursal_devolucion': str(reserva.sucursal_devolucion),
        'total_pagado': str(reserva.total),
        'garantia_monto': str(modelo.categoria.monto_garantia),
        'cliente': {
            'nombre': reserva.cliente.nombre,
            'apellido': reserva.cliente.apellido,
            'tipo_documento': getattr(reserva.cliente, 'tipo_documento', None),
            'documento': reserva.cliente.numero_documento,
            'email': reserva.cliente.correo,
            'telefono': reserva.cliente.telefono,
        },
        'fecha_firma': aceptacion.fecha_aceptacion if aceptacion else None,
        'ip_cliente': aceptacion.ip_cliente if aceptacion else None,
        'medio_aceptacion': aceptacion.medio_aceptacion if aceptacion else None,
        'version_contrato': (
            aceptacion.contrato_version.numero_version if aceptacion else None
        ),
    }


def comprobante_pdf(reserva):
    info = datos_reserva(reserva)
    lineas = [
        'COMPROBANTE DE RESERVA',
        f"Código de reserva: {info['codigo']}",
        '',
        'ESTADO',
        'Pago confirmado' if info['estado'] == 'CONFIRMADA' else info['estado'].replace('_', ' ').capitalize(),
        *([f"Código de orden: {info['codigo_orden']}"] if info['codigo_orden'] else []),
        '',
        'ARRENDATARIO',
        f"Nombre: {info['cliente']['nombre']} {info['cliente']['apellido']}",
        f"Documento: {info['cliente']['tipo_documento'] or 'Documento'} · {info['cliente']['documento'] or 'Por verificar en sucursal'}",
        f"Correo: {info['cliente']['email']}",
        '',
        'VEHÍCULO',
        f"Modelo: {info['vehiculo']} · Patente: {info['patente']}",
        f"Categoría: {info['categoria']}",
        '',
        'RETIRO Y DEVOLUCIÓN',
        f"Retiro: {fecha_documento(info['fecha_hora_retiro'])} · {info['sucursal_retiro']}",
        f"Devolución: {fecha_documento(info['fecha_hora_devolucion'])} · {info['sucursal_devolucion']}",
        '',
        'PAGO Y GARANTÍA',
        'Detalle de cobro:',
        *(
            [
                f"{item['descripcion']} · {item['cantidad']} × "
                f"{pesos_documento(item['precio_unitario'])} = "
                f"{pesos_documento(item['subtotal'])}"
                for item in info['detalle_orden']
            ]
            or ['Detalle no disponible para esta reserva.']
        ),
        f"Subtotal: {pesos_documento(info['subtotal'])}",
        f"Descuento: {pesos_documento(info['descuento'])}",
        f"Total pagado: {pesos_documento(info['total_pagado'])}",
        f"Garantía a presentar en sucursal: {pesos_documento(info['garantia_monto'])}",
        '',
        'INFORMACIÓN TRIBUTARIA',
        'Este comprobante acredita los datos de la reserva; no es una boleta ni',
        'una factura tributaria.',
    ]
    return pdf_desde_lineas(lineas)


def enviar_confirmacion(reserva, pdf):
    info = datos_reserva(reserva)
    correo = EmailMessage(
        subject=f'Reserva confirmada - {info["codigo"]}',
        body=(
            f'Su reserva {info["codigo"]} fue confirmada y pagada.\n\n'
            f'Vehículo: {info["vehiculo"]} ({info["patente"]})\n'
            f'Retiro: {info["fecha_hora_retiro"]} en {info["sucursal_retiro"]}\n'
            f'Devolución: {info["fecha_hora_devolucion"]}\n'
            f'Total pagado: ${info["total_pagado"]}\n'
            f'Garantía a presentar en sucursal: ${info["garantia_monto"]}\n\n'
            'Adjuntamos el contrato firmado y un comprobante de reserva. '
            'El comprobante no reemplaza la boleta o factura tributaria; '
            'su emisión depende de la integración con el proveedor DTE.\n\n'
            'Para retirar el vehículo, presenta tu documento de identidad, '
            'licencia vigente, código de reserva y tarjeta de crédito para garantía. '
            'La empresa no almacena datos de tarjetas.'
        ),
        to=[reserva.cliente.correo],
    )
    correo.attach(
        f'contrato-{info["codigo"]}.pdf',
        pdf_desde_lineas(contrato_lineas(info)),
        'application/pdf',
    )
    correo.attach(
        f'consentimiento-{info["codigo"]}.pdf',
        pdf_desde_lineas(consentimiento_lineas(info)),
        'application/pdf',
    )
    correo.attach(f'comprobante-reserva-{info["codigo"]}.pdf', pdf, 'application/pdf')
    return correo.send(fail_silently=False)


class WebpayConfigurationError(Exception):
    pass


def opciones_webpay():
    commerce_code = settings.WEBPAY_COMMERCE_CODE
    api_key = settings.WEBPAY_API_KEY
    if not commerce_code or not api_key:
        raise WebpayConfigurationError(
            'Define WEBPAY_COMMERCE_CODE y WEBPAY_API_KEY.'
        )

    tipos_integracion = {
        'INTEGRATION': IntegrationType.TEST,
        'TEST': IntegrationType.TEST,
        'PRODUCTION': IntegrationType.LIVE,
        'LIVE': IntegrationType.LIVE,
    }
    integration_type = tipos_integracion.get(settings.WEBPAY_ENV)
    if integration_type is None:
        raise WebpayConfigurationError(
            'WEBPAY_ENV debe ser INTEGRATION o PRODUCTION.'
        )

    return WebpayOptions(
        commerce_code,
        api_key,
        integration_type,
    )


def confirmar_o_consultar_estado(transaccion, token):
    try:
        return transaccion.commit(token)
    except TransbankError:
        respuesta = transaccion.status(token)
        if respuesta.get('status') != 'AUTHORIZED':
            raise TransbankError('Transbank todavía no confirma el pago.')
        return respuesta


def url_retorno_webpay(request):
    return settings.WEBPAY_RETURN_URL or request.build_absolute_uri(
        reverse('webpay_return')
    )


@csrf_exempt
def retorno_webpay(request):
    if request.method not in ('GET', 'POST'):
        return HttpResponse(status=405)
    datos = request.POST if request.method == 'POST' else request.GET
    parametros = {}
    for campo in ('token_ws', 'TBK_TOKEN', 'TBK_ORDEN_COMPRA'):
        valor = datos.get(campo)
        if valor:
            parametros[campo] = valor
    destino = f'{settings.WEBPAY_FRONTEND_URL}/resultado-pago'
    if parametros:
        destino = f'{destino}?{urlencode(parametros)}'
    return HttpResponseRedirect(destino)


def crear_documento_tributario_pendiente(orden):
    return DocumentoTributario.objects.get_or_create(
        clave_idempotencia=f'DTE-ORDEN-{orden.pk}',
        defaults={
            'orden': orden,
            'tipo_dte': 33 if orden.tipo_documento_solicitado == 'FACTURA' else 39,
            'proveedor': 'PENDIENTE_CONFIGURACION',
            'ambiente': 'CERTIFICACION',
            'estado': 'PENDIENTE',
            'monto_total': orden.total,
            'fecha_solicitud': timezone.now(),
        },
    )[0]


def transaccion_de_usuario(request, reserva):
    return (
        es_trabajador(request.user)
        or reserva.cliente_id == request.user.id
    )


def puede_acceder_pago(request, reserva):
    if request.user.is_authenticated:
        return transaccion_de_usuario(request, reserva)
    token = (
        request.data.get('payment_access_token')
        or request.query_params.get('payment_access_token')
    )
    return validar_token_pago_invitado(token, reserva.pk)


class PagoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Pago.objects.select_related('orden', 'orden__reserva').order_by('-fecha_creacion')
    serializer_class = PagoSerializer
    permission_classes = [EsStaff]


@api_view(['POST'])
@permission_classes([AllowAny])
def crear_pago_transbank(request):
    reserva_id = request.data.get('reserva_id')
    try:
        reserva = Reserva.objects.select_related('cliente').get(pk=int(reserva_id))
    except (ValueError, TypeError):
        return Response({'detail': 'reserva_id debe ser un número.'}, status=status.HTTP_400_BAD_REQUEST)
    except Reserva.DoesNotExist:
        return Response({'detail': 'La reserva no existe.'}, status=status.HTTP_404_NOT_FOUND)

    if not puede_acceder_pago(request, reserva):
        return Response({'detail': 'No puedes pagar una reserva de otra persona.'}, status=status.HTTP_403_FORBIDDEN)
    if reserva.estado != 'PENDIENTE_PAGO':
        return Response({'detail': 'La reserva no está pendiente de pago.'}, status=status.HTTP_400_BAD_REQUEST)
    orden = OrdenCompra.objects.filter(reserva=reserva).first()
    if orden is None or orden.estado != 'PENDIENTE':
        return Response({'detail': 'No hay una orden pendiente de pago para esta reserva.'}, status=status.HTTP_409_CONFLICT)
    if orden.total != orden.total.to_integral_value():
        return Response({'detail': 'El monto de la orden debe expresarse en pesos enteros.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        webpay_options = opciones_webpay()
    except WebpayConfigurationError as error:
        logger.error('Webpay no está configurado: %s', error)
        return Response(
            {'detail': 'Webpay no está configurado correctamente.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    with transaction.atomic():
        orden = OrdenCompra.objects.select_for_update().get(pk=orden.pk)
        if orden.estado != 'PENDIENTE':
            return Response({'detail': 'La orden ya no está pendiente de pago.'}, status=status.HTTP_409_CONFLICT)
        pago_activo = Pago.objects.filter(orden=orden, estado_pago='PENDIENTE').first()
        if pago_activo:
            return Response(
                {'detail': 'Ya existe un intento de pago pendiente. No vuelvas a pagar; revisa el resultado o contacta a la sucursal.'},
                status=status.HTTP_409_CONFLICT,
            )
        buy_order = f'{orden.id}-{uuid.uuid4().hex[:8]}'
        session_id = uuid.uuid4().hex[:24]
        pago = Pago.objects.create(
            orden=orden,
            monto=orden.total,
            metodo_pago='WEBPAY',
            origen_pago='WEB',
            estado_pago='PENDIENTE',
            proveedor='TRANSBANK',
            buy_order=buy_order,
            session_id=session_id,
            clave_idempotencia=uuid.uuid4().hex,
            fecha_creacion=timezone.now(),
        )
    try:
        respuesta = Transaction(webpay_options).create(
            buy_order,
            session_id,
            int(orden.total),
            url_retorno_webpay(request),
        )
    except TransbankError:
        logger.exception('Transbank no pudo iniciar el pago de la orden %s', orden.pk)
        Pago.objects.filter(pk=pago.pk, estado_pago='PENDIENTE').update(
            estado_pago='RECHAZADO',
            fecha_actualizacion=timezone.now(),
        )
        return Response(
            {'detail': 'Transbank no pudo iniciar el pago. Intenta nuevamente.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    pago.token_webpay = respuesta['token']
    pago.save(update_fields=['token_webpay'])
    return Response({
        'url': respuesta['url'],
        'token': respuesta['token'],
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def confirmar_pago_transbank(request):
    token = request.data.get('token_ws')
    if not token:
        return Response({'detail': 'token_ws es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
    pago = Pago.objects.filter(token_webpay=token).select_related(
        'orden', 'orden__reserva', 'orden__reserva__cliente',
    ).first()
    if pago is None:
        return Response({'detail': 'No existe un intento de pago para ese token.'}, status=status.HTTP_404_NOT_FOUND)
    reserva = pago.orden.reserva
    if not puede_acceder_pago(request, reserva):
        return Response({'detail': 'No puedes confirmar el pago de otra persona.'}, status=status.HTTP_403_FORBIDDEN)
    if pago.estado_pago == 'AUTORIZADO' and reserva.estado == 'CONFIRMADA':
        return Response({
            'status': 'aprobado',
            'detalles': {'buy_order': pago.buy_order},
            'reserva': datos_reserva(reserva),
            'documento_tributario': 'PENDIENTE_EMISION',
        })
    if pago.estado_pago != 'PENDIENTE':
        return Response({'detail': 'Este intento de pago ya fue procesado.'}, status=status.HTTP_409_CONFLICT)

    try:
        webpay_options = opciones_webpay()
    except WebpayConfigurationError as error:
        logger.error('Webpay no está configurado: %s', error)
        return Response(
            {'detail': 'Webpay no está configurado correctamente.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        respuesta = confirmar_o_consultar_estado(
            Transaction(webpay_options),
            token,
        )
    except TransbankError:
        logger.exception('Transbank no pudo confirmar el pago %s', pago.pk)
        return Response(
            {'detail': 'No fue posible consultar el resultado del pago. Intenta nuevamente.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        monto_recibido = Decimal(str(respuesta.get('amount')))
    except (InvalidOperation, TypeError, ValueError):
        monto_recibido = None
    compra_coincide = respuesta.get('buy_order') == pago.buy_order
    monto_coincide = monto_recibido is not None and monto_recibido == pago.orden.total
    autorizado = (
        respuesta.get('response_code') == 0
        and respuesta.get('status') == 'AUTHORIZED'
        and compra_coincide
        and monto_coincide
    )
    if not autorizado:
        with transaction.atomic():
            pago.estado_pago = 'RECHAZADO'
            pago.fecha_actualizacion = timezone.now()
            pago.save(update_fields=['estado_pago', 'fecha_actualizacion'])
            if reserva.estado == 'PENDIENTE_PAGO':
                reserva.estado = 'EXPIRADA'
                reserva.save(update_fields=['estado'])
                HistorialEstadoReserva.objects.create(
                    reserva=reserva,
                    estado_anterior='PENDIENTE_PAGO',
                    estado_nuevo='EXPIRADA',
                    actor_tipo='SISTEMA',
                    observacion='El intento de pago fue rechazado.',
                    fecha_cambio=timezone.now(),
                )
        return Response({'status': 'rechazado', 'detalles': respuesta})

    with transaction.atomic():
        pago.estado_pago = 'AUTORIZADO'
        pago.metodo_pago = 'WEBPAY'
        pago.codigo_autorizacion = str(respuesta.get('authorization_code') or '')
        pago.codigo_transaccion_externa = str(respuesta.get('buy_order') or '')
        pago.fecha_pago = timezone.now()
        pago.fecha_actualizacion = timezone.now()
        pago.save(update_fields=(
            'estado_pago', 'metodo_pago', 'codigo_autorizacion',
            'codigo_transaccion_externa', 'fecha_pago', 'fecha_actualizacion',
        ))
        pago.orden.estado = 'PAGADA'
        pago.orden.save(update_fields=['estado'])
        reserva.estado = 'CONFIRMADA'
        reserva.save(update_fields=['estado'])
        HistorialEstadoReserva.objects.create(
            reserva=reserva,
            estado_anterior='PENDIENTE_PAGO',
            estado_nuevo='CONFIRMADA',
            actor_tipo='SISTEMA',
            observacion='Pago Webpay autorizado.',
            fecha_cambio=timezone.now(),
        )
        crear_documento_tributario_pendiente(pago.orden)

    aviso_correo = None
    try:
        if not enviar_confirmacion(reserva, comprobante_pdf(reserva)):
            aviso_correo = 'La reserva se confirmó, pero el correo no pudo enviarse.'
    except (BadHeaderError, OSError, SMTPException):
        logger.exception('No se pudo enviar el correo de confirmación de la reserva %s', reserva.pk)
        aviso_correo = 'La reserva se confirmó, pero ocurrió un error al enviar el correo.'

    return Response({
        'status': 'aprobado',
        'detalles': respuesta,
        'reserva': datos_reserva(reserva),
        'documento_tributario': 'PENDIENTE_EMISION',
        'aviso': aviso_correo,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def cancelar_pago_transbank(request):
    token = request.data.get('token_ws')
    buy_order = request.data.get('buy_order')
    if not token and not buy_order:
        return Response(
            {'detail': 'Se requiere token_ws o buy_order.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    pagos = Pago.objects.select_related(
        'orden', 'orden__reserva',
    )
    pago = pagos.filter(token_webpay=token).first() if token else None
    if pago is None and buy_order:
        pago = pagos.filter(buy_order=buy_order).first()
    if pago is None:
        return Response(
            {'detail': 'No existe un intento de pago para esos datos.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    reserva = pago.orden.reserva
    if not puede_acceder_pago(request, reserva):
        return Response({'detail': 'No puedes cancelar un pago de otra persona.'}, status=status.HTTP_403_FORBIDDEN)
    if pago.estado_pago != 'PENDIENTE':
        return Response({'detail': 'Este intento de pago ya fue procesado.'}, status=status.HTTP_409_CONFLICT)

    with transaction.atomic():
        pago.estado_pago = 'RECHAZADO'
        pago.fecha_actualizacion = timezone.now()
        pago.save(update_fields=['estado_pago', 'fecha_actualizacion'])
        if reserva.estado == 'PENDIENTE_PAGO':
            reserva.estado = 'EXPIRADA'
            reserva.save(update_fields=['estado'])
            HistorialEstadoReserva.objects.create(
                reserva=reserva,
                estado_anterior='PENDIENTE_PAGO',
                estado_nuevo='EXPIRADA',
                actor_tipo='SISTEMA',
                observacion='El cliente canceló el flujo de pago Webpay.',
                fecha_cambio=timezone.now(),
            )
    return Response({'status': 'cancelado'})


@api_view(['GET'])
@permission_classes([AllowAny])
def descargar_comprobante(request, reserva_id):
    try:
        reserva = Reserva.objects.select_related(
            'cliente', 'vehiculo', 'modelo', 'modelo__categoria',
            'sucursal_retiro', 'sucursal_devolucion',
        ).get(pk=reserva_id, estado='CONFIRMADA')
    except Reserva.DoesNotExist:
        return Response(
            {'detail': 'No existe una reserva confirmada con ese código.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    if not puede_acceder_pago(request, reserva):
        return Response(
            {'detail': 'Debes ser el titular de la reserva o un trabajador autorizado.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    respuesta = HttpResponse(comprobante_pdf(reserva), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="comprobante-reserva-{reserva.codigo}.pdf"'
    return respuesta
