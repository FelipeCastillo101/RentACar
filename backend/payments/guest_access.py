from django.core import signing


_GUEST_PAYMENT_SALT = 'rentcar.guest-payment'


def crear_token_pago_invitado(reserva_id):
    return signing.dumps(
        {'reserva_id': int(reserva_id)},
        salt=_GUEST_PAYMENT_SALT,
        compress=True,
    )


def validar_token_pago_invitado(token, reserva_id):
    if not token:
        return False
    try:
        datos = signing.loads(token, salt=_GUEST_PAYMENT_SALT, max_age=24 * 60 * 60)
    except signing.BadSignature:
        return False
    return isinstance(datos, dict) and datos.get('reserva_id') == int(reserva_id)
