import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

const fechaLocal = (desfase) => {
  const fecha = new Date()
  fecha.setDate(fecha.getDate() + desfase)
  const local = new Date(fecha.getTime() - fecha.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

const ventajas = [
  { numero: '01', titulo: 'Elige con confianza', texto: 'Información clara, fotos reales y precios transparentes para encontrar el auto ideal.' },
  { numero: '02', titulo: 'Reserva a tu ritmo', texto: 'Filtra por fecha, categoría y descubre cada detalle antes de decidir.' },
  { numero: '03', titulo: 'Listos para el camino', texto: 'Retira tu vehículo en sucursal con tu reserva y documentos a mano.' },
]

function Home() {
  const navigate = useNavigate()
  const [inicio, setInicio] = useState(() => fechaLocal(1))
  const [fin, setFin] = useState(() => fechaLocal(4))
  const [errorFechas, setErrorFechas] = useState('')

  const buscarAutos = (event) => {
    event.preventDefault()
    if (fin <= inicio) {
      setErrorFechas('La devolución debe ser posterior al retiro.')
      return
    }
    setErrorFechas('')
    navigate(`/flota?inicio=${inicio}&fin=${fin}`, {
      state: { fechaInicio: inicio, fechaFin: fin },
    })
  }

  return (
    <>
      <section className="hero-section">
        <img
          className="hero-image"
          src="https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=2200&q=85"
          alt="Vehículo listo para iniciar un viaje"
        />
        <div className="hero-shade" />
        <div className="hero-content">
          <p className="eyebrow hero-eyebrow">MÁS CAMINO. MENOS COMPLICACIONES.</p>
          <h1>Tu próxima aventura<br />empieza <em>al volante.</em></h1>
          <p className="hero-copy">Encuentra el vehículo que se adapta a tu viaje. Reserva simple, precios claros y libertad para llegar más lejos.</p>
          <Link className="button button-light" to="/flota">Explorar vehículos <span aria-hidden="true">→</span></Link>
        </div>
        <div className="hero-index"><span>01</span><i /> RENT A CAR · CHILE</div>
      </section>

      <section className="booking-search home-search" aria-labelledby="home-search-title">
        <div className="search-intro">
          <span className="search-icon" aria-hidden="true">↗</span>
          <div>
            <p className="eyebrow">EMPIEZA AQUÍ</p>
            <h2 id="home-search-title">Encuentra tu próximo auto</h2>
          </div>
        </div>
        <form className="search-form" onSubmit={buscarAutos}>
          <label className="field">
            <span>Retiro</span>
            <input type="date" min={fechaLocal(0)} value={inicio} onChange={(event) => setInicio(event.target.value)} required />
          </label>
          <label className="field">
            <span>Devolución</span>
            <input type="date" min={inicio || fechaLocal(0)} value={fin} onChange={(event) => setFin(event.target.value)} required />
          </label>
          <button className="button button-dark" type="submit">Ver disponibilidad <span aria-hidden="true">→</span></button>
        </form>
        {errorFechas && <p className="search-form-error" role="alert">{errorFechas}</p>}
      </section>

      <section className="home-intro section-wrap">
        <div>
          <p className="eyebrow">VIAJA A TU MANERA</p>
          <h2>Un buen viaje comienza<br />con el vehículo correcto.</h2>
        </div>
        <p>Escapada de fin de semana, viaje en familia o una ruta por descubrir. Encuentra opciones para cada plan y reserva en pocos pasos.</p>
      </section>

      <section className="benefit-grid section-wrap">
        {ventajas.map((ventaja) => (
          <article className="benefit-card" key={ventaja.numero}>
            <span>{ventaja.numero}</span>
            <h3>{ventaja.titulo}</h3>
            <p>{ventaja.texto}</p>
          </article>
        ))}
      </section>

      <section className="home-cta section-wrap">
        <div>
          <p className="eyebrow">TU VIAJE, A UN CLIC</p>
          <h2>¿Listo para salir?</h2>
        </div>
        <Link className="button button-dark" to="/flota">Reservar un vehículo <span aria-hidden="true">→</span></Link>
      </section>
    </>
  )
}

export default Home
