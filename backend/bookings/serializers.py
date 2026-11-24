import math
import re
from datetime import date, time
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import connection
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework import serializers

from fleet.models import Modelo, Producto, Seguro, Sucursal, Tarifa, Vehiculo
from payments.models import DatosFacturacion, OrdenCompra, OrdenDetalle, Pago
from users.models import Cliente, DocumentoCliente, LicenciaConducir

from .models import (
    Cancelacion,
    Contrato,
    ContratoVersion,
    HistorialEstadoReserva,
    Reserva,
    ReservaProducto,
    ReservaSeguro,
)


def edad_en_anios(fecha_nacimiento, hoy=None):
    hoy = hoy or date.today()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def rut_valido(numero):
    limpio = re.sub(r'[.\-\s]', '', numero or '').upper()
    if len(limpio) < 2 or not limpio[:-1].isdigit() or limpio[-1] not in '0123456789K':
        return False
    suma = 0
    multiplicador = 2
    for digito in reversed(limpio[:-1]):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - (suma % 11)
    esperado = '0' if resto == 11 else 'K' if resto == 10 else str(resto)
    return esperado == limpio[-1]


class ReservaSeguroSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservaSeguro
        fields = ('nombre_snapshot', 'precio_diario_snapshot', 'deducible_snapshot', 'dias_cobrados', 'subtotal')


class ReservaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservaProducto
        fields = (
            'nombre_snapshot', 'cantidad', 'precio_unitario_snapshot',
            'dias_cobrados', 'subtotal',
        )


