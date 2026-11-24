from rest_framework import serializers

from .models import Pago


class PagoSerializer(serializers.ModelSerializer):
    codigo_orden = serializers.CharField(source='orden.codigo_orden', read_only=True)
    reserva_codigo = serializers.CharField(source='orden.reserva.codigo', read_only=True)

    class Meta:
        model = Pago
        fields = (
            'id', 'orden', 'codigo_orden', 'reserva_codigo', 'monto',
            'metodo_pago', 'origen_pago', 'estado_pago', 'proveedor',
            'codigo_autorizacion', 'codigo_transaccion_externa',
            'fecha_creacion', 'fecha_pago',
        )
        read_only_fields = fields
