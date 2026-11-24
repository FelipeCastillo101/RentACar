import { Link, useLocation } from 'react-router-dom'

const pesos = (valor) => new Intl.NumberFormat('es-CL', {
  style: 'currency',
  currency: 'CLP',
  maximumFractionDigits: 0,
}).format(Number(valor) || 0)

const fechaHora = (valor) => {
  if (!valor) return 'No informada'
  const fecha = new Date(valor)
  return Number.isNaN(fecha.getTime())
    ? valor
    : new Intl.DateTimeFormat('es-CL', { dateStyle: 'medium', timeStyle: 'short' }).format(fecha)
}

function ResultadoReserva() {
  const { state } = useLocation()
  const reserva = state?.reserva
  const auto = state?.auto

  if (!reserva) {
    return (
      <main className="page result-page">
        <section className="result-card">
          <p className="eyebrow">SOLICITUD DE RESERVA</p>
          <h1>No encontramos una reserva para mostrar.</h1>
          <Link className="button button-dark" to="/flota">Volver a vehículos <span aria-hidden="true">→</span></Link>
        </section>
      </main>
    )
  }

  const codigo = reserva.codigo || `#${reserva.id}`
  const nombreAuto = auto
    ? `${auto.marca || ''} ${auto.nombre_modelo || auto.modelo || ''}`.trim()
    : `${reserva.modelo?.marca || ''} ${reserva.modelo?.nombre_modelo || ''}`.trim()

  return (
    <main className="page result-page">
      <section className="result-card result-pending">
        <div className="result-symbol">✓</div>
        <p className="eyebrow">RESERVA GENERADA</p>
        <h1>Registramos tu solicitud.</h1>
        <p>Tu código de reserva es <strong>{codigo}</strong>.</p>
      </section>

      <section className="card reservation-confirmation">
        <div className="confirmed-heading">
          <div>
            <p className="eyebrow">DETALLE DE TU SOLICITUD</p>
            <h2>{nombreAuto || 'Vehículo seleccionado'}</h2>
          </div>
          <span className="confirmed-badge">Pendiente</span>
        </div>
        <div className="confirmed-grid">
          <div><span>Código de reserva</span><strong>{codigo}</strong></div>
          <div><span>Estado</span><strong>Pendiente de pago</strong></div>
          <div><span>Retiro</span><strong>{fechaHora(reserva.fecha_hora_retiro)}</strong></div>
          <div><span>Devolución</span><strong>{fechaHora(reserva.fecha_hora_devolucion)}</strong></div>
          <div><span>Total estimado</span><strong>{pesos(reserva.total || reserva.subtotal)}</strong></div>
        </div>
        <p className="pickup-reminder">
          La solicitud quedó guardada, pero todavía no confirma el arriendo ni registra un pago.
          Las reservas pendientes expiran a los 15 minutos si no se completa un pago.
        </p>
        <div className="result-actions">
          <Link className="button button-dark" to="/">Volver al inicio <span aria-hidden="true">→</span></Link>
          <Link className="button button-outline" to="/flota">Ver otros vehículos <span aria-hidden="true">→</span></Link>
        </div>
      </section>
    </main>
  )
}

export default ResultadoReserva
