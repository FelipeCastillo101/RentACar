from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from bookings.views import CancelacionViewSet, ReservaViewSet
from fleet.views import (
    CategoriaViewSet,
    ModeloViewSet,
    ProductoViewSet,
    SeguroViewSet,
    SucursalViewSet,
    VehiculoViewSet,
)
from users.views import (
    ClienteViewSet,
    cerrar_sesion,
    iniciar_sesion,
    iniciar_sesion_google,
    registro_cliente,
    yo,
    verificar_codigo_trabajador,
)
from payments.views import (
    PagoViewSet,
    cancelar_pago_transbank,
    crear_pago_transbank,
    confirmar_pago_transbank,
    descargar_comprobante,
    retorno_webpay,
)


# El Router crea automáticamente todas las rutas necesarias (listar y buscar por ID)
router = DefaultRouter()
router.register(r'categorias', CategoriaViewSet)
router.register(r'modelos', ModeloViewSet, basename='modelos')
router.register(r'vehiculos', VehiculoViewSet)
router.register(r'productos', ProductoViewSet)
router.register(r'seguros', SeguroViewSet)
router.register(r'sucursales', SucursalViewSet)
router.register(r'reservas', ReservaViewSet, basename='reservas')
router.register(r'cancelaciones', CancelacionViewSet, basename='cancelaciones')
router.register(r'clientes', ClienteViewSet, basename='clientes')
router.register(r'pagos', PagoViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Aquí exponemos nuestra API bajo el prefijo /api/
    path('api/', include(router.urls)),
    path('api/crear-pago/', crear_pago_transbank, name='crear_pago_transbank'),
    path('api/confirmar-pago/', confirmar_pago_transbank, name='confirmar_pago_transbank'),
    path('api/cancelar-pago/', cancelar_pago_transbank, name='cancelar_pago_transbank'),
    path('api/webpay/retorno/', retorno_webpay, name='webpay_return'),
    path('api/reservas/<int:reserva_id>/comprobante/', descargar_comprobante, name='descargar_comprobante'),
    # Sesiones (token firmado): clientes y trabajadores
    path('api/auth/registro-cliente/', registro_cliente, name='api_registro_cliente'),
    path('api/auth/login/', iniciar_sesion, name='api_login'),
    path('api/auth/verify-code/', verificar_codigo_trabajador, name='api_verify_staff_code'),
    path('api/auth/google/', iniciar_sesion_google, name='api_auth_google'),
    path('api/auth/logout/', cerrar_sesion, name='api_logout'),
    path('api/auth/me/', yo, name='api_me'),
]
