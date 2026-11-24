from django.db.models import Count, Q
from rest_framework.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.permissions import EsAdmin, EsStaff, es_admin

from .models import Categoria, Modelo, Producto, Seguro, Sucursal, Vehiculo
from .serializers import (
    CategoriaSerializer,
    ModeloSerializer,
    ProductoSerializer,
    SeguroSerializer,
    SucursalSerializer,
    VehiculoSerializer,
)


class AdminEditableCatalogViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [EsAdmin()]


class SucursalViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Sucursal.objects.filter(activa=True).order_by('nombre')
    serializer_class = SucursalSerializer
    permission_classes = [AllowAny]


class CategoriaViewSet(AdminEditableCatalogViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if not es_admin(self.request.user):
            queryset = queryset.filter(activa=True)
        return queryset


class ModeloViewSet(AdminEditableCatalogViewSet):
    serializer_class = ModeloSerializer

    def get_queryset(self):
        queryset = Modelo.objects.filter(activo=True).annotate(
            stock_total=Count(
                'vehiculo',
                filter=~Q(vehiculo__estado_operativo='BAJA'),
                distinct=True,
            ),
            stock_disponible=Count(
                'vehiculo',
                filter=Q(vehiculo__estado_operativo='ACTIVO'),
                distinct=True,
            ),
        ).select_related('categoria').order_by('id')
        if es_admin(self.request.user):
            queryset = Modelo.objects.all().annotate(
                stock_total=Count(
                    'vehiculo',
                    filter=~Q(vehiculo__estado_operativo='BAJA'),
                    distinct=True,
                ),
                stock_disponible=Count(
                    'vehiculo',
                    filter=Q(vehiculo__estado_operativo='ACTIVO'),
                    distinct=True,
                ),
            ).select_related('categoria').order_by('id')
        else:
            queryset = queryset.filter(activo=True, stock_disponible__gt=0)
        categoria = self.request.query_params.get('categoria')
        if categoria:
            valores = categoria.split(',')
            try:
                categorias_ids = [int(valor.strip()) for valor in valores]
            except ValueError as error:
                raise ValidationError({
                    'categoria': 'Indica uno o más identificadores de categoría válidos.'
                }) from error
            if not categorias_ids or any(valor <= 0 for valor in categorias_ids):
                raise ValidationError({
                    'categoria': 'Indica uno o más identificadores de categoría válidos.'
                })
            queryset = queryset.filter(categoria_id__in=categorias_ids)
        return queryset


class VehiculoViewSet(viewsets.ModelViewSet):
    queryset = Vehiculo.objects.select_related('modelo', 'modelo__categoria', 'sucursal_actual').order_by('id')
    serializer_class = VehiculoSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [EsStaff()]
        return [EsAdmin()]

    @action(detail=True, methods=['post'])
    def estado(self, request, pk=None):
        vehiculo = self.get_object()
        estados = {
            'disponible': 'ACTIVO',
            'activo': 'ACTIVO',
            'en_arriendo': 'EN_ARRENDAMIENTO',
            'en_arrendamiento': 'EN_ARRENDAMIENTO',
            'limpieza': 'LIMPIEZA',
            'mantenimiento': 'MANTENCION',
            'mantencion': 'MANTENCION',
            'fuera_servicio': 'FUERA_SERVICIO',
            'baja': 'BAJA',
        }
        estado = str(request.data.get('estado') or '').strip().lower()
        nuevo = estados.get(estado)
        if nuevo is None:
            return Response(
                {'estado': 'Estado inválido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vehiculo.estado_operativo = nuevo
        vehiculo.save(update_fields=['estado_operativo'])
        return Response(self.get_serializer(vehiculo).data)


class ProductoViewSet(AdminEditableCatalogViewSet):
    queryset = Producto.objects.all().order_by('nombre')
    serializer_class = ProductoSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if not es_admin(self.request.user):
            queryset = queryset.filter(activo=True)
        return queryset


class SeguroViewSet(AdminEditableCatalogViewSet):
    queryset = Seguro.objects.all().order_by('nombre')
    serializer_class = SeguroSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if not es_admin(self.request.user):
            queryset = queryset.filter(activo=True)
        return queryset
