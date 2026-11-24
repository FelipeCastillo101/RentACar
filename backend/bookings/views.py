import logging
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from smtplib import SMTPException
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse
from payments.guest_access import crear_token_pago_invitado
from django.core.mail.message import BadHeaderError
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.permissions import EsAdmin, EsStaff, es_trabajador
from fleet.models import Modelo, Sucursal, Tarifa, Vehiculo
from fleet.serializers import ModeloSerializer
from payments.models import OrdenCompra, Pago

from .models import (
    Cancelacion,
    HistorialEstadoReserva,
    Reembolso,
    Reserva,
)
from .dashboard import PERIODOS_DASHBOARD, construir_dashboard
from .serializers import CancelacionSerializer, ReservaSerializer
from .policies import calcular_devolucion


ESTADOS_QUE_BLOQUEAN_UNIDAD = (
    'PENDIENTE_PAGO', 'CONFIRMADA', 'EN_CURSO', 'CANCELACION_EN_PROCESO',
)
MAX_TAMANO_COMPROBANTE = 8 * 1024 * 1024
TIPOS_COMPROBANTE = {
    '.pdf': ('application/pdf', b'%PDF-'),
    '.png': ('image/png', b'\x89PNG\r\n\x1a\n'),
    '.jpg': ('image/jpeg', b'\xff\xd8\xff'),
    '.jpeg': ('image/jpeg', b'\xff\xd8\xff'),
}
ESTADOS_CANCELACION_ACTIVA = (
    'PENDIENTE', 'EN_REVISION', 'APROBADA', 'DERIVADA_FINANZAS',
    'REEMBOLSO_REGISTRADO',
)
logger = logging.getLogger(__name__)


def guardar_comprobante_reembolso(archivo):
    extension = Path(archivo.name).suffix.lower()
    tipo_esperado = TIPOS_COMPROBANTE.get(extension)
    if tipo_esperado is None or archivo.content_type != tipo_esperado[0]:
        return None, 'El comprobante debe ser PDF, PNG o JPEG.'
    if archivo.size > MAX_TAMANO_COMPROBANTE:
        return None, 'El comprobante no puede superar 8 MB.'
    if not archivo.read(len(tipo_esperado[1])).startswith(tipo_esperado[1]):
        archivo.seek(0)
        return None, 'El contenido del comprobante no coincide con su formato.'
    archivo.seek(0)
    ruta = default_storage.save(
        f'reembolsos/{uuid4().hex}{extension}',
        archivo,
    )
    return ruta, None


def cotizar_devolucion(reserva, ahora=None):
    ahora = ahora or timezone.now()
    orden = OrdenCompra.objects.filter(reserva=reserva).first()
    if orden is None:
        raise ValueError('La reserva no tiene una orden de compra.')
    total_pagado = Pago.objects.filter(
        orden=orden,
        estado_pago='AUTORIZADO',
    ).aggregate(total=Sum('monto'))['total']
    if total_pagado is None or total_pagado <= 0:
        raise ValueError('La reserva no tiene un pago autorizado.')

    fecha_retiro = timezone.localtime(reserva.fecha_hora_retiro)
    tarifa = Tarifa.objects.filter(
        modelo=reserva.modelo,
        activa=True,
        fecha_desde__lte=fecha_retiro.date(),
    ).filter(
        Q(fecha_hasta__isnull=True) | Q(fecha_hasta__gte=fecha_retiro.date())
    ).order_by('-fecha_desde', '-id').first()
    if tarifa is None:
        raise ValueError('No hay una tarifa vigente para calcular la devolución.')

    return calcular_devolucion(
        total_pagado=total_pagado,
        tarifa_diaria=tarifa.precio_diario,
        fecha_reserva=reserva.fecha_creacion,
        fecha_retiro=reserva.fecha_hora_retiro,
        ahora=ahora,
    )


