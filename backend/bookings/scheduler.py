import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from payments.models import Pago

from .models import HistorialEstadoReserva, Reserva


logger = logging.getLogger(__name__)


def expirar_reservas_sin_pago():
    limite = timezone.now() - timedelta(minutes=15)
    pagos_pendientes = Pago.objects.filter(
        orden__reserva_id=OuterRef('pk'),
        estado_pago='PENDIENTE',
    )
    reservas = Reserva.objects.filter(
        estado='PENDIENTE_PAGO',
        fecha_creacion__lt=limite,
    ).annotate(
        tiene_pago_pendiente=Exists(pagos_pendientes),
    ).filter(tiene_pago_pendiente=False)

    expiradas = 0
    for reserva in reservas.iterator():
        with transaction.atomic():
            actualizada = Reserva.objects.filter(
                pk=reserva.pk,
                estado='PENDIENTE_PAGO',
            ).update(estado='EXPIRADA')
            if actualizada:
                HistorialEstadoReserva.objects.create(
                    reserva_id=reserva.pk,
                    estado_anterior='PENDIENTE_PAGO',
                    estado_nuevo='EXPIRADA',
                    actor_tipo='SISTEMA',
                    observacion='La reserva expiró por falta de pago.',
                    fecha_cambio=timezone.now(),
                )
                expiradas += 1
    if expiradas:
        logger.info('Se marcaron %s reservas como expiradas.', expiradas)
    return expiradas


def iniciar_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        expirar_reservas_sin_pago,
        'interval',
        minutes=1,
        id='expirar_reservas_sin_pago',
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
