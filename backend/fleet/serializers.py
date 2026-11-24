import unicodedata

from django.utils import timezone
from rest_framework import serializers

from .models import Categoria, Modelo, Producto, Seguro, Sucursal, Vehiculo


def nombre_categoria_visible(nombre):
    corregido = str(nombre or '')
    for _ in range(3):
        if not any(marca in corregido for marca in ('Ã', 'Â')):
            break
        try:
            recuperado = corregido.encode('latin-1').decode('utf-8')
        except UnicodeError:
            break
        if recuperado == corregido:
            break
        corregido = recuperado
    clave = ''.join(
        caracter for caracter in unicodedata.normalize('NFD', corregido)
        if unicodedata.category(caracter) != 'Mn'
    ).lower()
    if clave == 'economico':
        return 'Económico'
    if clave == 'sedan':
        return 'Sedán'
    return corregido


class SucursalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sucursal
        fields = ('id', 'nombre', 'direccion', 'region', 'comuna')


class CategoriaSerializer(serializers.ModelSerializer):
    garantia_monto = serializers.DecimalField(
        source='monto_garantia', max_digits=12, decimal_places=2, required=False
    )

    class Meta:
        model = Categoria
        fields = ('id', 'nombre', 'descripcion', 'garantia_monto', 'activa')

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        datos['nombre'] = nombre_categoria_visible(datos['nombre'])
        return datos


class ModeloSerializer(serializers.ModelSerializer):
    categoria_id = serializers.PrimaryKeyRelatedField(
        source='categoria', queryset=Categoria.objects.all(), write_only=True,
    )
    categoria = CategoriaSerializer(read_only=True)
    categoria_nombre = serializers.SerializerMethodField()
    garantia_monto = serializers.DecimalField(
        source='categoria.monto_garantia', max_digits=12, decimal_places=2, read_only=True
    )
    precio_diario = serializers.SerializerMethodField()
    anio = serializers.SerializerMethodField()
    imagen = serializers.CharField(source='imagen_principal', read_only=True, allow_null=True)
    stock_total = serializers.IntegerField(read_only=True)
    stock_disponible = serializers.IntegerField(read_only=True)

    class Meta:
        model = Modelo
        fields = (
            'id', 'marca', 'nombre_modelo', 'anio', 'transmision', 'combustible',
            'pasajeros', 'puertas', 'descripcion', 'precio_diario', 'imagen',
            'categoria', 'categoria_nombre', 'garantia_monto', 'stock_total',
            'stock_disponible', 'categoria_id', 'activo',
        )

    def get_precio_diario(self, obj):
        fecha = timezone.localdate()
        tarifa = obj.tarifa_set.filter(
            activa=True,
            fecha_desde__lte=fecha,
        ).filter(
            models_q_fecha(fecha)
        ).order_by('-fecha_desde', '-id').first()
        return str(tarifa.precio_diario) if tarifa else '0.00'

    def get_categoria_nombre(self, obj):
        return nombre_categoria_visible(obj.categoria.nombre)

    def get_anio(self, obj):
        return obj.vehiculo_set.order_by('-anio').values_list('anio', flat=True).first()


def models_q_fecha(fecha):
    from django.db.models import Q
    return Q(fecha_hasta__isnull=True) | Q(fecha_hasta__gte=fecha)


class VehiculoSerializer(serializers.ModelSerializer):
    modelo_id = serializers.PrimaryKeyRelatedField(
        source='modelo', queryset=Modelo.objects.all(), write_only=True,
    )
    sucursal_id = serializers.PrimaryKeyRelatedField(
        source='sucursal_actual', queryset=Sucursal.objects.filter(activa=True),
        write_only=True,
    )
    modelo = ModeloSerializer(read_only=True)
    sucursal = serializers.CharField(source='sucursal_actual.nombre', read_only=True)
    sucursal_id_actual = serializers.IntegerField(
        source='sucursal_actual_id', read_only=True,
    )
    estado = serializers.SerializerMethodField()
    estado_operativo = serializers.ChoiceField(
        choices=Vehiculo.ESTADOS, write_only=True, required=False,
    )
    kilometraje = serializers.IntegerField(source='kilometraje_actual', required=False)

    class Meta:
        model = Vehiculo
        fields = (
            'id', 'patente', 'anio', 'color', 'estado', 'kilometraje',
            'modelo', 'sucursal', 'observaciones', 'modelo_id', 'sucursal_id',
            'estado_operativo', 'sucursal_id_actual',
        )

    def get_estado(self, obj):
        return obj.estado_operativo.lower()


class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ('id', 'nombre', 'tipo', 'descripcion', 'precio_diario', 'activo')


class SeguroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seguro
        fields = ('id', 'nombre', 'descripcion', 'precio_diario', 'deducible_monto', 'activo')
