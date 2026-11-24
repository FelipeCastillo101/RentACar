"""Notificaciones del flujo de cancelaciones y devoluciones."""
import logging
from pathlib import Path
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.message import BadHeaderError
from django.core.files.storage import default_storage
from django.db.models import Q

from fleet.models import Trabajador

logger = logging.getLogger(__name__)


def _enviar(asunto, cuerpo, destinos):
    destinos = [destino for destino in destinos if destino]
    if not destinos:
        logger.warning('No hay destinatarios configurados para "%s".', asunto)
        return False
    try:
        enviados = EmailMessage(subject=asunto, body=cuerpo, to=destinos).send(
            fail_silently=False,
        )
    except (BadHeaderError, OSError, SMTPException):
        logger.exception('No se pudo enviar el correo "%s".', asunto)
        return False
    return enviados > 0


def destinatarios_staff():
    """Admins y asistentes activos reciben avisos operacionales."""
    return list(
        Trabajador.objects.filter(
            Q(roles__codigo__iexact='admin') | Q(roles__codigo__iexact='asistente'),
            activo=True,
        )
        .values_list('correo', flat=True)
        .distinct()
    )


def notificar_nueva_cancelacion(cancelacion, cotizacion):
    reserva = cancelacion.reserva
    cuerpo = (
        'Se recibió una nueva solicitud de cancelación.\n\n'
        f'Reserva: {reserva.codigo}\n'
        f'Cliente: {reserva.cliente.nombre} {reserva.cliente.apellido}\n'
        f'Motivo: {cancelacion.motivo}\n'
        f'Monto pagado: ${reserva.total}\n'
        f'Devolución preliminar: ${cotizacion["monto_devolucion"]}\n\n'
        'El monto definitivo lo determina Finanzas. Revisa y deriva la solicitud '
        'desde el panel de operación.'
    )
    return _enviar(
        f'Nueva solicitud de cancelación {reserva.codigo}',
        cuerpo,
        destinatarios_staff(),
    )


def notificar_cliente_cancelacion(cancelacion, cotizacion):
    reserva = cancelacion.reserva
    cuerpo = (
        f'Recibimos tu solicitud de cancelación para la reserva {reserva.codigo}.\n\n'
        f'Vehículo: {reserva.modelo.marca} {reserva.modelo.nombre_modelo}\n'
        f'Monto pagado: ${cotizacion["monto_pagado"]}\n'
        f'Monto retenido estimado: ${cotizacion["monto_retenido"]}\n'
        f'Devolución preliminar: ${cotizacion["monto_devolucion"]}\n'
        f'Criterio aplicado: {cotizacion["fundamento"]}\n\n'
        'Este cálculo es informativo y no es una aprobación. Un trabajador revisará '
        'la solicitud y Finanzas determinará el monto final y realizará la transferencia.'
    )
    return _enviar(
        f'Solicitud de cancelación recibida - {reserva.codigo}',
        cuerpo,
        [reserva.cliente.correo],
    )


def derivar_cancelacion_a_finanzas(cancelacion, cotizacion):
    reserva = cancelacion.reserva
    destinatario = getattr(settings, 'CANCELATION_FINANCE_EMAIL', '')
    cuerpo = (
        'Hay una solicitud de cancelación derivada para calcular la devolución.\n\n'
        f'Solicitud: {cancelacion.pk}\n'
        f'Reserva: {reserva.codigo}\n'
        f'Devolución preliminar: ${cotizacion["monto_devolucion"]}\n'
        'El monto final debe ser determinado por Finanzas y no ha sido registrado todavía.\n\n'
        'Consulta los datos bancarios desde el panel de operación. No se incluyen '
        'datos de cuenta en este correo.'
    )
    return _enviar(
        f'Devolución pendiente - reserva {reserva.codigo}',
        cuerpo,
        [destinatario],
    )


def notificar_cliente_reembolso(cancelacion, monto, referencia, comprobante_path):
    reserva = cancelacion.reserva
    cuerpo = (
        f'La cancelación de la reserva {reserva.codigo} fue completada y el vehículo liberado.\n\n'
        f'Monto: ${monto}\n'
        f'Código de comprobante de transferencia: {referencia}\n\n'
        'Adjuntamos el comprobante de la transferencia.\n\n'
        'Si tienes dudas, contacta a la sucursal.'
    )
    try:
        correo = EmailMessage(
            subject=f'Cancelación y devolución completadas - {reserva.codigo}',
            body=cuerpo,
            to=[reserva.cliente.correo],
        )
        extension = Path(comprobante_path).suffix.lower()
        tipo = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
        }[extension]
        with default_storage.open(comprobante_path, 'rb') as comprobante:
            correo.attach(
                f'comprobante-transferencia-{reserva.codigo}{extension}',
                comprobante.read(),
                tipo,
            )
        enviados = correo.send(fail_silently=False)
    except (BadHeaderError, OSError, SMTPException):
        logger.exception('No se pudo enviar el comprobante de devolución %s.', reserva.codigo)
        return False
    return enviados > 0


def notificar_cliente_cancelacion_cerrada_sin_reembolso(cancelacion):
    reserva = cancelacion.reserva
    cuerpo = (
        f'La cancelación de la reserva {reserva.codigo} fue cerrada.\n\n'
        f'Monto pagado: ${reserva.total}\n'
        'Devolución: $0 según el criterio aplicado a la solicitud.\n'
        'Si tienes dudas sobre la revisión, contacta a la sucursal.'
    )
    return _enviar(
        f'Cancelación cerrada - {reserva.codigo}',
        cuerpo,
        [reserva.cliente.correo],
    )


def notificar_cliente_cancelacion_rechazada(cancelacion):
    reserva = cancelacion.reserva
    cuerpo = (
        f'La solicitud de cancelación de la reserva {reserva.codigo} fue rechazada.\n\n'
        f'Motivo: {cancelacion.motivo_rechazo}\n'
        'La reserva permanece confirmada. Contacta a la sucursal si necesitas ayuda.'
    )
    return _enviar(
        f'Solicitud de cancelación revisada - {reserva.codigo}',
        cuerpo,
        [reserva.cliente.correo],
    )
