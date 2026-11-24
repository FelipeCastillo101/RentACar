from types import SimpleNamespace

from django.test import SimpleTestCase

from bookings.views import ReservaViewSet
from core.permissions import EsAdmin, EsStaff
from fleet.serializers import nombre_categoria_visible
from fleet.views import ProductoViewSet, VehiculoViewSet
from users.views import ClienteViewSet


class PermisosPorRolTests(SimpleTestCase):
    def permiso_view(self, view_class, action):
        view = view_class()
        view.action = action
        return view, view.get_permissions()[0]

    def test_asistente_puede_operar_reservas_pero_no_editar_catalogos(self):
        asistente = SimpleNamespace(is_authenticated=True, rol='asistente')
        request = SimpleNamespace(user=asistente)
        reserva, permiso_reserva = self.permiso_view(ReservaViewSet, 'partial_update')
        vehiculo, permiso_vehiculo = self.permiso_view(VehiculoViewSet, 'estado')
        producto, permiso_producto = self.permiso_view(ProductoViewSet, 'partial_update')
        cliente, permiso_cliente = self.permiso_view(ClienteViewSet, 'partial_update')

        self.assertIsInstance(permiso_reserva, EsStaff)
        self.assertTrue(permiso_reserva.has_permission(request, reserva))
        for view, permiso in (
            (vehiculo, permiso_vehiculo),
            (producto, permiso_producto),
            (cliente, permiso_cliente),
        ):
            self.assertIsInstance(permiso, EsAdmin)
            self.assertFalse(permiso.has_permission(request, view))

    def test_admin_puede_editar_flota_productos_y_clientes(self):
        admin = SimpleNamespace(is_authenticated=True, rol='admin')
        request = SimpleNamespace(user=admin)
        for view_class, action in (
            (VehiculoViewSet, 'state'),
            (ProductoViewSet, 'partial_update'),
            (ClienteViewSet, 'partial_update'),
        ):
            view, permiso = self.permiso_view(view_class, action)
            self.assertTrue(permiso.has_permission(request, view))


class NombreCategoriaVisibleTests(SimpleTestCase):
    def test_normaliza_economico_duplicado_y_texto_mojibake(self):
        self.assertEqual(nombre_categoria_visible('Economico'), 'Económico')
        self.assertEqual(nombre_categoria_visible('EconÃ³mico'), 'Económico')
        self.assertEqual(nombre_categoria_visible('Sedan'), 'Sedán')
