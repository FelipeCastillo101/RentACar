import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

const contenidos = {
  b2b: {
    titulo: 'Reservas para empresas',
    intro: 'Coordina una flota para tu empresa con atención personalizada.',
    campos: ['Empresa', 'RUT empresa', 'Persona de contacto', 'Correo corporativo', 'Teléfono', 'Cantidad de vehículos', 'Mensaje'],
    confirmacion: 'Recibimos tu solicitud. Un asistente se pondrá en contacto para validar los datos y derivarla a un moderador.'
  },
  cancelacion: {
    titulo: 'Cancelación y devolución',
    intro: 'Envía una solicitud para que el equipo revise tu reserva manualmente.',
    campos: ['Código de reserva', 'RUT o pasaporte', 'Correo', 'Motivo de la solicitud', 'Detalle'],
    confirmacion: 'Recibimos tu solicitud. La cancelación o devolución quedará pendiente de revisión y confirmación manual.'
  },
  privacidad: { titulo: 'Política y privacidad', intro: 'Protegemos los datos entregados durante la cotización, reserva y atención.', texto: 'Solo solicitamos información necesaria para identificar al arrendatario, gestionar la reserva, procesar el pago y responder solicitudes. No ingreses fotografías de documentos ni datos de tarjetas en formularios web.' },
}

function Informacion() {
  const { tipo } = useParams()
  const contenido = contenidos[tipo]
  const [enviado, setEnviado] = useState(false)

  if (tipo === 'quienes') {
    return (
      <main className="information-page">
        <section className="information-hero">
          <p className="eyebrow">QUIÉNES SOMOS</p>
          <h1>Tu próximo viaje comienza aquí.</h1>
          <p>
            En Rentacar hacemos que encontrar y reservar un vehículo sea simple.
            Queremos que cada persona pueda planificar su viaje con información
            clara, elegir lo que necesita y comenzar con confianza.
          </p>
        </section>
        <section className="about-story">
          <p className="eyebrow">NUESTRA FORMA DE TRABAJAR</p>
          <h2>Arriendos claros, viajes tranquilos.</h2>
          <p>
            Reunimos la búsqueda del vehículo, los detalles de la reserva y el
            pago en un mismo lugar. Nuestro equipo en Viña del Mar está para
            orientar a cada cliente antes de retirar su vehículo y durante la
            preparación de su viaje.
          </p>
        </section>
        <section className="about-values" aria-label="Nuestros compromisos">
          <article>
            <span>01</span>
            <h3>Información transparente</h3>
            <p>Mostramos las fechas, condiciones y valores antes de confirmar la reserva.</p>
          </article>
          <article>
            <span>02</span>
            <h3>Atención cercana</h3>
            <p>Buscamos que cada etapa sea fácil de entender y resolver.</p>
          </article>
          <article>
            <span>03</span>
            <h3>Viajes a tu medida</h3>
            <p>Elige el vehículo y los adicionales que mejor se ajusten a tu recorrido.</p>
          </article>
        </section>
        <Link className="button button-dark" to="/flota">Encuentra tu auto <span aria-hidden="true">→</span></Link>
      </main>
    )
  }

  if (tipo === 'sucursal') {
    const direccion = 'Av. España 656, Viña del Mar, Chile'
    const mapaUrl = `https://maps.google.com/maps?q=${encodeURIComponent(direccion)}&output=embed`
    const indicacionesUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(direccion)}`

    return (
      <main className="information-page branch-page">
        <header className="branch-heading">
          <p className="eyebrow">VISÍTANOS</p>
          <h1>Sucursal Viña del Mar</h1>
          <p>Coordinamos contigo el retiro y la devolución de tu vehículo.</p>
        </header>
        <div className="branch-layout">
          <section className="branch-details">
            <article>
              <span className="eyebrow">DIRECCIÓN</span>
              <address>{direccion}</address>
            </article>
            <article>
              <span className="eyebrow">HORARIO REFERENCIAL</span>
              <p>Lunes a sábado: 09:00–18:00</p>
              <p>Domingos y festivos: 10:00–14:00</p>
            </article>
            <article>
              <span className="eyebrow">ATENCIÓN</span>
              <p>Retiro y devolución coordinados según los datos de tu reserva.</p>
            </article>
            <a className="button button-dark" href={indicacionesUrl} target="_blank" rel="noreferrer">
              Cómo llegar con Google Maps <span aria-hidden="true">↗</span>
            </a>
          </section>
          <div className="branch-map">
            <iframe
              title="Mapa de la sucursal Rentacar en Avenida España 656, Viña del Mar"
              src={mapaUrl}
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              allowFullScreen
            />
          </div>
        </div>
      </main>
    )
  }

  if (!contenido) {
    return (
      <main className="information-page">
        <h1>Información no disponible</h1>
        <Link className="button button-dark" to="/">Volver al inicio</Link>
      </main>
    )
  }

  if (contenido.campos) {
    return (
      <main className="information-page">
        <h1>{contenido.titulo}</h1>
        <p>{contenido.intro}</p>
        {enviado ? <p role="status">{contenido.confirmacion}</p> : (
          <form className="information-form" onSubmit={(evento) => { evento.preventDefault(); setEnviado(true) }}>
            {contenido.campos.map((campo) => (
              <label key={campo}>{campo}
                {campo === 'Detalle' || campo === 'Mensaje' || campo === 'Motivo de la solicitud'
                  ? <textarea required rows="4" />
                  : <input required type={campo.includes('Correo') ? 'email' : 'text'} />}
              </label>
            ))}
            <button className="button button-dark" type="submit">Enviar solicitud</button>
          </form>
        )}
      </main>
    )
  }

  return (
    <main className="information-page">
      <p className="eyebrow">RENTA CAR</p>
      <h1>{contenido.titulo}</h1>
      <p>{contenido.intro}</p>
      <p>{contenido.texto}</p>
    </main>
  )
}

export default Informacion