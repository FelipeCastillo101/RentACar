from django.contrib import admin

from .models import Categoria, Modelo, Vehiculo, Producto, Sucursal, Trabajador

admin.site.register(Categoria)
admin.site.register(Modelo)
admin.site.register(Vehiculo)
admin.site.register(Producto)
admin.site.register(Sucursal)
admin.site.register(Trabajador)
