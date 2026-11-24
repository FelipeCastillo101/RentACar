"""Permisos por rol: admin > asistente > cliente.

- admin:     gestión de datos maestros y operación completa.
- asistente: reservas, pagos presenciales, cancelaciones y estados operacionales.
-            No modifica vehículos, clientes ni productos directamente.
- cliente:   sus propios datos y reservas.
"""
from rest_framework.permissions import BasePermission


def es_trabajador(usuario):
    return bool(usuario and usuario.is_authenticated and hasattr(usuario, 'rol'))


def es_admin(usuario):
    return es_trabajador(usuario) and usuario.rol == 'admin'


def es_staff(usuario):
    """Admin o asistente: los roles que operan el sistema."""
    return es_trabajador(usuario) and usuario.rol in ('admin', 'asistente')


class EsTrabajador(BasePermission):
    message = 'Se requiere una cuenta de trabajador (admin o asistente).'

    def has_permission(self, request, view):
        return es_trabajador(request.user)


class EsStaff(BasePermission):
    message = 'Se requiere perfil de admin o asistente.'

    def has_permission(self, request, view):
        return es_staff(request.user)


class EsAdmin(BasePermission):
    message = 'Se requiere perfil de administrador.'

    def has_permission(self, request, view):
        return es_admin(request.user)


class EsCliente(BasePermission):
    message = 'Se requiere una cuenta de cliente.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and not hasattr(request.user, 'rol')
        )
