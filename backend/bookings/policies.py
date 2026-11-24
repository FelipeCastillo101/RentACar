from datetime import timedelta
from decimal import Decimal


def calcular_devolucion(total_pagado, tarifa_diaria, fecha_reserva, fecha_retiro, ahora):
    total_pagado = Decimal(total_pagado)
    tarifa_diaria = Decimal(tarifa_diaria)

    if ahora < fecha_retiro and ahora <= fecha_reserva + timedelta(days=10):
        dias_retenidos = 0
        fundamento = 'Retracto solicitado dentro de 10 días y antes del inicio del servicio.'
    else:
        horas_anticipacion = (fecha_retiro - ahora).total_seconds() / 3600
        if horas_anticipacion > 48:
            dias_retenidos = 0
            fundamento = 'Cancelación con más de 48 horas de anticipación.'
        elif horas_anticipacion >= 24:
            dias_retenidos = 1
            fundamento = 'Cancelación entre 24 y 48 horas antes del retiro.'
        elif horas_anticipacion > 0:
            dias_retenidos = 2
            fundamento = 'Cancelación con menos de 24 horas antes del retiro.'
        else:
            dias_retenidos = 3
            fundamento = 'No-show: no se registró la entrega del vehículo.'

    monto_retenido = min(total_pagado, tarifa_diaria * dias_retenidos)
    return {
        'monto_pagado': total_pagado,
        'monto_retenido': monto_retenido,
        'monto_devolucion': total_pagado - monto_retenido,
        'dias_retenidos': dias_retenidos,
        'fundamento': fundamento,
    }