def crear_inspeccion(reserva, trabajador, tipo, datos):
    kilometraje = datos.get('kilometraje')
    combustible = str(datos.get('nivel_combustible') or '').strip()
    if isinstance(kilometraje, bool):
        raise ValueError('El kilometraje debe ser un entero no negativo.')
    try:
        kilometraje = int(kilometraje)
    except (TypeError, ValueError):
        raise ValueError('El kilometraje debe ser un entero no negativo.') from None
    if kilometraje < 0:
        raise ValueError('El kilometraje debe ser un entero no negativo.')
    if not combustible or len(combustible) > 20:
        raise ValueError('Indica el nivel de combustible (máximo 20 caracteres).')
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO inspeccion_vehiculo
                (reserva_id, vehiculo_id, trabajador_id, tipo_inspeccion,
                 kilometraje, nivel_combustible, observaciones, fecha_inspeccion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            [
                reserva.id, reserva.vehiculo_id, trabajador.id, tipo,
                kilometraje, combustible, str(datos.get('observaciones') or '').strip(),
                timezone.now(),
            ],
        )
        return cursor.fetchone()[0]


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.select_related(
        'cliente', 'modelo', 'modelo__categoria', 'vehiculo',
        'sucursal_retiro', 'sucursal_devolucion',
    ).prefetch_related('detalles', 'cancelaciones').order_by('-fecha_creacion')
    serializer_class = ReservaSerializer

    def get_permissions(self):
        if self.action == 'disponibilidad':
            return [AllowAny()]
        if self.action == 'create':
            return [IsAuthenticated()]
        if self.action in ('buscar', 'confirmar_presencial', 'estado', 'cancelar', 'dashboard'):
            return [EsStaff()]
        if self.action in ('update', 'partial_update'):
            return [EsStaff()]
        if self.action == 'destroy':
            return [EsAdmin()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED and not request.user.is_authenticated:
            response.data = {
                **response.data,
                'payment_access_token': crear_token_pago_invitado(response.data['id']),
            }
        return response

    def get_queryset(self):
        queryset = super().get_queryset()
        usuario = self.request.user
        if usuario and usuario.is_authenticated and not es_trabajador(usuario):
            queryset = queryset.filter(cliente_id=usuario.id)
        return queryset

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        periodo = request.query_params.get('periodo', 'mes')
        fecha = request.query_params.get('fecha')
        try:
            referencia = date.fromisoformat(fecha) if fecha else timezone.localdate()
            if periodo not in PERIODOS_DASHBOARD:
                raise ValueError
            resultado = construir_dashboard(
                periodo,
                referencia,
                es_administrador=request.user.rol == 'admin',
            )
        except ValueError:
            return Response(
                {'detail': 'Usa un período válido y una fecha en formato YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(resultado)

    @action(detail=False, methods=['get'])
    def disponibilidad(self, request):
        try:
            fecha_inicio = date.fromisoformat(request.query_params.get('inicio', ''))
            fecha_fin = date.fromisoformat(request.query_params.get('fin', ''))
            hora_inicio = time.fromisoformat(request.query_params.get('hora_inicio', '09:00'))
            hora_fin = time.fromisoformat(request.query_params.get('hora_fin', '18:00'))
        except ValueError:
            return Response(
                {'detail': 'Usa fechas YYYY-MM-DD y horarios HH:MM válidos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not time(9) <= hora_inicio <= time(18) or not time(9) <= hora_fin <= time(18):
            return Response(
                {'detail': 'Los horarios deben estar entre las 09:00 y las 18:00.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        retiro = timezone.make_aware(datetime.combine(fecha_inicio, hora_inicio))
        devolucion = timezone.make_aware(datetime.combine(fecha_fin, hora_fin))
        if devolucion <= retiro:
            return Response(
                {'detail': 'La devolución debe ser posterior al retiro.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if retiro < timezone.now():
            return Response(
                {'detail': 'La fecha y hora de retiro deben ser futuras.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sucursal_id = request.query_params.get('sucursal')
        sucursal = None
        if sucursal_id:
            try:
                sucursal = Sucursal.objects.get(pk=int(sucursal_id), activa=True)
            except (ValueError, TypeError, Sucursal.DoesNotExist):
                return Response(
                    {'sucursal': 'La sucursal indicada no existe o no está activa.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            sucursal = Sucursal.objects.filter(activa=True).order_by('id').first()
        if sucursal is None:
            return Response({'detail': 'No hay sucursales activas.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        categoria = request.query_params.get('categoria')
        categorias_ids = set()
        if categoria:
            try:
                categorias_ids = {
                    int(valor.strip())
                    for valor in categoria.split(',')
                    if valor.strip()
                }
                if not categorias_ids or len(categorias_ids) != len(categoria.split(',')):
                    raise ValueError
            except (TypeError, ValueError):
                return Response(
                    {'categoria': 'Indica uno o más identificadores de categoría válidos.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        reservas_solapadas = Reserva.objects.filter(
            vehiculo_id=OuterRef('pk'),
            estado__in=ESTADOS_QUE_BLOQUEAN_UNIDAD,
            fecha_hora_retiro__lt=devolucion,
            fecha_hora_devolucion__gt=retiro,
        )
        vehiculos = Vehiculo.objects.filter(
            estado_operativo='ACTIVO',
            sucursal_actual=sucursal,
            modelo__activo=True,
            modelo__categoria__activa=True,
        ).annotate(
            reservada=Exists(reservas_solapadas),
        )
        total_por_modelo = {
            fila['modelo_id']: fila['total']
            for fila in Vehiculo.objects.exclude(
                estado_operativo='BAJA',
            ).values('modelo_id').annotate(total=Count('id'))
        }
        disponibles = {}
        for vehiculo in vehiculos.filter(reservada=False).select_related('modelo', 'modelo__categoria'):
            if categorias_ids and vehiculo.modelo.categoria_id not in categorias_ids:
                continue
            disponibles[vehiculo.modelo_id] = disponibles.get(vehiculo.modelo_id, 0) + 1

        ids = list(disponibles)
        modelos = Modelo.objects.filter(pk__in=ids).select_related('categoria').order_by('id')
        resultados = []
        for modelo in modelos:
            tarifa = Tarifa.objects.filter(
                modelo=modelo,
                activa=True,
                fecha_desde__lte=fecha_inicio,
            ).filter(
                Q(fecha_hasta__isnull=True) | Q(fecha_hasta__gte=fecha_inicio)
            ).order_by('-fecha_desde', '-id').first()
            if tarifa is None:
                continue
            datos = dict(ModeloSerializer(modelo).data)
            datos['precio_diario'] = str(tarifa.precio_diario)
            datos['stock_disponible'] = disponibles[modelo.id]
            datos['stock_total'] = total_por_modelo.get(modelo.id, 0)
            resultados.append(datos)
        return Response({'vehiculos_disponibles': resultados})

    @action(detail=False, methods=['get'])
    def buscar(self, request):
        termino = (request.query_params.get('q') or '').strip()
        if not termino:
            return Response(
                {'detail': 'Escribe código de reserva, RUT/pasaporte o patente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reservas = self.get_queryset().filter(
            Q(codigo__iexact=termino)
            | Q(cliente__documentos__numero_documento__icontains=termino)
            | Q(vehiculo__patente__iexact=termino)
        ).distinct()[:20]
        return Response(self.get_serializer(reservas, many=True).data)

    @action(detail=True, methods=['post'])
    def confirmar_presencial(self, request, pk=None):
        reserva = self.get_object()
        if reserva.estado != 'PENDIENTE_PAGO':
            return Response(
                {'detail': 'Solo las reservas pendientes pueden recibir un pago presencial.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        orden = OrdenCompra.objects.filter(reserva=reserva, estado='PENDIENTE').first()
        if orden is None:
            return Response({'detail': 'La reserva no tiene una orden pendiente.'}, status=status.HTTP_409_CONFLICT)
        metodos = {
            'efectivo': 'EFECTIVO',
            'transbank_pos': 'TRANSBANK_POS',
            'tarjeta': 'TRANSBANK_POS',
            'transferencia': 'TRANSFERENCIA',
            'otro': 'OTRO',
        }
        metodo = metodos.get(str(request.data.get('metodo_pago') or 'efectivo').strip().lower())
        if metodo is None:
            return Response(
                {'metodo_pago': 'Usa efectivo, transbank_pos, transferencia u otro.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        referencia = str(request.data.get('referencia_externa') or '').strip()
        with transaction.atomic():
            Pago.objects.create(
                orden=orden,
                monto=orden.total,
                metodo_pago=metodo,
                origen_pago='SUCURSAL',
                estado_pago='AUTORIZADO',
                proveedor='TRANSBANK' if metodo == 'TRANSBANK_POS' else None,
                codigo_transaccion_externa=referencia or None,
                clave_idempotencia=f'PRES-{uuid4().hex}' ,
                fecha_creacion=timezone.now(),
                fecha_pago=timezone.now(),
                registrado_por_trabajador=request.user,
            )
            orden.estado = 'PAGADA'
            orden.save(update_fields=['estado'])
            reserva.estado = 'CONFIRMADA'
            reserva.save(update_fields=['estado'])
            HistorialEstadoReserva.objects.create(
                reserva=reserva,
                estado_anterior='PENDIENTE_PAGO',
                estado_nuevo='CONFIRMADA',
                actor_tipo='TRABAJADOR',
                trabajador=request.user,
                observacion=f'Pago presencial registrado: {metodo}.',
                fecha_cambio=timezone.now(),
            )
            from payments.views import crear_documento_tributario_pendiente
            crear_documento_tributario_pendiente(orden)

        aviso = None
        try:
            from payments.views import comprobante_pdf, enviar_confirmacion
            if not enviar_confirmacion(reserva, comprobante_pdf(reserva)):
                aviso = 'El pago se registró, pero el correo de confirmación no pudo enviarse.'
        except (BadHeaderError, OSError, SMTPException):
            logger.exception('No se pudo enviar la confirmación de la reserva %s', reserva.pk)
            aviso = 'El pago se registró, pero ocurrió un error al enviar el correo.'
        response = Response(self.get_serializer(reserva).data)
        if aviso:
            response.data['aviso'] = aviso
        return response

    @action(detail=True, methods=['post'])
    def estado(self, request, pk=None):
        reserva = self.get_object()
        nuevo = str(request.data.get('estado') or '').upper()
        if nuevo == 'EN_CURSO':
            if reserva.estado != 'CONFIRMADA':
                return Response({'detail': 'Solo una reserva pagada y confirmada puede iniciar.'}, status=400)
            checks = (
                'codigo_orden_verificado', 'identidad_verificada',
                'licencia_verificada', 'garantia_verificada',
            )
            if any(request.data.get(campo) is not True for campo in checks):
                return Response(
                    {'detail': 'Confirma la orden, identidad, licencia y garantía antes de entregar las llaves.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                with transaction.atomic():
                    inspeccion_id = crear_inspeccion(reserva, request.user, 'ENTREGA', request.data)
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO control_entrega
                                (reserva_id, inspeccion_entrega_id, trabajador_id,
                                 codigo_orden_verificado, identidad_verificada,
                                 licencia_verificada, garantia_verificada,
                                 llaves_entregadas, fecha_entrega)
                            VALUES (%s, %s, %s, TRUE, TRUE, TRUE, TRUE, TRUE, %s)
                            """,
                            [reserva.id, inspeccion_id, request.user.id, timezone.now()],
                        )
                    reserva.estado = 'EN_CURSO'
                    reserva.vehiculo.estado_operativo = 'EN_ARRENDAMIENTO'
                    reserva.vehiculo.save(update_fields=['estado_operativo'])
                    reserva.save(update_fields=['estado'])
                    HistorialEstadoReserva.objects.create(
                        reserva=reserva,
                        estado_anterior='CONFIRMADA',
                        estado_nuevo='EN_CURSO',
                        actor_tipo='TRABAJADOR',
                        trabajador=request.user,
                        fecha_cambio=timezone.now(),
                    )
            except ValueError as error:
                return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        elif nuevo == 'COMPLETADA':
            if reserva.estado != 'EN_CURSO':
                return Response({'detail': 'Solo una reserva en curso puede devolverse.'}, status=400)
            try:
                kilometraje = int(request.data['kilometraje'])
                if kilometraje < reserva.vehiculo.kilometraje_actual:
                    return Response({'kilometraje': 'El kilometraje no puede ser menor al anterior.'}, status=400)
                with transaction.atomic():
                    crear_inspeccion(reserva, request.user, 'DEVOLUCION', request.data)
                    requiere_revision = request.data.get('requiere_revision') is True
                    reserva.vehiculo.kilometraje_actual = kilometraje
                    reserva.vehiculo.estado_operativo = 'MANTENCION' if requiere_revision else 'ACTIVO'
                    reserva.vehiculo.save(update_fields=('kilometraje_actual', 'estado_operativo'))
                    reserva.estado = 'COMPLETADA'
                    reserva.save(update_fields=['estado'])
                    HistorialEstadoReserva.objects.create(
                        reserva=reserva,
                        estado_anterior='EN_CURSO',
                        estado_nuevo='COMPLETADA',
                        actor_tipo='TRABAJADOR',
                        trabajador=request.user,
                        observacion=str(request.data.get('observaciones') or ''),
                        fecha_cambio=timezone.now(),
                    )
            except (ValueError, KeyError) as error:
                return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(
                {'estado': 'Solo puedes pasar a EN_CURSO (entrega) o COMPLETADA (devolución).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(reserva).data)

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        reserva = self.get_object()
        if reserva.estado != 'PENDIENTE_PAGO':
            return Response(
                {'detail': 'Una reserva con pago debe seguir el proceso formal de cancelación y reembolso.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            orden = OrdenCompra.objects.filter(reserva=reserva).first()
            if orden:
                orden.estado = 'ANULADA'
                orden.save(update_fields=['estado'])
                orden.pagos.filter(estado_pago='PENDIENTE').update(estado_pago='RECHAZADO')
            reserva.estado = 'CANCELADA'
            reserva.save(update_fields=['estado'])
            HistorialEstadoReserva.objects.create(
                reserva=reserva,
                estado_anterior='PENDIENTE_PAGO',
                estado_nuevo='CANCELADA',
                actor_tipo='TRABAJADOR',
                trabajador=request.user,
                fecha_cambio=timezone.now(),
            )
        return Response(self.get_serializer(reserva).data)


class CancelacionViewSet(viewsets.ModelViewSet):
    serializer_class = CancelacionSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action == 'cotizacion':
            return [IsAuthenticated()]
        if self.action in ('create', 'list', 'retrieve'):
            return [IsAuthenticated()]
        return [EsStaff()]

    def get_queryset(self):
        queryset = Cancelacion.objects.select_related(
            'reserva', 'reserva__cliente', 'trabajador_revisor',
        ).order_by('-fecha_solicitud')
        usuario = self.request.user
        if usuario and usuario.is_authenticated and not es_trabajador(usuario):
            queryset = queryset.filter(reserva__cliente_id=usuario.id)
        estado = self.request.query_params.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)
        return queryset

    @action(detail=False, methods=['get'])
    def notificaciones(self, request):
        pendientes = self.get_queryset().filter(estado='PENDIENTE')
        return Response({
            'cantidad': pendientes.count(),
            'ids': list(pendientes.values_list('id', flat=True)[:50]),
        })

    def _solicitud_activa(self, reserva):
        return Cancelacion.objects.filter(
            reserva=reserva,
            estado__in=ESTADOS_CANCELACION_ACTIVA,
        ).order_by('-fecha_solicitud').first()

    def _respuesta_solicitud_existente(self, reserva):
        solicitud = self._solicitud_activa(reserva)
        if solicitud is None:
            return None
        datos = self.get_serializer(solicitud).data
        datos['solicitud_preexistente'] = True
        return Response(datos)

    @action(detail=False, methods=['get'])
    def cotizacion(self, request):
        codigo = str(request.query_params.get('codigo') or '').strip()
        if not codigo:
            return Response({'codigo': 'Ingresa el código de reserva.'}, status=400)
        reserva = Reserva.objects.filter(codigo__iexact=codigo).first()
        if reserva is None or (
            not es_trabajador(request.user)
            and reserva.cliente_id != request.user.id
        ):
            return Response({'detail': 'No se encontró una reserva asociada a tu cuenta.'}, status=404)
        if reserva.estado == 'CANCELACION_EN_PROCESO':
            solicitud = self._solicitud_activa(reserva)
            if solicitud is None:
                return Response(
                    {'detail': 'La reserva tiene una cancelación en proceso; contacta al equipo de soporte.'},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response({
                'codigo': reserva.codigo,
                'solicitud_preexistente': True,
                'estado': solicitud.estado,
                'fecha_solicitud': solicitud.fecha_solicitud,
            })
        if reserva.estado != 'CONFIRMADA':
            return Response(
                {'detail': 'Solo se pueden cotizar reservas confirmadas.'},
                status=400,
            )
        try:
            cotizacion = cotizar_devolucion(reserva)
        except ValueError as error:
            return Response({'detail': str(error)}, status=409)
        return Response({
            'codigo': reserva.codigo,
            'vehiculo': f'{reserva.modelo.marca} {reserva.modelo.nombre_modelo}',
            **{campo: str(valor) if isinstance(valor, Decimal) else valor
               for campo, valor in cotizacion.items()},
        })

    def create(self, request, *args, **kwargs):
        datos = request.data.copy()
        codigo = str(datos.get('codigo_reserva') or datos.get('codigo') or '').strip()
        if codigo:
            reserva = Reserva.objects.filter(codigo__iexact=codigo).first()
            if reserva is None:
                return Response({'codigo': 'La reserva indicada no existe.'}, status=status.HTTP_404_NOT_FOUND)
            datos['reserva'] = reserva.pk

        serializer = self.get_serializer(data=datos)
        serializer.is_valid(raise_exception=True)
        reserva = serializer.validated_data['reserva']
        if not es_trabajador(request.user) and reserva.cliente_id != request.user.id:
            return Response({'detail': 'La reserva no pertenece a tu cuenta.'}, status=status.HTTP_403_FORBIDDEN)
        if reserva.estado == 'CANCELACION_EN_PROCESO':
            respuesta_existente = self._respuesta_solicitud_existente(reserva)
            if respuesta_existente is not None:
                return respuesta_existente
            return Response(
                {'detail': 'La reserva tiene una cancelación en proceso, pero no se encontró su solicitud.'},
                status=status.HTTP_409_CONFLICT,
            )
        if reserva.estado != 'CONFIRMADA':
            return Response({'detail': 'Solo se pueden solicitar cancelaciones para reservas confirmadas.'}, status=400)
        if not Pago.objects.filter(orden__reserva=reserva, estado_pago='AUTORIZADO').exists():
            return Response({'detail': 'La reserva no tiene un pago autorizado que pueda reembolsarse.'}, status=400)
        try:
            cotizacion = cotizar_devolucion(reserva)
        except ValueError as error:
            return Response({'detail': str(error)}, status=409)
        try:
            with transaction.atomic():
                reserva = Reserva.objects.select_for_update().get(pk=reserva.pk)
                if reserva.estado != 'CONFIRMADA':
                    if reserva.estado == 'CANCELACION_EN_PROCESO':
                        respuesta_existente = self._respuesta_solicitud_existente(reserva)
                        if respuesta_existente is not None:
                            return respuesta_existente
                    return Response(
                        {'detail': 'La reserva ya no está disponible para cancelación.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                reserva.estado = 'CANCELACION_EN_PROCESO'
                reserva.save(update_fields=['estado'])
                cancelacion = serializer.save(
                    monto_solicitado=None,
                    fecha_solicitud=timezone.now(),
                    estado='PENDIENTE',
                )
                orden = OrdenCompra.objects.select_for_update().get(reserva=reserva)
                orden.estado = 'REEMBOLSO_PENDIENTE'
                orden.save(update_fields=['estado'])
                HistorialEstadoReserva.objects.create(
                    reserva=reserva,
                    estado_anterior='CONFIRMADA',
                    estado_nuevo='CANCELACION_EN_PROCESO',
                    actor_tipo='CLIENTE',
                    observacion='Solicitud de cancelación enviada.',
                    fecha_cambio=timezone.now(),
                )
        except IntegrityError:
            respuesta_existente = self._respuesta_solicitud_existente(reserva)
            if respuesta_existente is not None:
                return respuesta_existente
            return Response(
                {'detail': 'Ya existe una solicitud activa para esta reserva.'},
                status=status.HTTP_409_CONFLICT,
            )
        from .correos import notificar_cliente_cancelacion, notificar_nueva_cancelacion

        avisos = []
        if not notificar_nueva_cancelacion(cancelacion, cotizacion):
            avisos.append('No se pudo enviar el aviso al equipo.')
        if not notificar_cliente_cancelacion(cancelacion, cotizacion):
            avisos.append('No se pudo enviar la confirmación por correo.')
        datos = self.get_serializer(cancelacion).data
        datos['fundamento'] = cotizacion['fundamento']
        datos['aviso'] = ' '.join(avisos)
        return Response(datos, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def derivar_finanzas(self, request, pk=None):
        cancelacion = self.get_object()
        if cancelacion.estado not in ('PENDIENTE', 'EN_REVISION', 'APROBADA'):
            return Response({'detail': 'La solicitud no está disponible para derivar.'}, status=400)
        try:
            cotizacion = cotizar_devolucion(cancelacion.reserva)
        except ValueError as error:
            return Response({'detail': str(error)}, status=status.HTTP_409_CONFLICT)
        cancelacion.estado = 'DERIVADA_FINANZAS'
        cancelacion.fecha_revision = timezone.now()
        cancelacion.trabajador_revisor = request.user
        cancelacion.save(update_fields=('estado', 'fecha_revision', 'trabajador_revisor'))
        from .correos import derivar_cancelacion_a_finanzas

        datos = self.get_serializer(cancelacion).data
        if not derivar_cancelacion_a_finanzas(cancelacion, cotizacion):
            datos['aviso'] = 'La solicitud se derivó, pero no se pudo notificar a Finanzas.'
        return Response(datos)

    @action(detail=True, methods=['post'])
    def cerrar_sin_reembolso(self, request, pk=None):
        cancelacion = self.get_object()
        if cancelacion.estado != 'DERIVADA_FINANZAS':
            return Response(
                {'detail': 'Finanzas debe revisar la solicitud antes de cerrarla.'},
                status=status.HTTP_409_CONFLICT,
            )
        if cancelacion.monto_solicitado is not None:
            return Response(
                {'detail': 'Esta solicitud ya tiene un monto de devolución registrado.'},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            cancelacion.monto_solicitado = Decimal('0')
            cancelacion.estado = 'CERRADA'
            cancelacion.fecha_revision = timezone.now()
            cancelacion.trabajador_revisor = request.user
            cancelacion.save(update_fields=(
                'monto_solicitado', 'estado', 'fecha_revision', 'trabajador_revisor',
            ))
            reserva = cancelacion.reserva
            reserva.estado = 'CANCELADA'
            reserva.save(update_fields=['estado'])
            orden = OrdenCompra.objects.get(reserva=reserva)
            orden.estado = 'ANULADA'
            orden.save(update_fields=['estado'])
            HistorialEstadoReserva.objects.create(
                reserva=reserva,
                estado_anterior='CANCELACION_EN_PROCESO',
                estado_nuevo='CANCELADA',
                actor_tipo='TRABAJADOR',
                trabajador=request.user,
                observacion='Cancelación cerrada sin monto a devolver según la política informada.',
                fecha_cambio=timezone.now(),
            )
        from .correos import notificar_cliente_cancelacion_cerrada_sin_reembolso

        datos = self.get_serializer(cancelacion).data
        if not notificar_cliente_cancelacion_cerrada_sin_reembolso(cancelacion):
            datos['aviso'] = 'La cancelación se cerró, pero no se pudo enviar el correo al cliente.'
        return Response(datos)

    @action(detail=True, methods=['get'])
    def datos_finanzas(self, request, pk=None):
        cancelacion = self.get_object()
        if cancelacion.estado != 'DERIVADA_FINANZAS':
            return Response(
                {'detail': 'Los datos bancarios solo se habilitan al derivar la solicitud a Finanzas.'},
                status=status.HTTP_409_CONFLICT,
            )
        encryption_key = settings.BANK_DATA_ENCRYPTION_KEY
        if not encryption_key:
            return Response(
                {'detail': 'BANK_DATA_ENCRYPTION_KEY no está configurada.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT pgp_sym_decrypt(%s, %s)',
                [cancelacion.numero_cuenta_cifrado, encryption_key],
            )
            cuenta = cursor.fetchone()[0]
        return Response({
            'banco_destino': cancelacion.banco_destino,
            'tipo_cuenta': cancelacion.tipo_cuenta,
            'numero_cuenta': cuenta,
            'tipo_documento_titular': cancelacion.tipo_documento_titular,
            'rut_titular': cancelacion.rut_titular,
            'nombre_titular': cancelacion.nombre_titular,
        })

    @action(detail=True, methods=['get'])
    def comprobante_finanzas(self, request, pk=None):
        cancelacion = self.get_object()
        reembolso = cancelacion.reembolso_set.order_by('-id').first()
        if not reembolso or not reembolso.comprobante_url:
            return Response(
                {'detail': 'No hay comprobante de transferencia asociado.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            archivo = default_storage.open(reembolso.comprobante_url, 'rb')
        except FileNotFoundError:
            logger.exception(
                'No se encontró el comprobante guardado para cancelación %s.',
                cancelacion.pk,
            )
            return Response(
                {'detail': 'No se encontró el archivo del comprobante.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        extension = Path(reembolso.comprobante_url).suffix.lower()
        tipo = TIPOS_COMPROBANTE[extension][0]
        nombre = f'comprobante-transferencia-{cancelacion.reserva.codigo}{extension}'
        return FileResponse(archivo, as_attachment=True, filename=nombre, content_type=tipo)

    @action(detail=True, methods=['post'])
    def registrar_reembolso(self, request, pk=None):
        cancelacion = self.get_object()
        if cancelacion.estado != 'DERIVADA_FINANZAS':
            return Response({'detail': 'Primero deriva la solicitud a Finanzas.'}, status=400)
        referencia = str(request.data.get('numero_transaccion_externa') or '').strip()
        monto_raw = request.data.get('monto')
        if not referencia or len(referencia) > 150:
            return Response({'numero_transaccion_externa': 'Indica la transacción informada por Finanzas.'}, status=400)
        try:
            monto = Decimal(str(monto_raw))
        except (ValueError, TypeError, ArithmeticError):
            return Response({'monto': 'Indica un monto válido.'}, status=400)
        if not monto.is_finite() or monto <= 0:
            return Response({'monto': 'El monto transferido debe ser mayor que cero.'}, status=400)
        monto_pagado = Pago.objects.filter(
            orden__reserva=cancelacion.reserva,
            estado_pago='AUTORIZADO',
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0')
        if monto > monto_pagado:
            return Response({'monto': 'El monto no puede superar el total pagado.'}, status=400)
        archivo = request.FILES.get('comprobante')
        if archivo is None:
            return Response(
                {'comprobante': 'Adjunta el comprobante de la transferencia.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            cancelacion = self.get_queryset().select_for_update().get(pk=cancelacion.pk)
            if cancelacion.estado != 'DERIVADA_FINANZAS':
                return Response(
                    {'detail': 'La solicitud ya fue procesada por Finanzas.'},
                    status=status.HTTP_409_CONFLICT,
                )
            ruta_comprobante, error_comprobante = guardar_comprobante_reembolso(archivo)
            if error_comprobante:
                return Response(
                    {'comprobante': error_comprobante},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            Reembolso.objects.create(
                solicitud_cancelacion=cancelacion,
                monto=monto,
                estado='COMPLETADO',
                departamento_externo='Finanzas',
                numero_transaccion_externa=referencia,
                comprobante_url=ruta_comprobante,
                fecha_reembolso=timezone.now(),
                ingresado_por_trabajador=request.user,
                observaciones=str(request.data.get('observaciones') or ''),
            )
            cancelacion.monto_solicitado = monto
            cancelacion.estado = 'CERRADA'
            cancelacion.fecha_revision = timezone.now()
            cancelacion.trabajador_revisor = request.user
            cancelacion.save(update_fields=(
                'monto_solicitado', 'estado', 'fecha_revision', 'trabajador_revisor',
            ))
            reserva = cancelacion.reserva
            reserva.estado = 'CANCELADA'
            reserva.save(update_fields=['estado'])
            orden = OrdenCompra.objects.get(reserva=reserva)
            orden.estado = 'REEMBOLSADA'
            orden.save(update_fields=['estado'])
            monto_autorizado = orden.pagos.filter(
                estado_pago='AUTORIZADO',
            ).aggregate(total=Sum('monto'))['total'] or Decimal('0')
            if monto == monto_autorizado:
                orden.pagos.filter(estado_pago='AUTORIZADO').update(
                    estado_pago='REEMBOLSADO',
                )
            HistorialEstadoReserva.objects.create(
                reserva=reserva,
                estado_anterior='CANCELACION_EN_PROCESO',
                estado_nuevo='CANCELADA',
                actor_tipo='TRABAJADOR',
                trabajador=request.user,
                observacion=f'Reembolso externo registrado: {referencia}.',
                fecha_cambio=timezone.now(),
            )
        from .correos import notificar_cliente_reembolso

        datos = self.get_serializer(cancelacion).data
        if not notificar_cliente_reembolso(
            cancelacion, monto, referencia, ruta_comprobante
        ):
            datos['aviso'] = 'El reembolso se registró, pero no se pudo enviar el correo al cliente.'
        return Response(datos)

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        cancelacion = self.get_object()
        if cancelacion.estado in ('CERRADA', 'REEMBOLSO_REGISTRADO', 'RECHAZADA'):
            return Response({'detail': 'La solicitud ya fue cerrada.'}, status=400)
        motivo = str(request.data.get('motivo_rechazo') or '').strip()
        if not motivo:
            return Response({'motivo_rechazo': 'Indica el motivo del rechazo.'}, status=400)
        with transaction.atomic():
            cancelacion.estado = 'RECHAZADA'
            cancelacion.fecha_revision = timezone.now()
            cancelacion.trabajador_revisor = request.user
            cancelacion.motivo_rechazo = motivo
            cancelacion.save(update_fields=(
                'estado', 'fecha_revision', 'trabajador_revisor', 'motivo_rechazo',
            ))
            reserva = cancelacion.reserva
            reserva.estado = 'CONFIRMADA'
            reserva.save(update_fields=['estado'])
            HistorialEstadoReserva.objects.create(
                reserva=reserva,
                estado_anterior='CANCELACION_EN_PROCESO',
                estado_nuevo='CONFIRMADA',
                actor_tipo='TRABAJADOR',
                trabajador=request.user,
                observacion=f'Solicitud de cancelación rechazada: {motivo}',
                fecha_cambio=timezone.now(),
            )
        from .correos import notificar_cliente_cancelacion_rechazada

        datos = self.get_serializer(cancelacion).data
        if not notificar_cliente_cancelacion_rechazada(cancelacion):
            datos['aviso'] = 'La solicitud se rechazó, pero no se pudo enviar el correo al cliente.'
        return Response(datos)
