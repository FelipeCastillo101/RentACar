import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import api from '../api'

const formatoPesos = (monto) => new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0,
}).format(Number(monto) || 0)

function Productos() {
  const location = useLocation()
  const navigate = useNavigate()
  const estado = useMemo(() => location.state || {}, [location.state])
  const auto = estado.autoSeleccionado || estado.auto
  const { fechaInicio, fechaFin, horaInicio = '09:00', horaFin = '18:00' } = estado

  const [productos, setProductos] = useState([])
  const [seguros, setSeguros] = useState([])
  const [segurosElegidos, setSegurosElegidos] = useState([])
  const [productosElegidos, setProductosElegidos] = useState([])
  const [mensaje, setMensaje] = useState('')

  useEffect(() => {
    if (!auto) {
      navigate('/flota')
      return
    }
    Promise.all([api.get('/api/productos/'), api.get('/api/seguros/')])
      .then(([respuestaProductos, respuestaSeguros]) => {
        setProductos(respuestaProductos.data)
        setSeguros(respuestaSeguros.data)
      })
      .catch(() => setMensaje('No se pudieron cargar los seguros y accesorios.'))
  }, [auto, estado, navigate])

  const alternar = (id, actualizar) => {
    actualizar((actual) => (
      actual.includes(id) ? actual.filter((item) => item !== id) : [...actual, id]
    ))
  }

  const dias = Math.max(
    1,
    Math.ceil((
      new Date(`${fechaFin}T${horaFin}`) - new Date(`${fechaInicio}T${horaInicio}`)
    ) / (1000 * 60 * 60 * 24)),
  )
  const elegidosSeguros = seguros.filter((seguro) => segurosElegidos.includes(seguro.id))
  const elegidosProductos = productos.filter((producto) => productosElegidos.includes(producto.id))
  const totalSeguros = elegidosSeguros.reduce(
    (suma, seguro) => suma + Number(seguro.precio_diario) * dias, 0,
  )
  const totalProductos = elegidosProductos.reduce(
    (suma, producto) => suma + Number(producto.precio_diario) * dias, 0,
  )
  const totalArriendo = Number(auto.precio_diario) * dias

  const continuar = () => {
    navigate('/checkout', {
      state: {
        ...estado,
        autoSeleccionado: auto,
        segurosSeleccionados: elegidosSeguros,
        productosSeleccionados: elegidosProductos,
      },
    })
  }

  return (
    <main className="page products-page">
      <header className="products-header">
        <p className="eyebrow">PERSONALIZA TU VIAJE</p>
        <h1>Elige tus extras.</h1>
        <p>Agrega opcionalmente seguros y accesorios. El valor se calcula por los días de arriendo.</p>
        <div className="products-trip">
          <strong>{auto.marca} {auto.nombre_modelo}</strong>
          <span>{fechaInicio} · {horaInicio} — {fechaFin} · {horaFin}</span>
          <span>{dias} día(s)</span>
        </div>
      </header>

      {mensaje && <p role="alert" className="form-error">{mensaje}</p>}

      <section className="addon-section">
        <div className="addon-section-heading">
          <div>
            <p className="eyebrow">PROTECCIÓN</p>
            <h2>Seguros</h2>
          </div>
          <span>Opcional</span>
        </div>
        <div className="addon-grid">
          {seguros.map((seguro) => {
            const activo = segurosElegidos.includes(seguro.id)
            return (
              <button
                key={seguro.id}
                type="button"
                className={`addon-card ${activo ? 'selected' : ''}`}
                aria-pressed={activo}
                onClick={() => alternar(seguro.id, setSegurosElegidos)}
              >
                <span className="addon-card-top">
                  <span className="addon-indicator" aria-hidden="true">{activo ? '✓' : '+'}</span>
                  <span className="addon-price">{formatoPesos(seguro.precio_diario)}<small> / día</small></span>
                </span>
                <strong>{seguro.nombre}</strong>
                <span className="addon-description">{seguro.descripcion}</span>
                <span className="addon-detail">Deducible: {formatoPesos(seguro.deducible_monto)}</span>
              </button>
            )
          })}
          {seguros.length === 0 && !mensaje && <p className="empty-addons">No hay seguros disponibles.</p>}
        </div>
      </section>

      <section className="addon-section">
        <div className="addon-section-heading">
          <div>
            <p className="eyebrow">A BORDO</p>
            <h2>Accesorios y extras</h2>
          </div>
          <span>Opcional</span>
        </div>
        <div className="addon-grid">
          {productos.map((producto) => {
            const activo = productosElegidos.includes(producto.id)
            return (
              <button
                key={producto.id}
                type="button"
                className={`addon-card ${activo ? 'selected' : ''}`}
                aria-pressed={activo}
                onClick={() => alternar(producto.id, setProductosElegidos)}
              >
                <span className="addon-card-top">
                  <span className="addon-indicator" aria-hidden="true">{activo ? '✓' : '+'}</span>
                  <span className="addon-price">{formatoPesos(producto.precio_diario)}<small> / día</small></span>
                </span>
                <strong>{producto.nombre}</strong>
                <span className="addon-description">{producto.descripcion}</span>
              </button>
            )
          })}
          {productos.length === 0 && !mensaje && <p className="empty-addons">No hay accesorios disponibles.</p>}
        </div>
      </section>

      <section className="card addons-summary">
        <div>
          <p className="eyebrow">RESUMEN</p>
          <h2>Total estimado</h2>
          <p>El monto final se confirma al generar la solicitud.</p>
        </div>
        <div className="addons-totals">
          <span>Arriendo <strong>{formatoPesos(totalArriendo)}</strong></span>
          <span>Seguros <strong>{formatoPesos(totalSeguros)}</strong></span>
          <span>Accesorios <strong>{formatoPesos(totalProductos)}</strong></span>
          <span className="addons-grand-total">Total <strong>{formatoPesos(totalArriendo + totalSeguros + totalProductos)}</strong></span>
        </div>
        <div className="addons-actions">
          <button type="button" className="button button-outline" onClick={() => navigate('/flota')}>Volver</button>
          <button type="button" className="button button-primary" onClick={continuar}>
            Continuar con mis datos <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>
    </main>
  )
}

export default Productos
