import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import api, { apiError, toList } from '../api'

const fechaLocal = (desfase) => {
  const fecha = new Date()
  fecha.setDate(fecha.getDate() + desfase)
  return new Date(fecha.getTime() - fecha.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

const dinero = (monto) => new Intl.NumberFormat('es-CL', {
  style: 'currency',
  currency: 'CLP',
  maximumFractionDigits: 0,
}).format(Number(monto) || 0)

function repararCodificacion(texto) {
  let resultado = String(texto || '')
  for (let intento = 0; intento < 3 && /[ÃÂ]/.test(resultado); intento += 1) {
    const caracteres = Array.from(resultado)
    if (caracteres.some((caracter) => caracter.charCodeAt(0) > 255)) break
    try {
      resultado = new TextDecoder('utf-8', { fatal: true }).decode(
        Uint8Array.from(caracteres, (caracter) => caracter.charCodeAt(0)),
      )
    } catch {
      break
    }
  }
  return resultado
}

function nombreCategoria(nombre) {
  const corregido = repararCodificacion(nombre)
  const normalizado = corregido.normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es-CL')
  if (normalizado === 'economico') return 'Económico'
  if (normalizado === 'sedan') return 'Sedán'
  if (normalizado === 'van pasajeros') return 'Van de pasajeros'
  return corregido
}

function textoEspecificacion(texto) {
  const corregido = repararCodificacion(texto)
  const clave = corregido.normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es-CL')
  const etiquetas = {
    automatica: 'Automática',
    semiautomatica: 'Semiautomática',
    diesel: 'Diésel',
    electrico: 'Eléctrico',
    hibrido: 'Híbrido',
  }
  return etiquetas[clave] || corregido
}

const normalizarVehiculo = (vehiculo) => ({
  ...vehiculo,
  modelo: vehiculo.nombre_modelo || vehiculo.modelo || vehiculo.nombre || 'Vehículo',
  imagen: vehiculo.imagen || vehiculo.imagen_principal || vehiculo.imagen_url || '',
  descripcion: repararCodificacion(vehiculo.descripcion),
  transmision: textoEspecificacion(vehiculo.transmision),
  combustible: textoEspecificacion(vehiculo.combustible),
  categoria: nombreCategoria(
    vehiculo.categoria_nombre || vehiculo.categoria?.nombre || 'Categoría',
  ),
  pasajeros: vehiculo.pasajeros || vehiculo.categoria?.pasajeros,
})

const fuenteImagen = (imagen) => {
  const archivoCodificado = imagen.match(
    /^https:\/\/thumb\.wikimedia\.org\/wikipedia\/commons\/thumb\/[^/]+\/[^/]+\/\d+px-([^?]+)/,
  )?.[1]
  if (!archivoCodificado) return ''
  const archivo = encodeURIComponent(decodeURIComponent(archivoCodificado)).replace(/%20/g, '_')
  return `https://commons.wikimedia.org/wiki/File:${archivo}`
}

async function consultarDisponibilidad(inicio, fin, horaInicio, horaFin, categoria) {
  const { data } = await api.get('/api/reservas/disponibilidad/', {
    params: {
      inicio,
      fin,
      hora_inicio: horaInicio,
      hora_fin: horaFin,
      ...(categoria ? { categoria } : {}),
    },
  })
  return Array.isArray(data?.vehiculos_disponibles)
    ? data.vehiculos_disponibles.map(normalizarVehiculo)
    : []
}

function VehiculoModal({ vehiculo, onClose, onReserve }) {
  useEffect(() => {
    const cerrarConEscape = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', cerrarConEscape)
    document.body.classList.add('modal-open')
    return () => {
      document.removeEventListener('keydown', cerrarConEscape)
      document.body.classList.remove('modal-open')
    }
  }, [onClose])

  return (
    <div className="modal-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section className="vehicle-modal" role="dialog" aria-modal="true" aria-labelledby="vehicle-modal-title">
        <button className="icon-button modal-close" type="button" onClick={onClose} aria-label="Cerrar detalles">×</button>
        <div className="modal-photo-wrap">
          {vehiculo.imagen
            ? <img className="modal-photo" src={vehiculo.imagen} alt={`${vehiculo.marca} ${vehiculo.modelo}`} />
            : <div className="vehicle-placeholder modal-photo"><span>RENTACAR</span></div>}
        </div>
        <div className="vehicle-modal-body">
          <p className="eyebrow">{vehiculo.categoria}</p>
          <h2 id="vehicle-modal-title">{vehiculo.marca} {vehiculo.modelo}</h2>
          <p className="modal-description">{vehiculo.descripcion || 'Un vehículo cómodo y confiable, listo para acompañarte en tu próximo viaje.'}</p>
          <div className="spec-grid">
            <div><span>Pasajeros</span><strong>{vehiculo.pasajeros || '—'}</strong></div>
            <div><span>Transmisión</span><strong>{vehiculo.transmision || '—'}</strong></div>
            <div><span>Combustible</span><strong>{vehiculo.combustible || '—'}</strong></div>
            <div><span>Año</span><strong>{vehiculo.anio || vehiculo.ano || '—'}</strong></div>
          </div>
          <div className="modal-action-row">
            <p className="vehicle-price">{dinero(vehiculo.precio_diario)} <span>/ día</span></p>
            <button className="button button-dark" type="button" onClick={() => onReserve(vehiculo)}>Reservar este auto <span aria-hidden="true">→</span></button>
          </div>
        </div>
      </section>
    </div>
  )
}

function Flota() {
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [initialSearch] = useState(() => ({
    inicio: location.state?.fechaInicio || searchParams.get('inicio') || fechaLocal(1),
    fin: location.state?.fechaFin || searchParams.get('fin') || fechaLocal(4),
    categoria: searchParams.get('categoria') || '',
  }))
  const [vehiculos, setVehiculos] = useState([])
  const [categorias, setCategorias] = useState([])
  const [categoriaSeleccionada, setCategoriaSeleccionada] = useState(initialSearch.categoria)
  const [fechaInicio, setFechaInicio] = useState(initialSearch.inicio)
  const [fechaFin, setFechaFin] = useState(initialSearch.fin)
  const [horaInicio, setHoraInicio] = useState('09:00')
  const [horaFin, setHoraFin] = useState('18:00')
  const [mensaje, setMensaje] = useState('')
  const [errorDisponibilidad, setErrorDisponibilidad] = useState('')
  const [errorCategorias, setErrorCategorias] = useState('')
  const [cargando, setCargando] = useState(true)
  const [vehiculoAbierto, setVehiculoAbierto] = useState(null)
  const activeRequest = useRef(0)
  const categoriasAgrupadas = categorias.reduce((grupos, categoria) => {
    const nombre = nombreCategoria(categoria.nombre)
    const existente = grupos.find((grupo) => grupo.nombre === nombre)
    if (existente) {
      existente.ids.push(String(categoria.id))
    } else {
      grupos.push({ nombre, ids: [String(categoria.id)] })
    }
    return grupos
  }, [])

  const buscar = async (inicio, fin, categoria = categoriaSeleccionada, horaRetiro = horaInicio, horaDevolucion = horaFin) => {
    if (!inicio || !fin || fin <= inicio) {
      setMensaje('Selecciona fechas válidas. La devolución debe ser posterior al retiro.')
      setVehiculos([])
      return
    }
    const solicitud = ++activeRequest.current
    setCargando(true)
    setMensaje('')
    setErrorDisponibilidad('')
    try {
      const resultados = await consultarDisponibilidad(inicio, fin, horaRetiro, horaDevolucion, categoria)
      if (solicitud !== activeRequest.current) return
      setVehiculos(resultados)
      setMensaje(resultados.length === 0 ? 'No encontramos vehículos disponibles para esas fechas y filtros.' : '')
    } catch (error) {
      if (solicitud !== activeRequest.current) return
      setVehiculos([])
      setErrorDisponibilidad(apiError(error, 'No se pudo consultar la disponibilidad.'))
    } finally {
      if (solicitud === activeRequest.current) setCargando(false)
    }
  }

  useEffect(() => {
    let activa = true
    const solicitudInicial = ++activeRequest.current
    api.get('/api/categorias/')
      .then(({ data }) => {
        if (activa) setCategorias(toList(data))
      })
      .catch((error) => {
        if (activa) setErrorCategorias(apiError(error, 'No se pudieron cargar las categorías.'))
      })
    consultarDisponibilidad(initialSearch.inicio, initialSearch.fin, '09:00', '18:00', initialSearch.categoria)
      .then((resultados) => {
        if (activa && solicitudInicial === activeRequest.current) {
          setVehiculos(resultados)
          setMensaje(resultados.length === 0 ? 'No encontramos vehículos disponibles para esas fechas y filtros.' : '')
        }
      })
      .catch((error) => {
        if (activa && solicitudInicial === activeRequest.current) {
          setErrorDisponibilidad(apiError(error, 'No se pudo consultar la disponibilidad.'))
        }
      })
      .finally(() => {
        if (activa && solicitudInicial === activeRequest.current) setCargando(false)
      })
    return () => {
      activa = false
      activeRequest.current += 1
    }
  }, [initialSearch])

  const enviarBusqueda = (event) => {
    event.preventDefault()
    setSearchParams({
      inicio: fechaInicio,
      fin: fechaFin,
      ...(categoriaSeleccionada ? { categoria: categoriaSeleccionada } : {}),
    })
    buscar(fechaInicio, fechaFin)
  }

  const cambiarCategoria = (categoria) => {
    setCategoriaSeleccionada(categoria)
    setSearchParams({
      inicio: fechaInicio,
      fin: fechaFin,
      ...(categoria ? { categoria } : {}),
    })
    buscar(fechaInicio, fechaFin, categoria)
  }

  const reservar = (auto) => {
    navigate('/checkout', {
      state: {
        autoSeleccionado: auto,
        fechaInicio,
        fechaFin,
        horaInicio,
        horaFin,
      },
    })
  }

  return (
    <>
      <section className="page-heading section-wrap">
        <p className="eyebrow">ENCUENTRA TU PRÓXIMO AUTO</p>
        <h1>Vehículos para cada camino.</h1>
        <p>Elige tus fechas, explora opciones y reserva el vehículo que mejor se adapta a tu viaje.</p>
      </section>

      <section className="fleet-search section-wrap">
        <form className="fleet-search-form" onSubmit={enviarBusqueda}>
          <label className="field">
            <span>Fecha de retiro</span>
            <input type="date" min={fechaLocal(0)} value={fechaInicio} onChange={(event) => setFechaInicio(event.target.value)} required />
          </label>
          <label className="field">
            <span>Hora de retiro</span>
            <input type="time" min="09:00" max="18:00" value={horaInicio} onChange={(event) => setHoraInicio(event.target.value)} required />
          </label>
          <label className="field">
            <span>Fecha de devolución</span>
            <input type="date" min={fechaInicio || fechaLocal(0)} value={fechaFin} onChange={(event) => setFechaFin(event.target.value)} required />
          </label>
          <label className="field">
            <span>Hora de devolución</span>
            <input type="time" min="09:00" max="18:00" value={horaFin} onChange={(event) => setHoraFin(event.target.value)} required />
          </label>
          <button className="button button-dark search-button" type="submit" disabled={cargando}>
            {cargando ? 'Buscando…' : 'Buscar autos'} <span aria-hidden="true">→</span>
          </button>
        </form>
      </section>

      <section className="fleet-results section-wrap">
        <div className="results-topline">
          <div>
            <p className="eyebrow">NUESTRA FLOTA</p>
            <h2>Elige tu compañero de ruta</h2>
          </div>
          <span className="result-count">{cargando ? 'Buscando disponibilidad…' : `${vehiculos.length} ${vehiculos.length === 1 ? 'opción' : 'opciones'}`}</span>
        </div>
        <div className="category-filters" aria-label="Filtrar por categoría">
          <button className={`filter-chip ${categoriaSeleccionada === '' ? 'selected' : ''}`} type="button" onClick={() => cambiarCategoria('')}>Todas las categorías</button>
          {categoriasAgrupadas.map((categoria) => (
            <button
              className={`filter-chip ${categoria.ids.some((id) => categoriaSeleccionada.split(',').includes(id)) ? 'selected' : ''}`}
              key={categoria.nombre}
              type="button"
              onClick={() => cambiarCategoria(categoria.ids.join(','))}
            >
              {categoria.nombre}
            </button>
          ))}
        </div>

        {errorCategorias && (
          <div className="notice notice-error" role="alert">
            <span>{errorCategorias}</span>
            <button className="text-button" type="button" onClick={() => window.location.reload()}>Reintentar</button>
          </div>
        )}
        {errorDisponibilidad && (
          <div className="notice notice-error" role="alert">
            <span>{errorDisponibilidad}</span>
            <button className="text-button" type="button" onClick={() => buscar(fechaInicio, fechaFin)}>Reintentar búsqueda</button>
          </div>
        )}
        {mensaje && <div className={`notice ${cargando ? 'notice-loading' : ''}`} role="status">{mensaje}</div>}

        <div className="vehicle-grid">
          {vehiculos.map((auto) => (
            <article className="vehicle-card" key={auto.id}>
              <div className="vehicle-image-wrap">
                {auto.imagen
                  ? <img className="vehicle-image" src={auto.imagen} alt={`${auto.marca} ${auto.modelo}`} loading="lazy" />
                  : <div className="vehicle-placeholder"><span>RENTACAR</span></div>}
                {fuenteImagen(auto.imagen) && (
                  <a
                    className="image-attribution"
                    href={fuenteImagen(auto.imagen)}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(event) => event.stopPropagation()}
                  >
                    Fuente y licencia
                  </a>
                )}
                <span className="vehicle-category">{auto.categoria}</span>
              </div>
              <div className="vehicle-card-body">
                <div className="vehicle-title-row">
                  <div>
                    <p className="eyebrow">{auto.marca || 'RENTACAR'}</p>
                    <h3>{auto.modelo}</h3>
                  </div>
                  {auto.stock_disponible != null && <span className="stock-tag">{auto.stock_disponible} disponible{auto.stock_disponible === 1 ? '' : 's'}</span>}
                </div>
                <div className="vehicle-specs">
                  <span>{auto.pasajeros || '—'} pasajeros</span>
                  <span>{auto.transmision || '—'}</span>
                  <span>{auto.combustible || '—'}</span>
                </div>
                <div className="vehicle-card-bottom">
                  <p className="vehicle-price">{dinero(auto.precio_diario)} <span>/ día</span></p>
                  <div className="vehicle-card-actions">
                    <button className="button button-outline" type="button" onClick={() => setVehiculoAbierto(auto)}>Ver detalles</button>
                    <button className="button button-dark" type="button" onClick={() => reservar(auto)}>Reservar <span aria-hidden="true">→</span></button>
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      {vehiculoAbierto && (
        <VehiculoModal
          vehiculo={vehiculoAbierto}
          onClose={() => setVehiculoAbierto(null)}
          onReserve={reservar}
        />
      )}
    </>
  )
}

export default Flota
