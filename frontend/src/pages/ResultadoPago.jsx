import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../api'

function ResultadoPago() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token_ws')
  const tokenCancelado = searchParams.get('TBK_TOKEN')
  const ordenCancelada = searchParams.get('TBK_ORDEN_COMPRA')
  const [mensaje, setMensaje] = useState(
    () => token || tokenCancelado || ordenCancelada
      ? 'Validando pago…'
      : 'La dirección no contiene un pago en proceso.',
  )
  const [reserva, setReserva] = useState(null)
  const [aviso, setAviso] = useState('')
  const [errorDescarga, setErrorDescarga] = useState('')
  const confirmacionIniciada = useRef(false)

  useEffect(() => {
    if (!token && !tokenCancelado && !ordenCancelada) {
      return
    }
    if (confirmacionIniciada.current) return
    confirmacionIniciada.current = true
    const paymentAccessToken = sessionStorage.getItem('rentcar-payment-access')
    const datosAcceso = paymentAccessToken
      ? { payment_access_token: paymentAccessToken }
      : {}

    if (tokenCancelado || (!token && ordenCancelada)) {
      api.post('/api/cancelar-pago/', {
        ...(tokenCancelado ? { token_ws: tokenCancelado } : {}),
        ...(ordenCancelada ? { buy_order: ordenCancelada } : {}),
        ...datosAcceso,
      })
        .then(() => setMensaje('El pago fue cancelado. La reserva pendiente se liberó.'))
        .catch((error) => {
          setMensaje(error.response?.data?.detail || 'No se pudo actualizar el resultado del pago cancelado.')
        })
      return
    }

    api.post('/api/confirmar-pago/', {
      token_ws: token,
      ...datosAcceso,
    })
      .then((response) => {
        if (response.data.status === 'aprobado') {
          setReserva(response.data.reserva)
          setAviso(response.data.aviso || '')
          setMensaje('Pago aprobado. Tu reserva está confirmada.')
        } else {
          setMensaje('El pago fue rechazado o cancelado. No se confirmó la reserva.')
        }
      })
      .catch((error) => {
        setMensaje(error.response?.data?.detail || 'No se pudo confirmar el pago. Contacta con la sucursal antes de volver a pagar.')
      })
  }, [token, tokenCancelado, ordenCancelada])

  const descargarComprobante = async () => {
    setErrorDescarga('')
    try {
      const response = await api.get(
        `/api/reservas/${reserva.codigo_reserva}/comprobante/`,
        {
          responseType: 'blob',
          params: {
            payment_access_token: sessionStorage.getItem('rentcar-payment-access'),
          },
        },
      )
      const url = URL.createObjectURL(response.data)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = `comprobante-reserva-${reserva.codigo}.pdf`
      enlace.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setErrorDescarga(error.response?.data?.detail || 'No se pudo descargar el comprobante.')
    }
  }

  return (
    <main className="payment-result section-wrap">
      <section className={`result-card ${reserva ? 'result-success' : tokenCancelado || ordenCancelada ? 'result-cancelled' : 'result-pending'}`}>
        <div className={`result-symbol ${reserva ? '' : 'result-symbol-pending'}`}>
          {reserva ? '✓' : '…'}
        </div>
        <p className="eyebrow">RESULTADO DE WEBPAY</p>
        <h1>{reserva ? '¡Tu reserva está confirmada!' : 'Estamos verificando tu pago.'}</h1>
        <p role="status">{mensaje}</p>
        {aviso && <p role="alert" className="form-error">{aviso}</p>}
      </section>
      {reserva && (
        <section className="confirmed-reservation">
          <div className="confirmed-heading">
            <div>
              <p className="eyebrow">COMPROBANTE DE RESERVA</p>
              <h2>Reserva {reserva.codigo}</h2>
            </div>
            <span className="confirmed-badge">Pagada</span>
          </div>
          <div className="confirmed-grid">
            <div><span>Cliente</span><strong>{reserva.cliente.nombre}</strong></div>
            <div><span>Vehículo</span><strong>{reserva.vehiculo}</strong></div>
            <div><span>Categoría</span><strong>{reserva.categoria}</strong></div>
            <div><span>Patente</span><strong>{reserva.patente}</strong></div>
            <div><span>Retiro</span><strong>{reserva.fecha_hora_retiro}</strong></div>
            <div><span>Devolución</span><strong>{reserva.fecha_hora_devolucion}</strong></div>
            <div><span>Sucursal</span><strong>{reserva.sucursal_retiro}</strong></div>
            <div><span>Total pagado</span><strong>${reserva.total_pagado}</strong></div>
            <div><span>Garantía en sucursal</span><strong>${reserva.garantia_monto}</strong></div>
          </div>
          <p className="pickup-reminder">
            La boleta o factura tributaria se emite según la configuración del proveedor. El comprobante de reserva no reemplaza ese documento.
          </p>
          {errorDescarga && <p role="alert" className="form-error">{errorDescarga}</p>}
          <div className="result-actions">
            <button type="button" className="button button-primary" onClick={descargarComprobante}>
              Descargar comprobante
            </button>
            <Link className="button button-dark" to="/">Volver al inicio <span aria-hidden="true">→</span></Link>
          </div>
        </section>
      )}
      {!reserva && (
        <div className="result-actions">
          <Link className="button button-outline" to="/">Volver al inicio <span aria-hidden="true">→</span></Link>
        </div>
      )}
    </main>
  )
}

export default ResultadoPago
