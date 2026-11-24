from django.db import models


class Sucursal(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=180)
    region = models.CharField(max_length=100)
    comuna = models.CharField(max_length=100)
    telefono = models.CharField(max_length=25, blank=True, null=True)
    correo = models.CharField(max_length=120, blank=True, null=True)
    activa = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'sucursal'

    def __str__(self):
        return self.nombre


class Rol(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=60)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'rol'

    def __str__(self):
        return self.nombre


class Permiso(models.Model):
    codigo = models.CharField(max_length=80, unique=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    roles = models.ManyToManyField(Rol, through='RolPermiso', related_name='permisos')

    class Meta:
        managed = False
        db_table = 'permiso'


class RolPermiso(models.Model):
    rol = models.ForeignKey(Rol, models.DO_NOTHING, db_column='rol_id', primary_key=True)
    permiso = models.ForeignKey(Permiso, models.DO_NOTHING, db_column='permiso_id')

    class Meta:
        managed = False
        db_table = 'rol_permiso'
        unique_together = (('rol', 'permiso'),)


class Trabajador(models.Model):
    rut = models.CharField(max_length=12, unique=True)
    correo = models.CharField(max_length=150, unique=True)
    nombre = models.CharField(max_length=70)
    apellido = models.CharField(max_length=70)
    password_hash = models.CharField(max_length=255)
    activo = models.BooleanField(default=True)
    roles = models.ManyToManyField(Rol, through='TrabajadorRol', related_name='trabajadores')
    sucursales = models.ManyToManyField(
        Sucursal, through='TrabajadorSucursal', related_name='trabajadores'
    )

    class Meta:
        managed = False
        db_table = 'trabajador'

    @property
    def rol(self):
        codigo = self.roles.order_by('id').values_list('codigo', flat=True).first()
        return codigo.lower() if codigo else ''

    @property
    def sucursal(self):
        return self.sucursales.order_by('-trabajadorsucursal__es_principal', 'id').first()

    @property
    def sucursal_id(self):
        sucursal = self.sucursal
        return sucursal.id if sucursal else None

    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        return f'{self.nombre} {self.apellido}'


class TrabajadorRol(models.Model):
    trabajador = models.ForeignKey(
        Trabajador, models.DO_NOTHING, db_column='trabajador_id', primary_key=True
    )
    rol = models.ForeignKey(Rol, models.DO_NOTHING, db_column='rol_id')

    class Meta:
        managed = False
        db_table = 'trabajador_rol'
        unique_together = (('trabajador', 'rol'),)


class TrabajadorSucursal(models.Model):
    trabajador = models.ForeignKey(
        Trabajador, models.DO_NOTHING, db_column='trabajador_id', primary_key=True
    )
    sucursal = models.ForeignKey(Sucursal, models.DO_NOTHING, db_column='sucursal_id')
    es_principal = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'trabajador_sucursal'
        unique_together = (('trabajador', 'sucursal'),)


class Categoria(models.Model):
    nombre = models.CharField(unique=True, max_length=60)
    descripcion = models.TextField(blank=True, null=True)
    monto_garantia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    activa = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'categoria'

    def __str__(self):
        return self.nombre


class Modelo(models.Model):
    marca = models.CharField(max_length=60)
    nombre_modelo = models.CharField(max_length=70)
    transmision = models.CharField(max_length=30)
    combustible = models.CharField(max_length=30)
    pasajeros = models.SmallIntegerField()
    puertas = models.SmallIntegerField(blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    imagen_principal = models.CharField(max_length=500, blank=True, null=True)
    categoria = models.ForeignKey(Categoria, models.DO_NOTHING, db_column='categoria_id')
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'modelo'

    def __str__(self):
        return f'{self.marca} {self.nombre_modelo}'


class Tarifa(models.Model):
    modelo = models.ForeignKey(Modelo, models.DO_NOTHING, db_column='modelo_id')
    precio_diario = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField(blank=True, null=True)
    activa = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'tarifa'


class Vehiculo(models.Model):
    ESTADOS = (
        ('ACTIVO', 'Disponible'),
        ('EN_ARRENDAMIENTO', 'En arriendo'),
        ('LIMPIEZA', 'Limpieza'),
        ('MANTENCION', 'Mantención'),
        ('FUERA_SERVICIO', 'Fuera de servicio'),
        ('BAJA', 'Baja'),
    )

    patente = models.CharField(unique=True, max_length=10)
    anio = models.SmallIntegerField()
    color = models.CharField(max_length=40, blank=True, null=True)
    kilometraje_actual = models.IntegerField(default=0)
    estado_operativo = models.CharField(max_length=25, choices=ESTADOS, default='ACTIVO')
    modelo = models.ForeignKey(Modelo, models.DO_NOTHING, db_column='modelo_id')
    sucursal_actual = models.ForeignKey(Sucursal, models.DO_NOTHING, db_column='sucursal_actual_id')
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'vehiculo'

    def __str__(self):
        return self.patente


class Seguro(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    precio_diario = models.DecimalField(max_digits=12, decimal_places=2)
    deducible_monto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'seguro'


class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50)
    descripcion = models.TextField(blank=True, null=True)
    precio_diario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'producto'
