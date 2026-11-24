from rest_framework import serializers

from .models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = (
            'id', 'nombre', 'apellido', 'correo', 'telefono',
            'fecha_nacimiento', 'fecha_registro', 'activo',
        )
        read_only_fields = ('id', 'fecha_registro')