class ReservaSerializer(serializers.ModelSerializer):
    modelo_id = serializers.PrimaryKeyRelatedField(
        source='modelo', queryset=Modelo.objects.filter(activo=True), write_only=True
    )
    cliente_id = serializers.PrimaryKeyRelatedField(
        source='cliente', queryset=Cliente.objects.filter(activo=True),
        write_only=True, required=False
    )
    modelo = serializers.SerializerMethodField()
    vehiculo = serializers.SerializerMethodField()
    cliente = serializers.SerializerMethodField()
    monto_garantia = serializers.SerializerMethodField()
    seguros = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, write_only=True
    )
    productos = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )
    tipo_documento_solicitado = serializers.ChoiceField(
        choices=OrdenCompra.TIPOS_DOCUMENTO, required=False, default='BOLETA', write_only=True
    )
    datos_facturacion = serializers.DictField(required=False, write_only=True)
    tipo_documento = serializers.ChoiceField(
        choices=(('RUT', 'RUT'), ('PASAPORTE', 'Pasaporte')), write_only=True
    )
    numero_documento = serializers.CharField(max_length=30, write_only=True)
    licencia = serializers.CharField(max_length=50, write_only=True)
    licencia_vencimiento = serializers.DateField(write_only=True)
    fecha_nacimiento = serializers.DateField(write_only=True)
    nombre = serializers.CharField(max_length=70, required=False, write_only=True)
    apellido = serializers.CharField(max_length=70, required=False, write_only=True)
    correo = serializers.EmailField(max_length=150, required=False, write_only=True)
    telefono = serializers.CharField(max_length=25, required=False, allow_blank=True, write_only=True)
    firma_condiciones = serializers.BooleanField(write_only=True)
    sucursal_retiro = serializers.PrimaryKeyRelatedField(
        queryset=Sucursal.objects.filter(activa=True), required=False
    )
    sucursal_devolucion = serializers.PrimaryKeyRelatedField(
        queryset=Sucursal.objects.filter(activa=True), required=False
    )

    class Meta:
        model = Reserva
        fields = (
            'id', 'codigo', 'cliente_id', 'cliente', 'modelo_id', 'modelo', 'vehiculo',
            'sucursal_retiro', 'sucursal_devolucion', 'fecha_hora_retiro',
            'fecha_hora_devolucion', 'canal', 'estado', 'subtotal', 'descuento',
            'total', 'monto_garantia', 'fecha_creacion', 'seguros', 'productos',
            'tipo_documento_solicitado', 'datos_facturacion', 'tipo_documento',
            'numero_documento', 'licencia', 'licencia_vencimiento',
            'fecha_nacimiento', 'nombre', 'apellido', 'correo', 'telefono',
            'firma_condiciones',
        )
        read_only_fields = (
            'id', 'codigo', 'cliente', 'modelo', 'vehiculo', 'canal', 'estado',
            'subtotal', 'descuento', 'total', 'monto_garantia', 'fecha_creacion',
        )

    def get_modelo(self, obj):
        return {
            'id': obj.modelo_id,
            'marca': obj.modelo.marca,
            'nombre_modelo': obj.modelo.nombre_modelo,
        }

    def get_vehiculo(self, obj):
        return {'id': obj.vehiculo_id, 'patente': obj.vehiculo.patente}

    def get_cliente(self, obj):
        return {
            'id': obj.cliente_id,
            'nombre': f'{obj.cliente.nombre} {obj.cliente.apellido}',
            'correo': obj.cliente.correo,
        }

    def get_monto_garantia(self, obj):
        return str(obj.modelo.categoria.monto_garantia)

    def validate(self, attrs):
        if self.instance is not None:
            allowed = {'fecha_hora_retiro', 'fecha_hora_devolucion', 'firma_condiciones'}
            if set(attrs) - allowed:
                raise serializers.ValidationError(
                    'Solo se pueden modificar las fechas de una reserva pendiente.'
                )
            if self.instance.estado != 'PENDIENTE_PAGO':
                raise serializers.ValidationError(
                    'Solo se pueden modificar reservas pendientes de pago.'
                )
            if attrs.get('firma_condiciones') is not True:
                raise serializers.ValidationError({
                    'firma_condiciones': 'El cliente debe aceptar las nuevas fechas.'
                })
            retiro = attrs.get('fecha_hora_retiro', self.instance.fecha_hora_retiro)
            devolucion = attrs.get('fecha_hora_devolucion', self.instance.fecha_hora_devolucion)
            if devolucion <= retiro:
                raise serializers.ValidationError({
                    'fecha_hora_devolucion': 'La devolución debe ser posterior al retiro.'
                })
            if retiro < timezone.now():
                raise serializers.ValidationError({
                    'fecha_hora_retiro': 'La fecha y hora de retiro deben ser futuras.'
                })
            for field, value in (
                ('fecha_hora_retiro', retiro),
                ('fecha_hora_devolucion', devolucion),
            ):
                local = timezone.localtime(value)
                if not time(9, 0) <= local.time().replace(tzinfo=None) <= time(18, 0):
                    raise serializers.ValidationError({
                        field: 'El horario debe estar entre las 09:00 y las 18:00.'
                    })
            return attrs

        request = self.context.get('request')
        if request and request.user.is_authenticated and not hasattr(request.user, 'rol'):
            attrs['nombre'] = request.user.nombre
            attrs['apellido'] = request.user.apellido
            attrs['correo'] = request.user.correo

        retiro = attrs.get('fecha_hora_retiro')
        devolucion = attrs.get('fecha_hora_devolucion')
        if not retiro or not devolucion:
            raise serializers.ValidationError('Debes seleccionar fecha y hora de retiro y devolución.')
        if devolucion <= retiro:
            raise serializers.ValidationError({
                'fecha_hora_devolucion': 'La devolución debe ser posterior al retiro.'
            })
        if retiro < timezone.now():
            raise serializers.ValidationError({
                'fecha_hora_retiro': 'La fecha y hora de retiro deben ser futuras.'
            })

        for field, value in (('fecha_hora_retiro', retiro), ('fecha_hora_devolucion', devolucion)):
            local = timezone.localtime(value)
            if not time(9, 0) <= local.time().replace(tzinfo=None) <= time(18, 0):
                raise serializers.ValidationError({
                    field: 'El horario debe estar entre las 09:00 y las 18:00.'
                })

        if attrs.get('firma_condiciones') is not True:
            raise serializers.ValidationError({
                'firma_condiciones': 'Debes aceptar el contrato y consentimiento.'
            })

        tipo_documento = attrs.get('tipo_documento')
        numero = attrs.get('numero_documento', '').strip()
        if tipo_documento == 'RUT' and not rut_valido(numero):
            raise serializers.ValidationError({'numero_documento': 'Ingresa un RUT válido.'})
        if tipo_documento == 'PASAPORTE' and (
            len(numero) < 5 or not numero.replace('-', '').isalnum()
        ):
            raise serializers.ValidationError({'numero_documento': 'Ingresa un pasaporte válido.'})

        hoy = timezone.localdate()
        nacimiento = attrs.get('fecha_nacimiento')
        vencimiento = attrs.get('licencia_vencimiento')
        if not nacimiento or nacimiento > hoy or edad_en_anios(nacimiento, hoy) < 18:
            raise serializers.ValidationError({
                'fecha_nacimiento': 'El arrendatario debe tener al menos 18 años.'
            })
        if not vencimiento or vencimiento <= hoy:
            raise serializers.ValidationError({
                'licencia_vencimiento': 'La licencia de conducir debe estar vigente.'
            })
        if not attrs.get('nombre') or not attrs.get('apellido') or not attrs.get('correo'):
            raise serializers.ValidationError('Completa nombre, apellido y correo de contacto.')

        tipo_documento_solicitado = attrs.get('tipo_documento_solicitado', 'BOLETA')
        datos_facturacion = attrs.get('datos_facturacion') or {}
        if tipo_documento_solicitado == 'FACTURA':
            requeridos = ('rut_receptor', 'razon_social', 'giro', 'direccion', 'comuna', 'correo')
            permitidos = set(requeridos)
            faltantes = [campo for campo in requeridos if not str(datos_facturacion.get(campo, '')).strip()]
            if faltantes:
                raise serializers.ValidationError({
                    'datos_facturacion': 'Para solicitar factura completa: ' + ', '.join(faltantes)
                })
            if set(datos_facturacion) - permitidos:
                raise serializers.ValidationError({
                    'datos_facturacion': 'Se enviaron campos de facturación no permitidos.'
                })
            if not rut_valido(datos_facturacion.get('rut_receptor', '')):
                raise serializers.ValidationError({
                    'datos_facturacion': 'El RUT del receptor no es válido.'
                })

        productos = attrs.get('productos', [])
        if any(set(item) - {'id', 'cantidad'} for item in productos):
            raise serializers.ValidationError({
                'productos': 'Cada producto solo puede contener id y cantidad.'
            })
        for item in productos:
            if not isinstance(item.get('id'), int) or not isinstance(item.get('cantidad', 1), int):
                raise serializers.ValidationError({
                    'productos': 'El id y la cantidad deben ser números enteros.'
                })
            if item.get('cantidad', 1) < 1:
                raise serializers.ValidationError({'productos': 'La cantidad debe ser mayor que cero.'})
            if item.get('cantidad', 1) > 32767:
                raise serializers.ValidationError({'productos': 'La cantidad excede el máximo permitido.'})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        is_worker = hasattr(user, 'rol')
        requested_customer = validated_data.pop('cliente', None)
        if not is_worker and requested_customer is not None:
            raise serializers.ValidationError({
                'cliente_id': 'No puedes crear una reserva para otro cliente.'
            })
        if is_worker:
            customer = requested_customer
            if customer is None:
                raise serializers.ValidationError({
                    'cliente_id': 'Selecciona un cliente para la reserva presencial.'
                })
        elif user.is_authenticated:
            customer = user
        else:
            raise serializers.ValidationError({
                'detail': 'Debes iniciar sesión con Google para crear una reserva.'
            })

        model = validated_data.pop('modelo')
        insurance_ids = validated_data.pop('seguros', [])
        product_inputs = validated_data.pop('productos', [])
        document_type = validated_data.pop('tipo_documento_solicitado', 'BOLETA')
        billing_data = validated_data.pop('datos_facturacion', {})
        accepted = validated_data.pop('firma_condiciones')
        document_kind = validated_data.pop('tipo_documento')
        document_number = validated_data.pop('numero_documento').strip()
        license_number = validated_data.pop('licencia').strip()
        license_expiry = validated_data.pop('licencia_vencimiento')
        birth_date = validated_data.pop('fecha_nacimiento')
        nombre = validated_data.pop('nombre')
        apellido = validated_data.pop('apellido')
        correo = validated_data.pop('correo')
        telefono = validated_data.pop('telefono', None) or None
        puede_editar_cliente = not is_worker or user.rol == 'admin'
        if puede_editar_cliente:
            customer.nombre = nombre
            customer.apellido = apellido
            customer.correo = correo
            customer.telefono = telefono
            customer.fecha_nacimiento = birth_date
            customer.save(update_fields=(
                'nombre', 'apellido', 'correo', 'telefono', 'fecha_nacimiento',
            ))
            try:
                with transaction.atomic():
                    DocumentoCliente.objects.update_or_create(
                        cliente=customer,
                        tipo_documento=document_kind,
                        pais_emision='CHILE',
                        defaults={
                            'numero_documento': document_number,
                            'es_principal': True,
                        },
                    )
                    LicenciaConducir.objects.update_or_create(
                        cliente=customer,
                        numero_licencia=license_number,
                        pais_emision='Chile',
                        defaults={'fecha_vencimiento': license_expiry},
                    )
            except IntegrityError:
                raise serializers.ValidationError({
                    'numero_documento': 'El documento o licencia ya está registrado en otra cuenta.'
                }) from None
        else:
            documento = customer.documentos.filter(es_principal=True).first()
            licencia = customer.licencias.order_by('-id').first()
            if (
                nombre != customer.nombre
                or apellido != customer.apellido
                or correo.lower() != customer.correo.lower()
                or telefono != (customer.telefono or None)
                or birth_date != customer.fecha_nacimiento
                or documento is None
                or documento.tipo_documento != document_kind
                or documento.numero_documento.lower() != document_number.lower()
                or licencia is None
                or licencia.numero_licencia.lower() != license_number.lower()
                or licencia.fecha_vencimiento != license_expiry
            ):
                raise serializers.ValidationError(
                    'Solo un administrador puede modificar los datos del cliente.'
                )

        retiro = validated_data['fecha_hora_retiro']
        devolucion = validated_data['fecha_hora_devolucion']
        dias = max(1, math.ceil((devolucion - retiro).total_seconds() / 86400))
        tarifa = model.tarifa_set.filter(
            activa=True,
            fecha_desde__lte=timezone.localdate(retiro),
        ).filter(
            models_q_fecha(timezone.localdate(retiro))
        ).order_by('-fecha_desde', '-id').first()
        if tarifa is None:
            raise serializers.ValidationError({'modelo_id': 'Este modelo no tiene una tarifa vigente.'})

        seguros = list(Seguro.objects.filter(id__in=set(insurance_ids), activo=True))
        if len(seguros) != len(set(insurance_ids)):
            raise serializers.ValidationError({'seguros': 'Uno o más seguros ya no están disponibles.'})
        product_ids = {item['id'] for item in product_inputs}
        products = {
            product.id: product
            for product in Producto.objects.filter(id__in=product_ids, activo=True)
        }
        if len(products) != len(product_ids):
            raise serializers.ValidationError({'productos': 'Uno o más productos ya no están disponibles.'})

        sucursal = validated_data.pop('sucursal_retiro', None)
        if sucursal is None:
            sucursal = getattr(user, 'sucursal', None) if is_worker else None
        if sucursal is None:
            sucursal = Sucursal.objects.filter(activa=True).order_by('id').first()
        if sucursal is None:
            raise serializers.ValidationError('No hay sucursales activas configuradas.')
        sucursal_devolucion = validated_data.pop('sucursal_devolucion', None) or sucursal

        ocupadas = Reserva.objects.filter(
            vehiculo_id=OuterRef('pk'),
            estado__in=(
                'PENDIENTE_PAGO', 'CONFIRMADA', 'EN_CURSO', 'CANCELACION_EN_PROCESO',
            ),
            fecha_hora_retiro__lt=devolucion,
            fecha_hora_devolucion__gt=retiro,
        )
        unidades = Vehiculo.objects.filter(
            modelo=model,
            estado_operativo='ACTIVO',
            sucursal_actual=sucursal,
        ).annotate(
            ocupada=Exists(ocupadas)
        ).filter(ocupada=False).order_by('id')

        unit = None
        for candidate in unidades:
            try:
                with transaction.atomic():
                    unit = Vehiculo.objects.select_for_update().get(pk=candidate.pk)
                    if Reserva.objects.filter(
                        vehiculo=unit,
                        estado__in=(
                            'PENDIENTE_PAGO', 'CONFIRMADA', 'EN_CURSO', 'CANCELACION_EN_PROCESO',
                        ),
                        fecha_hora_retiro__lt=devolucion,
                        fecha_hora_devolucion__gt=retiro,
                    ).exists():
                        unit = None
                        continue
                    base_total = tarifa.precio_diario * dias
                    insurance_total = sum(
                        (insurance.precio_diario * dias for insurance in seguros), Decimal('0')
                    )
                    products_total = sum(
                        (
                            products[item['id']].precio_diario
                            * item.get('cantidad', 1) * dias
                            for item in product_inputs
                        ),
                        Decimal('0'),
                    )
                    subtotal = base_total + insurance_total + products_total
                    reservation = Reserva.objects.create(
                        codigo=f'RC-TEMP-{uuid4().hex[:12].upper()}',
                        cliente=customer,
                        modelo=model,
                        vehiculo=unit,
                        sucursal_retiro=sucursal,
                        sucursal_devolucion=sucursal_devolucion,
                        fecha_hora_retiro=retiro,
                        fecha_hora_devolucion=devolucion,
                        canal='SUCURSAL' if is_worker else 'WEB',
                        estado='PENDIENTE_PAGO',
                        subtotal=subtotal,
                        descuento=Decimal('0'),
                        total=subtotal,
                        fecha_creacion=timezone.now(),
                        creado_por_trabajador=user if is_worker else None,
                    )
                    break
            except IntegrityError:
                unit = None

        if unit is None:
            raise serializers.ValidationError({
                'modelo_id': 'No hay unidades disponibles de este modelo para esas fechas.'
            })

        reservation.codigo = f'RC-{reservation.pk:06d}'
        reservation.save(update_fields=['codigo'])

        for insurance in seguros:
            line_total = insurance.precio_diario * dias
            ReservaSeguro.objects.create(
                reserva=reservation,
                seguro_id=insurance.id,
                nombre_snapshot=insurance.nombre,
                precio_diario_snapshot=insurance.precio_diario,
                deducible_snapshot=insurance.deducible_monto,
                dias_cobrados=dias,
                subtotal=line_total,
            )
        for item in product_inputs:
            product = products[item['id']]
            quantity = item.get('cantidad', 1)
            line_total = product.precio_diario * quantity * dias
            ReservaProducto.objects.create(
                reserva=reservation,
                producto_id=product.id,
                nombre_snapshot=product.nombre,
                cantidad=quantity,
                precio_unitario_snapshot=product.precio_diario,
                dias_cobrados=dias,
                subtotal=line_total,
            )

        order = OrdenCompra.objects.create(
            codigo_orden=f'OC-{uuid4().hex[:20].upper()}',
            reserva=reservation,
            subtotal=subtotal,
            descuento=Decimal('0'),
            total=subtotal,
            tipo_documento_solicitado=document_type,
            estado='PENDIENTE',
            fecha_creacion=timezone.now(),
        )
        OrdenDetalle.objects.create(
            orden=order,
            tipo_item='ARRIENDO',
            descripcion=f'Arriendo {model.marca} {model.nombre_modelo} por {dias} día(s)',
            cantidad=dias,
            precio_unitario=tarifa.precio_diario,
            subtotal=base_total,
        )
        for insurance in seguros:
            OrdenDetalle.objects.create(
                orden=order,
                tipo_item='SEGURO',
                descripcion=insurance.nombre,
                cantidad=dias,
                precio_unitario=insurance.precio_diario,
                subtotal=insurance.precio_diario * dias,
            )
        for item in product_inputs:
            product = products[item['id']]
            quantity = item.get('cantidad', 1)
            OrdenDetalle.objects.create(
                orden=order,
                tipo_item='PRODUCTO',
                descripcion=product.nombre,
                cantidad=quantity * dias,
                precio_unitario=product.precio_diario,
                subtotal=product.precio_diario * quantity * dias,
            )
        if document_type == 'FACTURA':
            DatosFacturacion.objects.create(
                orden=order,
                fecha_registro=timezone.now(),
                **billing_data,
            )

        version = ContratoVersion.objects.filter(activa=True).order_by('-vigente_desde').first()
        if version is None:
            version = ContratoVersion.objects.create(
                nombre='Contrato de arriendo',
                numero_version='1.0',
                archivo_plantilla='contrato-v1',
                vigente_desde=timezone.now(),
                activa=True,
            )
        Contrato.objects.create(
            reserva=reservation,
            contrato_version=version,
            aceptado=accepted,
            fecha_aceptacion=timezone.now(),
            ip_cliente=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            medio_aceptacion='SUCURSAL' if is_worker else 'WEB',
            trabajador_testigo=user if is_worker else None,
        )
        HistorialEstadoReserva.objects.create(
            reserva=reservation,
            estado_nuevo='PENDIENTE_PAGO',
            actor_tipo='TRABAJADOR' if is_worker else 'CLIENTE',
            trabajador=user if is_worker else None,
            observacion='Reserva creada.',
            fecha_cambio=timezone.now(),
        )
        return reservation

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Reserva.objects.select_for_update().get(pk=instance.pk)
        accepted = validated_data.pop('firma_condiciones')
        orden = OrdenCompra.objects.select_for_update().filter(
            reserva=instance,
        ).first()
        if orden is None or orden.estado != 'PENDIENTE' or Pago.objects.filter(orden=orden).exists():
            raise serializers.ValidationError(
                'No se pueden cambiar fechas después de iniciar el pago.'
            )

        retiro = validated_data.get('fecha_hora_retiro', instance.fecha_hora_retiro)
        devolucion = validated_data.get(
            'fecha_hora_devolucion', instance.fecha_hora_devolucion,
        )
        dias = max(1, math.ceil((devolucion - retiro).total_seconds() / 86400))
        tarifa = Tarifa.objects.filter(
            modelo=instance.modelo,
            activa=True,
            fecha_desde__lte=timezone.localdate(retiro),
        ).filter(
            models_q_fecha(timezone.localdate(retiro))
        ).order_by('-fecha_desde', '-id').first()
        if tarifa is None:
            raise serializers.ValidationError({
                'fecha_hora_retiro': 'No existe una tarifa vigente para las nuevas fechas.'
            })

        ocupadas = Reserva.objects.filter(
            vehiculo_id=OuterRef('pk'),
            estado__in=(
                'PENDIENTE_PAGO', 'CONFIRMADA', 'EN_CURSO',
                'CANCELACION_EN_PROCESO',
            ),
            fecha_hora_retiro__lt=devolucion,
            fecha_hora_devolucion__gt=retiro,
        ).exclude(pk=instance.pk)
        unidades = Vehiculo.objects.filter(
            modelo=instance.modelo,
            estado_operativo='ACTIVO',
            sucursal_actual=instance.sucursal_retiro,
        ).annotate(ocupada=Exists(ocupadas)).filter(
            ocupada=False,
        ).order_by('id')
        unidad = None
        for candidata in unidades:
            unidad_bloqueada = Vehiculo.objects.select_for_update().get(pk=candidata.pk)
            if not Reserva.objects.filter(
                vehiculo=unidad_bloqueada,
                estado__in=(
                    'PENDIENTE_PAGO', 'CONFIRMADA', 'EN_CURSO',
                    'CANCELACION_EN_PROCESO',
                ),
                fecha_hora_retiro__lt=devolucion,
                fecha_hora_devolucion__gt=retiro,
            ).exclude(pk=instance.pk).exists():
                unidad = unidad_bloqueada
                break
        if unidad is None:
            raise serializers.ValidationError({
                'fecha_hora_retiro': 'No hay un vehículo disponible para las nuevas fechas.'
            })

        base_total = tarifa.precio_diario * dias
        seguros = list(instance.seguros_reservados.all())
        productos = list(instance.detalles.all())
        seguros_total = Decimal('0')
        for seguro in seguros:
            seguro.dias_cobrados = dias
            seguro.subtotal = seguro.precio_diario_snapshot * dias
            seguros_total += seguro.subtotal
        productos_total = Decimal('0')
        for producto in productos:
            producto.dias_cobrados = dias
            producto.subtotal = producto.precio_unitario_snapshot * producto.cantidad * dias
            productos_total += producto.subtotal
        subtotal = base_total + seguros_total + productos_total
        total = subtotal - instance.descuento
        if total < 0:
            raise serializers.ValidationError('El descuento supera el nuevo subtotal.')

        anterior = instance.estado
        instance.fecha_hora_retiro = retiro
        instance.fecha_hora_devolucion = devolucion
        instance.vehiculo = unidad
        instance.subtotal = subtotal
        instance.total = total
        instance.save(update_fields=(
            'fecha_hora_retiro', 'fecha_hora_devolucion', 'vehiculo',
            'subtotal', 'total',
        ))
        for seguro in seguros:
            seguro.save(update_fields=('dias_cobrados', 'subtotal'))
        for producto in productos:
            producto.save(update_fields=('dias_cobrados', 'subtotal'))
        orden.subtotal = subtotal
        orden.total = total
        orden.save(update_fields=('subtotal', 'total'))
        OrdenDetalle.objects.filter(orden=orden).delete()
        OrdenDetalle.objects.create(
            orden=orden,
            tipo_item='ARRIENDO',
            descripcion=f'Arriendo {instance.modelo.marca} {instance.modelo.nombre_modelo} por {dias} día(s)',
            cantidad=dias,
            precio_unitario=tarifa.precio_diario,
            subtotal=base_total,
        )
        for seguro in seguros:
            OrdenDetalle.objects.create(
                orden=orden,
                tipo_item='SEGURO',
                descripcion=seguro.nombre_snapshot,
                cantidad=dias,
                precio_unitario=seguro.precio_diario_snapshot,
                subtotal=seguro.subtotal,
            )
        for producto in productos:
            OrdenDetalle.objects.create(
                orden=orden,
                tipo_item='PRODUCTO',
                descripcion=producto.nombre_snapshot,
                cantidad=producto.cantidad * dias,
                precio_unitario=producto.precio_unitario_snapshot,
                subtotal=producto.subtotal,
            )

        request = self.context['request']
        version = ContratoVersion.objects.filter(
            activa=True,
        ).order_by('-vigente_desde').first()
        if version is None:
            raise serializers.ValidationError(
                'No hay una versión vigente del contrato para registrar la aceptación.'
            )
        Contrato.objects.create(
            reserva=instance,
            contrato_version=version,
            aceptado=accepted,
            fecha_aceptacion=timezone.now(),
            ip_cliente=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            medio_aceptacion='SUCURSAL',
            trabajador_testigo=request.user,
        )
        HistorialEstadoReserva.objects.create(
            reserva=instance,
            estado_anterior=anterior,
            estado_nuevo=instance.estado,
            actor_tipo='TRABAJADOR',
            trabajador=request.user,
            observacion='Fechas modificadas y aceptadas por el cliente; se recalculó la orden pendiente.',
            fecha_cambio=timezone.now(),
        )
        return instance


