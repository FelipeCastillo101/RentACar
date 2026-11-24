from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from fleet.models import Vehiculo
from payments.models import Pago
from users.models import Cliente

from .models import Cancelacion, Reembolso, Reserva


PERIODOS_DASHBOARD = {
    'dia': 'Día',
    'semana': 'Semana',
    'mes': 'Mes',
    'trimestre': 'Trimestre',
    'semestre': 'Semestre',
    'anio': 'Año',
}
ESTADOS_RESERVA_REALIZADA = ('CONFIRMADA', 'EN_CURSO', 'COMPLETADA')
GASTOS_OPERACIONALES_REFERENCIA_PORCENTAJE = Decimal('0.15')


def rango_periodo(periodo, referencia=None):
    if periodo not in PERIODOS_DASHBOARD:
        raise ValueError('El período seleccionado no es válido.')

    referencia = referencia or timezone.localdate()
    if periodo == 'dia':
        inicio = referencia
        fin = inicio + timedelta(days=1)
    elif periodo == 'semana':
        inicio = referencia - timedelta(days=referencia.weekday())
        fin = inicio + timedelta(days=7)
    elif periodo == 'mes':
        inicio = referencia.replace(day=1)
        fin = (
            date(inicio.year + 1, 1, 1)
            if inicio.month == 12
            else date(inicio.year, inicio.month + 1, 1)
        )
    elif periodo == 'trimestre':
        mes_inicio = ((referencia.month - 1) // 3) * 3 + 1
        inicio = date(referencia.year, mes_inicio, 1)
        fin = date(referencia.year + 1, 1, 1) if mes_inicio == 10 else date(
            referencia.year, mes_inicio + 3, 1
        )
    elif periodo == 'semestre':
        mes_inicio = 1 if referencia.month <= 6 else 7
        inicio = date(referencia.year, mes_inicio, 1)
        fin = date(referencia.year, 7, 1) if mes_inicio == 1 else date(
            referencia.year + 1, 1, 1
        )
    else:
        inicio = date(referencia.year, 1, 1)
        fin = date(referencia.year + 1, 1, 1)
    return inicio, fin


def _a_fecha_hora_local(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


def construir_dashboard(periodo, referencia, es_administrador):
    inicio, fin = rango_periodo(periodo, referencia)
    inicio_dt = _a_fecha_hora_local(inicio)
    fin_dt = _a_fecha_hora_local(fin)

    reservas_periodo = Reserva.objects.filter(
        fecha_hora_retiro__gte=inicio_dt,
        fecha_hora_retiro__lt=fin_dt,
        estado__in=ESTADOS_RESERVA_REALIZADA,
    )
    cancelaciones_periodo = Cancelacion.objects.filter(
        fecha_solicitud__gte=inicio_dt,
        fecha_solicitud__lt=fin_dt,
    )
    vehiculos_por_estado = dict(
        Vehiculo.objects.values_list('estado_operativo').annotate(total=Count('id'))
    )
    vehiculos_total = sum(vehiculos_por_estado.values())
    clientes_total = Cliente.objects.filter(activo=True).count()
    clientes_arrendando = Reserva.objects.filter(
        estado='EN_CURSO',
        cliente__activo=True,
    ).values('cliente_id').distinct().count()

    resultado = {
        'periodo': {
            'clave': periodo,
            'etiqueta': PERIODOS_DASHBOARD[periodo],
            'inicio': inicio.isoformat(),
            'fin': (fin - timedelta(days=1)).isoformat(),
        },
        'reservas': {
            'total': reservas_periodo.count(),
            'completadas': reservas_periodo.filter(estado='COMPLETADA').count(),
            'vehiculos_arrendados': reservas_periodo.values('vehiculo_id').distinct().count(),
            'clientes_arrendatarios': reservas_periodo.values('cliente_id').distinct().count(),
        },
        'clientes': {
            'total': clientes_total,
            'nuevos_periodo': Cliente.objects.filter(
                fecha_registro__gte=inicio_dt,
                fecha_registro__lt=fin_dt,
                activo=True,
            ).count(),
            'arrendando': clientes_arrendando,
            'sin_arriendo_actual': max(clientes_total - clientes_arrendando, 0),
        },
        'flota': {
            'total': vehiculos_total,
            'disponibles': vehiculos_por_estado.get('ACTIVO', 0),
            'en_arrendamiento': vehiculos_por_estado.get('EN_ARRENDAMIENTO', 0),
            'limpieza': vehiculos_por_estado.get('LIMPIEZA', 0),
            'mantencion': vehiculos_por_estado.get('MANTENCION', 0),
            'fuera_servicio': vehiculos_por_estado.get('FUERA_SERVICIO', 0),
            'baja': vehiculos_por_estado.get('BAJA', 0),
        },
        'cancelaciones': {
            'total': cancelaciones_periodo.count(),
            'pendientes': cancelaciones_periodo.filter(estado='PENDIENTE').count(),
            'en_revision': cancelaciones_periodo.filter(estado='EN_REVISION').count(),
            'aprobadas': cancelaciones_periodo.filter(estado='APROBADA').count(),
            'rechazadas': cancelaciones_periodo.filter(estado='RECHAZADA').count(),
            'reembolsadas': cancelaciones_periodo.filter(
                estado__in=('REEMBOLSO_REGISTRADO', 'CERRADA')
            ).count(),
        },
    }

    if es_administrador:
        pagos_periodo = Pago.objects.filter(
            estado_pago='AUTORIZADO',
        ).filter(
            Q(fecha_pago__gte=inicio_dt, fecha_pago__lt=fin_dt)
            | Q(fecha_pago__isnull=True, fecha_creacion__gte=inicio_dt, fecha_creacion__lt=fin_dt)
        )
        reembolsos_periodo = Reembolso.objects.filter(
            estado='COMPLETADO',
            fecha_reembolso__gte=inicio_dt,
            fecha_reembolso__lt=fin_dt,
        )
        ventas_brutas = pagos_periodo.aggregate(total=Sum('monto'))['total'] or Decimal('0')
        monto_reembolsado = reembolsos_periodo.aggregate(total=Sum('monto'))['total'] or Decimal('0')
        ventas_netas = ventas_brutas - monto_reembolsado
        gastos_estimados = max(ventas_netas, Decimal('0')) * GASTOS_OPERACIONALES_REFERENCIA_PORCENTAJE
        resultado['finanzas'] = {
            'pagos_autorizados': pagos_periodo.count(),
            'ventas_brutas': str(ventas_brutas),
            'reembolsos_completados': reembolsos_periodo.count(),
            'monto_reembolsado': str(monto_reembolsado),
            'ventas_netas': str(ventas_netas),
            'gastos_operacionales_estimados': str(gastos_estimados),
            'gastos_estimados_porcentaje': int(GASTOS_OPERACIONALES_REFERENCIA_PORCENTAJE * 100),
        }

    return resultado
