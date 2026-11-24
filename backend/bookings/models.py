from django.db import models

from fleet.models import Modelo, Sucursal, Vehiculo
from users.models import Cliente


class Reserva(models.Model):
    ESTADOS = (
        ('PENDIENTE_PAGO', 'Pendiente de pago'),
        ('CONFIRMADA', 'Confirmada'),
        ('EN_CURSO', 'En curso'),
        ('CANCELACION_EN_PROCESO', 'Cancelación en proceso'),
        ('COMPLETADA', 'Completada'),
        ('CANCELADA', 'Cancelada'),
        ('EXPIRADA', 'Expirada'),
    )
    CANALES = (('WEB', 'Web'), ('SUCURSAL', 'Sucursal'))

    codigo = models.CharField(max_length=40, unique=True)
    cliente = models.ForeignKey(Cliente, models.DO_NOTHING, db_column='cliente_id', related_name='reservas')
    modelo = models.ForeignKey(Modelo, models.DO_NOTHING, db_column='modelo_id', related_name='reservas')
    vehiculo = models.ForeignKey(Vehiculo, models.DO_NOTHING, db_column='vehiculo_id', related_name='reservas')
    sucursal_retiro = models.ForeignKey(
        Sucursal, models.DO_NOTHING, db_column='sucursal_retiro_id', related_name='reservas_retiro'
    )
    sucursal_devolucion = models.ForeignKey(
        Sucursal, models.DO_NOTHING, db_column='sucursal_devolucion_id',
        related_name='reservas_devolucion'
    )
    fecha_hora_retiro = models.DateTimeField()
    fecha_hora_devolucion = models.DateTimeField()
    canal = models.CharField(max_length=20, choices=CANALES)
    estado = models.CharField(max_length=30, choices=ESTADOS, default='PENDIENTE_PAGO')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fecha_creacion = models.DateTimeField()
    creado_por_trabajador = models.ForeignKey(
        'fleet.Trabajador', models.DO_NOTHING, db_column='creado_por_trabajador_id',
        blank=True, null=True, related_name='reservas_creadas'
    )
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'reserva'

    @property
    def monto_total(self):
        return self.total

    @property
    def monto_garantia(self):
        return self.modelo.categoria.monto_garantia

    def __str__(self):
        return f'{self.codigo} ({self.estado})'


class ReservaSeguro(models.Model):
    reserva = models.ForeignKey(
        Reserva, models.DO_NOTHING, db_column='reserva_id', related_name='seguros_reservados'
    )
    seguro_id = models.BigIntegerField()
    nombre_snapshot = models.CharField(max_length=100)
    precio_diario_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    deducible_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    dias_cobrados = models.SmallIntegerField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'reserva_seguro'


class ReservaProducto(models.Model):
    reserva = models.ForeignKey(
        Reserva, models.DO_NOTHING, db_column='reserva_id', related_name='detalles'
    )
    producto_id = models.BigIntegerField()
    nombre_snapshot = models.CharField(max_length=100)
    cantidad = models.SmallIntegerField(default=1)
    precio_unitario_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    dias_cobrados = models.SmallIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'reserva_producto'


class HistorialEstadoReserva(models.Model):
    reserva = models.ForeignKey(Reserva, models.DO_NOTHING, db_column='reserva_id')
    estado_anterior = models.CharField(max_length=30, blank=True, null=True)
    estado_nuevo = models.CharField(max_length=30)
    actor_tipo = models.CharField(max_length=15, default='SISTEMA')
    trabajador = models.ForeignKey(
        'fleet.Trabajador', models.DO_NOTHING, db_column='trabajador_id', blank=True, null=True
    )
    observacion = models.TextField(blank=True, null=True)
    fecha_cambio = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'historial_estado_reserva'


class ContratoVersion(models.Model):
    nombre = models.CharField(max_length=100)
    numero_version = models.CharField(max_length=30, unique=True)
    archivo_plantilla = models.CharField(max_length=500)
    vigente_desde = models.DateTimeField()
    vigente_hasta = models.DateTimeField(blank=True, null=True)
    activa = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'contrato_version'


class Contrato(models.Model):
    reserva = models.ForeignKey(Reserva, models.DO_NOTHING, db_column='reserva_id')
    contrato_version = models.ForeignKey(
        ContratoVersion, models.DO_NOTHING, db_column='contrato_version_id'
    )
    archivo_generado = models.CharField(max_length=500, blank=True, null=True)
    hash_documento = models.CharField(max_length=128, blank=True, null=True)
    aceptado = models.BooleanField(default=False)
    fecha_aceptacion = models.DateTimeField(blank=True, null=True)
    ip_cliente = models.CharField(max_length=45, blank=True, null=True)
    user_agent = models.CharField(max_length=500, blank=True, null=True)
    medio_aceptacion = models.CharField(max_length=20)
    trabajador_testigo = models.ForeignKey(
        'fleet.Trabajador', models.DO_NOTHING, db_column='trabajador_testigo_id',
        blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = 'contrato'


class Cancelacion(models.Model):
    ESTADOS_TICKET = (
        ('PENDIENTE', 'Pendiente'),
        ('EN_REVISION', 'En revisión'),
        ('RECHAZADA', 'Rechazada'),
        ('APROBADA', 'Aprobada'),
        ('DERIVADA_FINANZAS', 'Derivada a Finanzas'),
        ('REEMBOLSO_REGISTRADO', 'Reembolso registrado'),
        ('CERRADA', 'Cerrada'),
    )

    reserva = models.ForeignKey(Reserva, models.DO_NOTHING, db_column='reserva_id', related_name='cancelaciones')
    motivo = models.TextField()
    banco_destino = models.CharField(max_length=100, blank=True, null=True)
    tipo_cuenta = models.CharField(max_length=60, blank=True, null=True)
    numero_cuenta_cifrado = models.BinaryField(blank=True, null=True)
    tipo_documento_titular = models.CharField(
        max_length=20,
        choices=(('RUT', 'RUT'), ('PASAPORTE', 'Pasaporte')),
        blank=True,
        null=True,
    )
    rut_titular = models.CharField(max_length=30, blank=True, null=True)
    nombre_titular = models.CharField(max_length=120, blank=True, null=True)
    monto_solicitado = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    estado = models.CharField(max_length=30, choices=ESTADOS_TICKET, default='PENDIENTE')
    fecha_solicitud = models.DateTimeField()
    fecha_revision = models.DateTimeField(blank=True, null=True)
    motivo_rechazo = models.TextField(blank=True, null=True)
    trabajador_revisor = models.ForeignKey(
        'fleet.Trabajador', models.DO_NOTHING, db_column='trabajador_revisor_id',
        blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = 'solicitud_cancelacion'


class Reembolso(models.Model):
    solicitud_cancelacion = models.ForeignKey(
        Cancelacion, models.DO_NOTHING, db_column='solicitud_cancelacion_id'
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=25, default='PENDIENTE')
    departamento_externo = models.CharField(max_length=100, blank=True, null=True)
    numero_transaccion_externa = models.CharField(max_length=150, blank=True, null=True)
    fecha_reembolso = models.DateTimeField(blank=True, null=True)
    comprobante_url = models.CharField(max_length=500, blank=True, null=True)
    ingresado_por_trabajador = models.ForeignKey(
        'fleet.Trabajador', models.DO_NOTHING, db_column='ingresado_por_trabajador_id',
        blank=True, null=True
    )
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'reembolso'
