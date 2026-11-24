from django.db import models


class Cliente(models.Model):
    nombre = models.CharField(max_length=70)
    apellido = models.CharField(max_length=70)
    correo = models.CharField(max_length=150, unique=True)
    telefono = models.CharField(max_length=25, blank=True, null=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    fecha_registro = models.DateTimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'cliente'

    @property
    def is_authenticated(self):
        return True

    @property
    def numero_documento(self):
        return self.documentos.filter(es_principal=True).values_list(
            'numero_documento', flat=True
        ).first()

    @property
    def tipo_documento(self):
        return self.documentos.filter(es_principal=True).values_list(
            'tipo_documento', flat=True
        ).first()

    @property
    def licencia(self):
        return self.licencias.order_by('-id').values_list('numero_licencia', flat=True).first()

    @property
    def licencia_vencimiento(self):
        return self.licencias.order_by('-id').values_list('fecha_vencimiento', flat=True).first()


class CuentaCliente(models.Model):
    cliente = models.ForeignKey(Cliente, models.DO_NOTHING, db_column='cliente_id', related_name='cuentas')
    proveedor = models.CharField(max_length=30)
    proveedor_usuario_id = models.CharField(max_length=191)
    correo_proveedor = models.CharField(max_length=150)
    vinculada_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'cuenta_cliente'
        unique_together = (('proveedor', 'proveedor_usuario_id'),)


class DocumentoCliente(models.Model):
    TIPOS = (('RUT', 'RUT'), ('PASAPORTE', 'Pasaporte'), ('OTRO', 'Otro'))

    cliente = models.ForeignKey(
        Cliente, models.DO_NOTHING, db_column='cliente_id', related_name='documentos'
    )
    tipo_documento = models.CharField(max_length=20, choices=TIPOS)
    numero_documento = models.CharField(max_length=30)
    pais_emision = models.CharField(max_length=80, default='CHILE')
    es_principal = models.BooleanField(default=False)
    archivo_respaldo = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'documento_cliente'


class LicenciaConducir(models.Model):
    cliente = models.ForeignKey(
        Cliente, models.DO_NOTHING, db_column='cliente_id', related_name='licencias'
    )
    numero_licencia = models.CharField(max_length=50)
    pais_emision = models.CharField(max_length=80, default='Chile')
    clase_licencia = models.CharField(max_length=30, blank=True, null=True)
    fecha_emision = models.DateField(blank=True, null=True)
    fecha_vencimiento = models.DateField()
    archivo_respaldo = models.CharField(max_length=500, blank=True, null=True)
    verificada = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'licencia_conducir'