def models_q_fecha(fecha):
    from django.db.models import Q
    return Q(fecha_hasta__isnull=True) | Q(fecha_hasta__gte=fecha)


class CancelacionSerializer(serializers.ModelSerializer):
    codigo_reserva = serializers.CharField(write_only=True, required=False)
    numero_cuenta = serializers.CharField(write_only=True, required=False)
    codigo = serializers.CharField(source='reserva.codigo', read_only=True)
    monto_pagado = serializers.SerializerMethodField()
    monto_retenido = serializers.SerializerMethodField()
    codigo_comprobante = serializers.SerializerMethodField()
    comprobante_disponible = serializers.SerializerMethodField()

    class Meta:
        model = Cancelacion
        fields = (
            'id', 'reserva', 'codigo_reserva', 'codigo', 'motivo',
            'banco_destino', 'tipo_cuenta', 'numero_cuenta',
            'tipo_documento_titular', 'rut_titular', 'nombre_titular',
            'monto_pagado', 'monto_retenido', 'monto_solicitado', 'estado',
            'fecha_solicitud', 'fecha_revision', 'motivo_rechazo',
            'codigo_comprobante', 'comprobante_disponible',
        )
        read_only_fields = (
            'id', 'estado', 'fecha_solicitud', 'fecha_revision',
            'motivo_rechazo', 'monto_solicitado',
        )

    def validate_numero_cuenta(self, value):
        if not value.isalnum():
            raise serializers.ValidationError('Revisa el número de cuenta.')
        return value

    def validate(self, attrs):
        reserva = attrs.get('reserva')
        if reserva is None:
            return attrs
        required = (
            'banco_destino', 'tipo_cuenta', 'numero_cuenta',
            'tipo_documento_titular', 'rut_titular', 'nombre_titular',
        )
        missing = [field for field in required if not str(attrs.get(field) or '').strip()]
        if missing:
            raise serializers.ValidationError({
                field: 'Este dato es obligatorio para solicitar la devolución.'
                for field in missing
            })
        tipo_documento = attrs['tipo_documento_titular']
        numero_documento = str(attrs['rut_titular']).strip()
        if tipo_documento == 'RUT' and not rut_valido(numero_documento):
            raise serializers.ValidationError({'rut_titular': 'Ingresa un RUT válido.'})
        if tipo_documento == 'PASAPORTE' and (
            len(numero_documento) < 3
            or len(numero_documento) > 30
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]*', numero_documento)
        ):
            raise serializers.ValidationError({
                'rut_titular': 'Ingresa un número de pasaporte válido.'
            })
        attrs['rut_titular'] = numero_documento
        return attrs

    def create(self, validated_data):
        numero_cuenta = validated_data.pop('numero_cuenta', None)
        cifrado = None
        if numero_cuenta:
            encryption_key = settings.BANK_DATA_ENCRYPTION_KEY
            if not encryption_key:
                raise serializers.ValidationError(
                    'Las solicitudes con devolución requieren configurar BANK_DATA_ENCRYPTION_KEY.'
                )
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT pgp_sym_encrypt(%s, %s)',
                    [numero_cuenta, encryption_key],
                )
                cifrado = cursor.fetchone()[0]
        return Cancelacion.objects.create(
            numero_cuenta_cifrado=cifrado,
            **validated_data,
        )

    def get_monto_pagado(self, obj):
        return str(obj.reserva.total)

    def get_monto_retenido(self, obj):
        if obj.monto_solicitado is None:
            return None
        monto_pagado = obj.reserva.total
        return str(monto_pagado - obj.monto_solicitado)

    def get_codigo_comprobante(self, obj):
        reembolso = obj.reembolso_set.order_by('-id').first()
        return reembolso.numero_transaccion_externa if reembolso else None

    def get_comprobante_disponible(self, obj):
        reembolso = obj.reembolso_set.order_by('-id').first()
        return bool(reembolso and reembolso.comprobante_url)

