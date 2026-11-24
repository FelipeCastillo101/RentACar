from django.db import models

from bookings.models import Reserva
from fleet.models import Trabajador


class OrdenCompra(models.Model):
    TIPOS_DOCUMENTO = (('BOLETA', 'Boleta'), ('FACTURA', 'Factura'))
    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('PAGADA', 'Pagada'),
        ('ANULADA', 'Anulada'),
        ('REEMBOLSO_PENDIENTE', 'Reembolso pendiente'),
        ('REEMBOLSADA', 'Reembolsada'),
    )

    codigo_orden = models.CharField(max_length=64, unique=True)
    reserva = models.OneToOneField(Reserva, models.DO_NOTHING, db_column='reserva_id')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    tipo_documento_solicitado = models.CharField(max_length=15, choices=TIPOS_DOCUMENTO, default='BOLETA')
    estado = models.CharField(max_length=25, choices=ESTADOS, default='PENDIENTE')
    fecha_creacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'orden_compra'

    @property
    def reserva_id(self):
        return self.reserva.id


class OrdenDetalle(models.Model):
    orden = models.ForeignKey(OrdenCompra, models.DO_NOTHING, db_column='orden_id', related_name='detalles')
    tipo_item = models.CharField(max_length=25)
    descripcion = models.CharField(max_length=255)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'orden_detalle'


class DatosFacturacion(models.Model):
    orden = models.OneToOneField(OrdenCompra, models.DO_NOTHING, db_column='orden_id')
    rut_receptor = models.CharField(max_length=12)
    razon_social = models.CharField(max_length=150)
    giro = models.CharField(max_length=150)
    direccion = models.CharField(max_length=180)
    comuna = models.CharField(max_length=100)
    correo = models.CharField(max_length=150)
    fecha_registro = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'datos_facturacion'


class DocumentoTributario(models.Model):
    orden = models.ForeignKey(OrdenCompra, models.DO_NOTHING, db_column='orden_id')
    tipo_dte = models.SmallIntegerField()
    folio = models.CharField(max_length=30, blank=True, null=True)
    proveedor = models.CharField(max_length=60)
    ambiente = models.CharField(max_length=15, default='CERTIFICACION')
    identificador_externo = models.CharField(max_length=150, blank=True, null=True)
    clave_idempotencia = models.CharField(max_length=100, unique=True)
    estado = models.CharField(max_length=25, default='PENDIENTE')
    monto_neto = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    monto_iva = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    codigo_respuesta = models.CharField(max_length=80, blank=True, null=True)
    mensaje_respuesta = models.TextField(blank=True, null=True)
    url_pdf = models.CharField(max_length=500, blank=True, null=True)
    url_xml = models.CharField(max_length=500, blank=True, null=True)
    fecha_solicitud = models.DateTimeField()
    fecha_emision = models.DateTimeField(blank=True, null=True)
    fecha_actualizacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'documento_tributario'


class Pago(models.Model):
    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('AUTORIZADO', 'Autorizado'),
        ('RECHAZADO', 'Rechazado'),
        ('ANULADO', 'Anulado'),
        ('REEMBOLSADO', 'Reembolsado'),
    )

    orden = models.ForeignKey(OrdenCompra, models.DO_NOTHING, db_column='orden_id', related_name='pagos')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = models.CharField(max_length=25)
    origen_pago = models.CharField(max_length=20)
    estado_pago = models.CharField(max_length=25, choices=ESTADOS)
    proveedor = models.CharField(max_length=50, blank=True, null=True)
    token_webpay = models.CharField(max_length=255, blank=True, null=True)
    buy_order = models.CharField(max_length=100, blank=True, null=True)
    session_id = models.CharField(max_length=100, blank=True, null=True)
    codigo_autorizacion = models.CharField(max_length=100, blank=True, null=True)
    codigo_transaccion_externa = models.CharField(max_length=150, blank=True, null=True)
    clave_idempotencia = models.CharField(max_length=100, unique=True, blank=True, null=True)
    fecha_creacion = models.DateTimeField()
    fecha_actualizacion = models.DateTimeField(blank=True, null=True)
    fecha_pago = models.DateTimeField(blank=True, null=True)
    registrado_por_trabajador = models.ForeignKey(
        Trabajador, models.DO_NOTHING, db_column='registrado_por_trabajador_id',
        blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = 'pago'

    @property
    def reserva(self):
        return self.orden.reserva

    @property
    def reserva_id(self):
        return self.orden.reserva_id
