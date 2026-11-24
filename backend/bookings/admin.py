from django.contrib import admin

from .models import (
    Cancelacion,
    Contrato,
    ContratoVersion,
    HistorialEstadoReserva,
    Reserva,
    ReservaProducto,
    ReservaSeguro,
)

admin.site.register(Reserva)
admin.site.register(ReservaProducto)
admin.site.register(ReservaSeguro)
admin.site.register(HistorialEstadoReserva)
admin.site.register(ContratoVersion)
admin.site.register(Contrato)
admin.site.register(Cancelacion)
