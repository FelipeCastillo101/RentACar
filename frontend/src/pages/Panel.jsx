import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { useSesion } from '../sesion'

const ESTADOS = {
  PENDIENTE_PAGO: 'Pendiente de pago',
  CONFIRMADA: 'Confirmada',
  EN_CURSO: 'En curso',
  CANCELACION_EN_PROCESO: 'Cancelación en proceso',
  COMPLETADA: 'Completada',
  CANCELADA: 'Cancelada',
  EXPIRADA: 'Expirada',
}

const estiloFormulario = { display: 'grid', gap: '10px', maxWidth: '680px' }
const estadoVehiculoCodigo = {
  activo: 'ACTIVO',
  en_arrendamiento: 'EN_ARRENDAMIENTO',
  limpieza: 'LIMPIEZA',
  mantencion: 'MANTENCION',
  fuera_servicio: 'FUERA_SERVICIO',
  baja: 'BAJA',
}
const productoInicial = {
  nombre: '', tipo: '', descripcion: '', precio_diario: '0', activo: true,
}
const vehiculoInicial = {
  patente: '', anio: '', color: '', kilometraje: '0', modelo_id: '',
  sucursal_id: '', estado_operativo: 'ACTIVO', observaciones: '',
}

function valorFechaHoraLocal(valor) {
  const fecha = new Date(valor)
  fecha.setMinutes(fecha.getMinutes() - fecha.getTimezoneOffset())
  return fecha.toISOString().slice(0, 16)
}

function fechaLocalHoy() {
  const fecha = new Date()
  return [
    fecha.getFullYear(),
    String(fecha.getMonth() + 1).padStart(2, '0'),
    String(fecha.getDate()).padStart(2, '0'),
  ].join('-')
}

function formatoDinero(valor) {
  return new Intl.NumberFormat('es-CL', {
    style: 'currency',
    currency: 'CLP',
    maximumFractionDigits: 0,
  }).format(Number(valor || 0))
}

function formatoFecha(valor) {
  return new Intl.DateTimeFormat('es-CL', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${valor}T00:00:00Z`))
}

function reproducirAlerta(contexto) {
  if (!contexto || contexto.state !== 'running') return
  const oscilador = contexto.createOscillator()
  const volumen = contexto.createGain()
  const ahora = contexto.currentTime
  oscilador.type = 'sine'
  oscilador.frequency.setValueAtTime(880, ahora)
  volumen.gain.setValueAtTime(0.0001, ahora)
  volumen.gain.exponentialRampToValueAtTime(0.15, ahora + 0.02)
  volumen.gain.exponentialRampToValueAtTime(0.0001, ahora + 0.35)
  oscilador.connect(volumen)
  volumen.connect(contexto.destination)
  oscilador.start(ahora)
  oscilador.stop(ahora + 0.35)
}

function IndicadorDashboard({ titulo, valor, detalle }) {
  return (
    <article className="dashboard-metric">
      <p>{titulo}</p>
      <strong>{valor}</strong>
      {detalle && <span>{detalle}</span>}
    </article>
  )
}

function BarraDashboard({ titulo, valor, total }) {
  const porcentaje = total ? Math.min((valor / total) * 100, 100) : 0
  return (
    <div className="dashboard-bar-item">
      <div className="dashboard-bar-label">
        <span>{titulo}</span>
        <strong>{valor}</strong>
      </div>
      <div
        className="dashboard-bar-track"
        role="progressbar"
        aria-label={`${titulo}: ${valor} de ${total}`}
        aria-valuemin="0"
        aria-valuemax={total}
        aria-valuenow={valor}
      >
        <span style={{ width: `${porcentaje}%` }} />
      </div>
    </div>
  )
}

function PanelDashboard({
  datos,
  cargando,
  periodo,
  fecha,
  alCambiarPeriodo,
  alCambiarFecha,
  esAdmin,
}) {
  const finanzas = datos?.finanzas
  const flota = datos?.flota
  const cancelaciones = datos?.cancelaciones

  return (
    <section className="card panel-dashboard">
      <div className="dashboard-heading">
        <div>
          <p className="eyebrow">RESUMEN DEL NEGOCIO</p>
          <h2>Dashboard</h2>
          {datos?.periodo && (
            <p className="dashboard-range">
              {formatoFecha(datos.periodo.inicio)} – {formatoFecha(datos.periodo.fin)}
            </p>
          )}
        </div>
        <div className="dashboard-filters">
          <label>
            Período
            <select value={periodo} onChange={(evento) => alCambiarPeriodo(evento.target.value)}>
              <option value="dia">Día</option>
              <option value="semana">Semana</option>
              <option value="mes">Mes</option>
              <option value="trimestre">Trimestre</option>
              <option value="semestre">Semestre</option>
              <option value="anio">Año</option>
            </select>
          </label>
          <label>
            Fecha de referencia
            <input type="date" value={fecha} onChange={(evento) => alCambiarFecha(evento.target.value)} />
          </label>
        </div>
      </div>

      {cargando && <p role="status">Actualizando indicadores…</p>}
      {!datos && !cargando && (
        <p className="dashboard-empty">No fue posible cargar los indicadores.</p>
      )}
      {datos && (
        <>
          <div className="dashboard-section">
            <h3>Actividad del período</h3>
            <div className="dashboard-metrics-grid">
              <IndicadorDashboard
                titulo="Reservas del período"
                valor={datos.reservas.total}
                detalle={`${datos.reservas.vehiculos_arrendados} vehículos asociados · ${datos.reservas.clientes_arrendatarios} clientes`}
              />
              <IndicadorDashboard
                titulo="Clientes nuevos"
                valor={datos.clientes.nuevos_periodo}
                detalle={`${datos.clientes.arrendando} con arriendo en curso`}
              />
              <IndicadorDashboard
                titulo="Cancelaciones"
                valor={cancelaciones.total}
                detalle={`${cancelaciones.pendientes} pendientes por revisar`}
              />
              {esAdmin && finanzas && (
                <>
                  <IndicadorDashboard
                    titulo="Ventas netas"
                    valor={formatoDinero(finanzas.ventas_netas)}
                    detalle={`${finanzas.pagos_autorizados} pagos autorizados`}
                  />
                  <IndicadorDashboard
                    titulo="Devoluciones pagadas"
                    valor={formatoDinero(finanzas.monto_reembolsado)}
                    detalle={`${finanzas.reembolsos_completados} transferencias registradas`}
                  />
                  <IndicadorDashboard
                    titulo="Gastos operacionales estimados"
                    valor={formatoDinero(finanzas.gastos_operacionales_estimados)}
                    detalle={`Estimación referencial: ${finanzas.gastos_estimados_porcentaje}% de ventas netas`}
                  />
                </>
              )}
            </div>
          </div>

          <div className="dashboard-section dashboard-current">
            <div>
              <h3>Estado actual de la flota</h3>
              <p>{flota.total} vehículos registrados</p>
              <div className="dashboard-bars">
                <BarraDashboard titulo="Disponibles" valor={flota.disponibles} total={flota.total} />
                <BarraDashboard titulo="En arriendo" valor={flota.en_arrendamiento} total={flota.total} />
                <BarraDashboard titulo="En limpieza" valor={flota.limpieza} total={flota.total} />
                <BarraDashboard titulo="En mantención" valor={flota.mantencion} total={flota.total} />
                <BarraDashboard titulo="Fuera de servicio" valor={flota.fuera_servicio} total={flota.total} />
                <BarraDashboard titulo="Dados de baja" valor={flota.baja} total={flota.total} />
              </div>
            </div>
            <div className="dashboard-side-summary">
              <h3>Clientes</h3>
              <IndicadorDashboard titulo="Total activos" valor={datos.clientes.total} />
              <IndicadorDashboard titulo="Arrendando ahora" valor={datos.clientes.arrendando} />
              <IndicadorDashboard titulo="Sin arriendo activo" valor={datos.clientes.sin_arriendo_actual} />
              <h3>Solicitudes de cancelación</h3>
              <p>{cancelaciones.en_revision} en revisión · {cancelaciones.aprobadas} aprobadas</p>
              <p>{cancelaciones.rechazadas} rechazadas · {cancelaciones.reembolsadas} cerradas o reembolsadas</p>
            </div>
          </div>

          {esAdmin && (
            <p className="dashboard-disclaimer">
              Los gastos operacionales son una estimación referencial calculada como porcentaje de
              las ventas netas; no reemplaza los registros contables reales.
            </p>
          )}
        </>
      )}
    </section>
  )
}

function Panel() {
  const { sesion } = useSesion()
  const navigate = useNavigate()
  const esAdmin = sesion?.rol === 'admin'
  const esTrabajador = sesion?.tipo === 'trabajador'
  const [pestana, setPestana] = useState('dashboard')
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  const [termino, setTermino] = useState('')
  const [reservas, setReservas] = useState([])
  const [reserva, setReserva] = useState(null)
  const [edicionReserva, setEdicionReserva] = useState(null)
  const [modelos, setModelos] = useState([])
  const [vehiculos, setVehiculos] = useState([])
  const [sucursales, setSucursales] = useState([])
  const [clientes, setClientes] = useState([])
  const [productos, setProductos] = useState([])
  const [clienteEditando, setClienteEditando] = useState(null)
  const [productoEditando, setProductoEditando] = useState(null)
  const [formProducto, setFormProducto] = useState(productoInicial)
  const [vehiculoEditando, setVehiculoEditando] = useState(null)
  const [formVehiculo, setFormVehiculo] = useState(vehiculoInicial)
  const [cancelaciones, setCancelaciones] = useState([])
  const [datosFinanzas, setDatosFinanzas] = useState(null)
  const [datosDashboard, setDatosDashboard] = useState(null)
  const [cargandoDashboard, setCargandoDashboard] = useState(false)
  const [periodoDashboard, setPeriodoDashboard] = useState('mes')
  const [fechaDashboard, setFechaDashboard] = useState(fechaLocalHoy)
  const [cancelacionesPendientes, setCancelacionesPendientes] = useState(0)
  const [sonidoActivo, setSonidoActivo] = useState(false)
  const idsNotificacionesAnteriores = useRef(null)
  const contextoAudio = useRef(null)
  const [estimacionesCancelacion, setEstimacionesCancelacion] = useState({})
  const [referencias, setReferencias] = useState({})
  const [montosReembolso, setMontosReembolso] = useState({})
  const [comprobantesReembolso, setComprobantesReembolso] = useState({})
  const [formCliente, setFormCliente] = useState({
    tipo_documento: 'RUT', numero_documento: '', nombre: '', apellido: '',
    correo: '', telefono: '', fecha_nacimiento: '', licencia: '',
    licencia_vencimiento: '',
  })
  const [formReserva, setFormReserva] = useState({
    modelo_id: '', fecha_inicio: '', fecha_fin: '',
    hora_inicio: '09:00', hora_fin: '18:00', acepto: false,
  })
  const [formOperacion, setFormOperacion] = useState({
    metodo_pago: 'efectivo', referencia_externa: '',
    kilometraje: '', nivel_combustible: 'Lleno',
    requiere_revision: false,
  })
  const [formCancelacionSucursal, setFormCancelacionSucursal] = useState({
    motivo: '', banco_destino: '', tipo_cuenta: 'vista', numero_cuenta: '',
    tipo_documento_titular: 'RUT', rut_titular: '', nombre_titular: '',
  })
  const [verificaciones, setVerificaciones] = useState({
    codigo_orden_verificado: false,
    identidad_verificada: false,
    licencia_verificada: false,
    garantia_verificada: false,
  })

  useEffect(() => {
    if (!sesion || sesion.tipo !== 'trabajador') navigate('/login', { replace: true })
  }, [sesion, navigate])

  const mostrarError = useCallback((err) => {
    const data = err.response?.data
    setError(data && typeof data === 'object'
      ? Object.values(data).flat().join(' ')
      : 'Ocurrió un error al completar la operación.')
  }, [])

  useEffect(() => {
    if (!esTrabajador) return undefined

    let activo = true
    const actualizarNotificaciones = async () => {
      try {
        const response = await api.get('/api/cancelaciones/notificaciones/')
        if (!activo) return
        const ids = new Set((response.data.ids || []).map((id) => String(id)))
        const anteriores = idsNotificacionesAnteriores.current
        const hayNuevas = anteriores && [...ids].some((id) => !anteriores.has(id))
        if (hayNuevas && sonidoActivo && contextoAudio.current) {
          reproducirAlerta(contextoAudio.current)
        }
        idsNotificacionesAnteriores.current = ids
        setCancelacionesPendientes(response.data.cantidad)
      } catch (err) {
        if (activo) mostrarError(err)
      }
    }

    actualizarNotificaciones()
    const intervalo = window.setInterval(actualizarNotificaciones, 30000)
    return () => {
      activo = false
      window.clearInterval(intervalo)
    }
  }, [esTrabajador, mostrarError, sonidoActivo])

  useEffect(() => {
    if (pestana !== 'dashboard' || !esTrabajador) return undefined
    let activo = true
    api.get('/api/reservas/dashboard/', {
      params: { periodo: periodoDashboard, fecha: fechaDashboard },
    }).then((response) => {
      if (activo) setDatosDashboard(response.data)
    }).catch((err) => {
      if (activo) mostrarError(err)
    }).finally(() => {
      if (activo) setCargandoDashboard(false)
    })
    return () => {
      activo = false
    }
  }, [esTrabajador, fechaDashboard, mostrarError, periodoDashboard, pestana])

  const cambiarPeriodoDashboard = (periodo) => {
    setCargandoDashboard(true)
    setError('')
    setPeriodoDashboard(periodo)
  }

  const cambiarFechaDashboard = (fecha) => {
    setCargandoDashboard(true)
    setError('')
    setFechaDashboard(fecha)
  }

  const alternarSonido = async () => {
    if (sonidoActivo) {
      setSonidoActivo(false)
      return
    }
    if (!window.AudioContext) {
      setError('Este navegador no permite activar las alertas sonoras.')
      return
    }
    try {
      const contexto = contextoAudio.current || new window.AudioContext()
      await contexto.resume()
      contextoAudio.current = contexto
      setSonidoActivo(true)
      reproducirAlerta(contexto)
      setError('')
    } catch (err) {
      setError(`No se pudo activar el sonido: ${err.message}`)
    }
  }

  const buscar = async (evento) => {
    evento.preventDefault()
    setError('')
    setMensaje('')
    try {
      const response = await api.get('/api/reservas/buscar/', { params: { q: termino } })
      setReservas(response.data)
      setReserva(response.data.length === 1 ? response.data[0] : null)
      setEdicionReserva(null)
      if (!response.data.length) setMensaje('No se encontraron reservas.')
    } catch (err) {
      mostrarError(err)
    }
  }

  const actualizarReserva = async (id) => {
    try {
      const response = await api.get(`/api/reservas/${id}/`)
      setReserva(response.data)
      setEdicionReserva(null)
      setReservas((actuales) => actuales.map((item) => item.id === id ? response.data : item))
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarModelos = async () => {
    try {
      const response = await api.get('/api/modelos/')
      setModelos(response.data)
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarVehiculos = async () => {
    try {
      const response = await api.get('/api/vehiculos/')
      setVehiculos(response.data)
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarSucursales = async () => {
    try {
      const response = await api.get('/api/sucursales/')
      setSucursales(response.data)
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarClientes = async () => {
    try {
      const response = await api.get('/api/clientes/')
      setClientes(response.data)
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarProductos = async () => {
    try {
      const response = await api.get('/api/productos/')
      setProductos(response.data)
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarCancelaciones = async () => {
    try {
      const response = await api.get('/api/cancelaciones/')
      setCancelaciones(response.data)
    } catch (err) {
      mostrarError(err)
    }
  }

  useEffect(() => {
    if (pestana === 'nueva') cargarModelos()
    if (pestana === 'vehiculos') {
      cargarVehiculos()
      if (esAdmin) {
        cargarModelos()
        cargarSucursales()
      }
    }
    if (pestana === 'cancelaciones') cargarCancelaciones()
    if (pestana === 'clientes' && esAdmin) cargarClientes()
    if (pestana === 'productos' && esAdmin) cargarProductos()
  }, [pestana, esAdmin])

  const guardarCliente = async (evento) => {
    evento.preventDefault()
    try {
      await api.patch(`/api/clientes/${clienteEditando.id}/`, {
        nombre: clienteEditando.nombre,
        apellido: clienteEditando.apellido,
        correo: clienteEditando.correo,
        telefono: clienteEditando.telefono || '',
        activo: clienteEditando.activo,
      })
      setClienteEditando(null)
      setMensaje('Datos del cliente actualizados.')
      await cargarClientes()
    } catch (err) {
      mostrarError(err)
    }
  }

  const guardarProducto = async (evento) => {
    evento.preventDefault()
    try {
      const payload = {
        ...formProducto,
        precio_diario: Number(formProducto.precio_diario),
      }
      if (productoEditando) {
        await api.patch(`/api/productos/${productoEditando}/`, payload)
      } else {
        await api.post('/api/productos/', payload)
      }
      setProductoEditando(null)
      setFormProducto(productoInicial)
      setMensaje('Producto guardado.')
      await cargarProductos()
    } catch (err) {
      mostrarError(err)
    }
  }

  const guardarVehiculo = async (evento) => {
    evento.preventDefault()
    try {
      const payload = {
        ...formVehiculo,
        anio: Number(formVehiculo.anio),
        kilometraje: Number(formVehiculo.kilometraje),
        modelo_id: Number(formVehiculo.modelo_id),
        sucursal_id: Number(formVehiculo.sucursal_id),
      }
      if (vehiculoEditando) {
        await api.patch(`/api/vehiculos/${vehiculoEditando}/`, payload)
      } else {
        await api.post('/api/vehiculos/', payload)
      }
      setVehiculoEditando(null)
      setFormVehiculo(vehiculoInicial)
      setMensaje('Vehículo guardado.')
      await cargarVehiculos()
    } catch (err) {
      mostrarError(err)
    }
  }

  const cambiarCliente = (evento) => {
    setFormCliente((actual) => ({ ...actual, [evento.target.name]: evento.target.value }))
  }
  const cambiarReserva = (evento) => {
    const { name, value, checked, type } = evento.target
    setFormReserva((actual) => ({ ...actual, [name]: type === 'checkbox' ? checked : value }))
  }

  const crearReservaPresencial = async (evento) => {
    evento.preventDefault()
    setError('')
    setMensaje('')
    if (!formReserva.acepto) {
      setError('Debes confirmar que el cliente leyó y aceptó el contrato en sucursal.')
      return
    }
    try {
      const clienteResponse = await api.post('/api/clientes/registrar_o_buscar/', formCliente)
      const cliente = clienteResponse.data
      const response = await api.post('/api/reservas/', {
        cliente_id: cliente.id,
        modelo_id: Number(formReserva.modelo_id),
        fecha_hora_retiro: `${formReserva.fecha_inicio}T${formReserva.hora_inicio}:00`,
        fecha_hora_devolucion: `${formReserva.fecha_fin}T${formReserva.hora_fin}:00`,
        tipo_documento: cliente.tipo_documento,
        numero_documento: cliente.numero_documento,
        licencia: cliente.licencia,
        licencia_vencimiento: cliente.licencia_vencimiento,
        fecha_nacimiento: cliente.fecha_nacimiento,
        nombre: cliente.nombre,
        apellido: cliente.apellido,
        correo: cliente.correo,
        telefono: cliente.telefono || '',
        firma_condiciones: true,
      })
      setReserva(response.data)
      setMensaje(`Reserva ${response.data.codigo} creada. Registra el pago en sucursal para confirmarla.`)
    } catch (err) {
      mostrarError(err)
    }
  }

  const confirmarPagoPresencial = async () => {
    if (!reserva) return
    try {
      const response = await api.post(`/api/reservas/${reserva.id}/confirmar_presencial/`, {
        metodo_pago: formOperacion.metodo_pago,
        referencia_externa: formOperacion.referencia_externa,
      })
      setReserva(response.data)
      setMensaje('Pago presencial registrado. La reserva está confirmada.')
    } catch (err) {
      mostrarError(err)
    }
  }

  const comenzarEdicionReserva = () => {
    setEdicionReserva({
      retiro: valorFechaHoraLocal(reserva.fecha_hora_retiro),
      devolucion: valorFechaHoraLocal(reserva.fecha_hora_devolucion),
      aceptado: false,
    })
  }

  const guardarEdicionReserva = async (evento) => {
    evento.preventDefault()
    setError('')
    try {
      const response = await api.patch(`/api/reservas/${reserva.id}/`, {
        fecha_hora_retiro: edicionReserva.retiro,
        fecha_hora_devolucion: edicionReserva.devolucion,
        firma_condiciones: edicionReserva.aceptado,
      })
      setReserva(response.data)
      setReservas((actuales) => actuales.map((item) => item.id === response.data.id ? response.data : item))
      setEdicionReserva(null)
      setMensaje('Fechas actualizadas y orden recalculada. El cliente aceptó el cambio.')
    } catch (err) {
      mostrarError(err)
    }
  }

  const cambiarEstadoReserva = async (estado) => {
    if (!reserva) return
    const payload = {
      estado,
      kilometraje: formOperacion.kilometraje,
      nivel_combustible: formOperacion.nivel_combustible,
      requiere_revision: formOperacion.requiere_revision,
    }
    if (estado === 'EN_CURSO') {
      Object.assign(payload, verificaciones)
    }
    try {
      const response = await api.post(`/api/reservas/${reserva.id}/estado/`, payload)
      setReserva(response.data)
      setMensaje(estado === 'EN_CURSO'
        ? 'Entrega registrada. Las llaves pueden entregarse al cliente.'
        : 'Devolución e inspección registradas.')
    } catch (err) {
      mostrarError(err)
    }
  }

  const solicitarCancelacionEnSucursal = async (evento) => {
    evento.preventDefault()
    if (!reserva) return
    try {
      await api.post('/api/cancelaciones/', {
        codigo_reserva: reserva.codigo,
        ...formCancelacionSucursal,
      })
      setMensaje('Cancelación enviada a revisión. El trabajador puede derivarla a Finanzas.')
      setFormCancelacionSucursal({
        motivo: '', banco_destino: '', tipo_cuenta: 'vista', numero_cuenta: '',
        tipo_documento_titular: 'RUT', rut_titular: '', nombre_titular: '',
      })
      await actualizarReserva(reserva.id)
    } catch (err) {
      mostrarError(err)
    }
  }

  const operarCancelacion = async (id, accion, payload = {}) => {
    setError('')
    try {
      const response = await api.post(`/api/cancelaciones/${id}/${accion}/`, payload)
      setMensaje(response.data.aviso || 'La solicitud de cancelación fue actualizada.')
      await cargarCancelaciones()
    } catch (err) {
      mostrarError(err)
    }
  }

  const registrarDevolucionExterna = async (id) => {
    setError('')
    const archivo = comprobantesReembolso[id]
    if (!montosReembolso[id] || !referencias[id]?.trim()) {
      setError('Indica el monto transferido y su código de comprobante.')
      return
    }
    if (!archivo) {
      setError('Adjunta el comprobante de la transferencia.')
      return
    }
    const formData = new FormData()
    formData.append('monto', montosReembolso[id] || '')
    formData.append('numero_transaccion_externa', referencias[id] || '')
    formData.append('comprobante', archivo)
    try {
      const response = await api.post(
        `/api/cancelaciones/${id}/registrar_reembolso/`,
        formData,
      )
      setMensaje(response.data.aviso || (
        `Cancelación completada. Comprobante ${response.data.codigo_comprobante || referencias[id]}. Se notificó al cliente.`
      ))
      setComprobantesReembolso((actuales) => ({ ...actuales, [id]: null }))
      await cargarCancelaciones()
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarDatosFinanzas = async (id) => {
    try {
      const response = await api.get(`/api/cancelaciones/${id}/datos_finanzas/`)
      setDatosFinanzas({ id, ...response.data })
    } catch (err) {
      mostrarError(err)
    }
  }

  const cargarEstimacionCancelacion = async (item) => {
    try {
      const response = await api.get('/api/cancelaciones/cotizacion/', {
        params: { codigo: item.codigo },
      })
      setEstimacionesCancelacion((actuales) => ({
        ...actuales, [item.id]: response.data,
      }))
    } catch (err) {
      mostrarError(err)
    }
  }

  const descargarComprobanteReembolso = async (id, codigo) => {
    try {
      const response = await api.get(
        `/api/cancelaciones/${id}/comprobante_finanzas/`,
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const enlace = document.createElement('a')
      enlace.href = url
      const disposition = response.headers['content-disposition'] || ''
      const nombre = disposition.match(/filename="?([^";]+)"?/i)?.[1]
      const extension = {
        'application/pdf': '.pdf',
        'image/png': '.png',
        'image/jpeg': '.jpg',
      }[response.headers['content-type']] || ''
      enlace.download = nombre || `comprobante-transferencia-${codigo}${extension}`
      enlace.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      mostrarError(err)
    }
  }

  if (!sesion || sesion.tipo !== 'trabajador') return null

  const pestanas = [
    ['dashboard', 'Dashboard'],
    ['reservas', 'Buscar reserva'],
    ['modificar', 'Modificar reserva'],
    ['nueva', 'Reserva presencial'],
    ['cancelaciones', 'Cancelaciones'],
    ...(esAdmin ? [
      ['vehiculos', 'Flota'],
      ['clientes', 'Clientes'],
      ['productos', 'Productos'],
    ] : []),
  ]

  return (
    <main className="page admin-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">{esAdmin ? 'ADMINISTRACIÓN' : 'OPERACIONES'}</p>
          <h1>{esAdmin ? 'Panel administrativo' : 'Panel de operación'}</h1>
        </div>
        <div className="panel-notifications">
          <button
            type="button"
            className="panel-bell"
            aria-label={`Ver solicitudes de cancelación${cancelacionesPendientes ? `, ${cancelacionesPendientes} pendientes` : ''}`}
            onClick={() => { setPestana('cancelaciones'); setError(''); setMensaje('') }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
            </svg>
            <span>Cancelaciones</span>
            {cancelacionesPendientes > 0 && (
              <span className="panel-bell-count">
                {cancelacionesPendientes > 99 ? '99+' : cancelacionesPendientes}
              </span>
            )}
          </button>
          <button
            type="button"
            className={sonidoActivo ? 'button button-primary panel-sound' : 'button button-secondary panel-sound'}
            aria-pressed={sonidoActivo}
            onClick={alternarSonido}
          >
            {sonidoActivo ? 'Silenciar sonido' : 'Activar sonido'}
          </button>
        </div>
      </div>
      <p className="panel-intro">
        {esAdmin
          ? 'Administra la operación, la flota, los clientes y el catálogo.'
          : 'Gestiona reservas, pagos presenciales y solicitudes de cancelación.'}
      </p>
      <nav className="panel-tabs" aria-label="Secciones del panel">
        {pestanas.map(([key, label]) => (
          <button key={key} type="button" className={pestana === key ? 'button button-primary' : 'button button-secondary'}
            onClick={() => {
              if (key === 'dashboard') setCargandoDashboard(true)
              setPestana(key)
              setError('')
              setMensaje('')
            }}>
            {label}
          </button>
        ))}
      </nav>
      {mensaje && <p role="status">{mensaje}</p>}
      {error && <p role="alert" className="form-error">{error}</p>}

      {pestana === 'dashboard' && (
        <PanelDashboard
          datos={datosDashboard}
          cargando={cargandoDashboard}
          periodo={periodoDashboard}
          fecha={fechaDashboard}
          alCambiarPeriodo={cambiarPeriodoDashboard}
          alCambiarFecha={cambiarFechaDashboard}
          esAdmin={esAdmin}
        />
      )}

      {pestana === 'reservas' && (
        <section className="card">
          <h2>Buscar por código, documento o patente</h2>
          <form onSubmit={buscar} className="inline-form">
            <input value={termino} onChange={(evento) => setTermino(evento.target.value)}
              placeholder="RC-000001, RUT o patente" required />
            <button type="submit" className="button button-primary">Buscar</button>
          </form>
          {reservas.length > 1 && (
            <ul>{reservas.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => actualizarReserva(item.id)}>
                  {item.codigo} · {ESTADOS[item.estado] || item.estado}
                </button>
              </li>
            ))}</ul>
          )}
          {reserva && (
            <div>
              <h3>{reserva.codigo} · {ESTADOS[reserva.estado] || reserva.estado}</h3>
              <p>{reserva.cliente?.nombre} · {reserva.modelo?.marca} {reserva.modelo?.nombre_modelo}</p>
              <p>{reserva.fecha_hora_retiro} → {reserva.fecha_hora_devolucion}</p>
              <p>Total: ${reserva.total} · Patente: {reserva.vehiculo?.patente}</p>
              {reserva.estado === 'PENDIENTE_PAGO' && (
                <button type="button" className="button button-secondary"
                  onClick={() => { setPestana('modificar'); setEdicionReserva(null) }}>
                  Modificar fechas y horarios
                </button>
              )}
              {reserva.estado === 'PENDIENTE_PAGO' && (
                <div className="form-grid">
                  <label>Método de pago
                    <select name="metodo_pago" value={formOperacion.metodo_pago}
                      onChange={(evento) => setFormOperacion({ ...formOperacion, metodo_pago: evento.target.value })}>
                      <option value="efectivo">Efectivo</option>
                      <option value="transbank_pos">Transbank en sucursal</option>
                      <option value="transferencia">Transferencia</option>
                    </select>
                  </label>
                  <label>Referencia externa (si aplica)
                    <input value={formOperacion.referencia_externa}
                      onChange={(evento) => setFormOperacion({ ...formOperacion, referencia_externa: evento.target.value })} />
                  </label>
                  <button type="button" className="button button-primary" onClick={confirmarPagoPresencial}>
                    Registrar pago
                  </button>
                </div>
              )}
              {reserva.estado === 'CONFIRMADA' && (
                <section className="card">
                  <h4>Entrega de llaves e inspección inicial</h4>
                  <label>Kilometraje
                    <input type="number" min="0" value={formOperacion.kilometraje}
                      onChange={(evento) => setFormOperacion({ ...formOperacion, kilometraje: evento.target.value })} />
                  </label>
                  <label>Combustible
                    <input value={formOperacion.nivel_combustible}
                      onChange={(evento) => setFormOperacion({ ...formOperacion, nivel_combustible: evento.target.value })} />
                  </label>
                  {[
                    ['codigo_orden_verificado', 'Orden de compra verificada'],
                    ['identidad_verificada', 'Identidad del cliente verificada'],
                    ['licencia_verificada', 'Licencia de conducir vigente'],
                    ['garantia_verificada', 'Garantía revisada'],
                  ].map(([campo, etiqueta]) => (
                    <label className="check-row" key={campo}>
                      <input type="checkbox" checked={verificaciones[campo]}
                        onChange={(evento) => setVerificaciones({
                          ...verificaciones, [campo]: evento.target.checked,
                        })} />
                      {etiqueta}
                    </label>
                  ))}
                  <button type="button" className="button button-primary"
                    disabled={Object.values(verificaciones).some((verificado) => !verificado)}
                    onClick={() => cambiarEstadoReserva('EN_CURSO')}>
                    Registrar entrega y entregar llaves
                  </button>
                </section>
              )}
              {reserva.estado === 'EN_CURSO' && (
                <section className="card">
                  <h4>Devolución e inspección</h4>
                  <label>Kilometraje final
                    <input type="number" min="0" value={formOperacion.kilometraje}
                      onChange={(evento) => setFormOperacion({ ...formOperacion, kilometraje: evento.target.value })} />
                  </label>
                  <label>Nivel de combustible
                    <input value={formOperacion.nivel_combustible}
                      onChange={(evento) => setFormOperacion({ ...formOperacion, nivel_combustible: evento.target.value })} />
                  </label>
                  <label className="check-row">
                    <input type="checkbox" checked={formOperacion.requiere_revision}
                      onChange={(evento) => setFormOperacion({ ...formOperacion, requiere_revision: evento.target.checked })} />
                    Enviar vehículo a revisión/mantención
                  </label>
                  <button type="button" className="button button-primary"
                    onClick={() => cambiarEstadoReserva('COMPLETADA')}>
                    Registrar devolución
                  </button>
                </section>
              )}
              {reserva.estado === 'CONFIRMADA' && (
                <details className="card">
                  <summary>Registrar cancelación presencial</summary>
                  <p>Confirma la identidad del cliente y registra sus datos bancarios cifrados para la revisión.</p>
                  <form onSubmit={solicitarCancelacionEnSucursal} style={estiloFormulario}>
                    <label>Motivo
                      <textarea value={formCancelacionSucursal.motivo}
                        onChange={(evento) => setFormCancelacionSucursal({
                          ...formCancelacionSucursal, motivo: evento.target.value,
                        })} required rows="3" />
                    </label>
                    <label>Banco
                      <input value={formCancelacionSucursal.banco_destino}
                        onChange={(evento) => setFormCancelacionSucursal({
                          ...formCancelacionSucursal, banco_destino: evento.target.value,
                        })} required />
                    </label>
                    <label>Tipo de cuenta
                      <select value={formCancelacionSucursal.tipo_cuenta}
                        onChange={(evento) => setFormCancelacionSucursal({
                          ...formCancelacionSucursal, tipo_cuenta: evento.target.value,
                        })}>
                        <option value="vista">Cuenta vista</option>
                        <option value="corriente">Cuenta corriente</option>
                        <option value="ahorro">Cuenta de ahorro</option>
                      </select>
                    </label>
                    <label>Número de cuenta
                      <input value={formCancelacionSucursal.numero_cuenta}
                        onChange={(evento) => setFormCancelacionSucursal({
                          ...formCancelacionSucursal, numero_cuenta: evento.target.value,
                        })} autoComplete="off" pattern="[A-Za-z0-9]+" required />
                    </label>
                    <label>Documento del titular
                      <select value={formCancelacionSucursal.tipo_documento_titular}
                        onChange={(evento) => setFormCancelacionSucursal({
                          ...formCancelacionSucursal,
                          tipo_documento_titular: evento.target.value,
                        })} required>
                        <option value="RUT">RUT chileno</option>
                        <option value="PASAPORTE">Pasaporte</option>
                      </select>
                    </label>
                    <label>{formCancelacionSucursal.tipo_documento_titular === 'PASAPORTE'
                      ? 'Número de pasaporte'
                      : 'RUT del titular'}
                      <input value={formCancelacionSucursal.rut_titular}
                        onChange={(evento) => setFormCancelacionSucursal({
                          ...formCancelacionSucursal, rut_titular: evento.target.value,
                        })} maxLength={30} autoComplete="off" required />
                    </label>
                    <label>Nombre del titular
                      <input value={formCancelacionSucursal.nombre_titular}
                        onChange={(evento) => setFormCancelacionSucursal({
                          ...formCancelacionSucursal, nombre_titular: evento.target.value,
                        })} required />
                    </label>
                    <button className="button button-primary" type="submit">
                      Crear solicitud de cancelación
                    </button>
                  </form>
                </details>
              )}
            </div>
          )}
        </section>
      )}

      {pestana === 'modificar' && (
        <section className="card panel-section">
          <div className="panel-section-heading">
            <div>
              <p className="eyebrow">GESTIÓN DE RESERVAS</p>
              <h2>Modificar reserva</h2>
              <p>Busca una reserva para ajustar sus fechas y horarios antes del pago.</p>
            </div>
          </div>
          <form onSubmit={buscar} className="inline-form panel-search-form">
            <label htmlFor="reserva-modificar-busqueda">Código, documento o patente</label>
            <div>
              <input
                id="reserva-modificar-busqueda"
                value={termino}
                onChange={(evento) => setTermino(evento.target.value)}
                placeholder="Ej.: RC-000001"
                required
              />
              <button type="submit" className="button button-primary">Buscar reserva</button>
            </div>
          </form>
          {reservas.length > 1 && (
            <div className="panel-search-results" aria-label="Resultados de búsqueda">
              {reservas.map((item) => (
                <button key={item.id} type="button" onClick={() => actualizarReserva(item.id)}>
                  <span>{item.codigo}</span>
                  <span>{ESTADOS[item.estado] || item.estado}</span>
                  <span>{item.cliente?.nombre} {item.cliente?.apellido}</span>
                </button>
              ))}
            </div>
          )}
          {reserva && (
            <article className="panel-reservation-card">
              <header className="panel-reservation-heading">
                <div>
                  <p className="eyebrow">RESERVA SELECCIONADA</p>
                  <h3>{reserva.codigo}</h3>
                </div>
                <span className={`panel-status panel-status-${reserva.estado.toLowerCase()}`}>
                  {ESTADOS[reserva.estado] || reserva.estado}
                </span>
              </header>
              <div className="panel-reservation-details">
                <div>
                  <span>Cliente</span>
                  <strong>{reserva.cliente?.nombre} {reserva.cliente?.apellido}</strong>
                </div>
                <div>
                  <span>Vehículo</span>
                  <strong>{reserva.modelo?.marca} {reserva.modelo?.nombre_modelo} · {reserva.vehiculo?.patente}</strong>
                </div>
                <div>
                  <span>Retiro actual</span>
                  <strong>{reserva.fecha_hora_retiro}</strong>
                </div>
                <div>
                  <span>Devolución actual</span>
                  <strong>{reserva.fecha_hora_devolucion}</strong>
                </div>
              </div>
              {reserva.estado === 'PENDIENTE_PAGO' ? (
                <section className="panel-edit-area">
                  <div>
                    <h3>Nuevo horario</h3>
                    <p>El sistema comprobará disponibilidad y recalculará la orden. Guarda el cambio solo con la aceptación del cliente.</p>
                  </div>
                  {!edicionReserva ? (
                    <button type="button" className="button button-primary" onClick={comenzarEdicionReserva}>
                      Editar fechas y horarios
                    </button>
                  ) : (
                    <form onSubmit={guardarEdicionReserva} className="form-grid panel-date-form">
                      <label>Retiro
                        <input type="datetime-local" value={edicionReserva.retiro}
                          onChange={(evento) => setEdicionReserva({
                            ...edicionReserva, retiro: evento.target.value,
                          })} required />
                      </label>
                      <label>Devolución
                        <input type="datetime-local" value={edicionReserva.devolucion}
                          onChange={(evento) => setEdicionReserva({
                            ...edicionReserva, devolucion: evento.target.value,
                          })} required />
                      </label>
                      <label className="check-row panel-acceptance">
                        <input type="checkbox" checked={edicionReserva.aceptado}
                          onChange={(evento) => setEdicionReserva({
                            ...edicionReserva, aceptado: evento.target.checked,
                          })} />
                        Confirmo que el cliente acepta las nuevas fechas y el monto recalculado.
                      </label>
                      <div className="panel-form-actions">
                        <button type="submit" className="button button-primary"
                          disabled={!edicionReserva.aceptado}>
                          Guardar cambios
                        </button>
                        <button type="button" className="button button-outline"
                          onClick={() => setEdicionReserva(null)}>
                          Cancelar
                        </button>
                      </div>
                    </form>
                  )}
                </section>
              ) : (
                <p className="panel-readonly-note">
                  Esta reserva no se puede modificar: las fechas solo se editan antes del pago.
                </p>
              )}
            </article>
          )}
        </section>
      )}

      {pestana === 'nueva' && (
        <section className="card">
          <h2>Crear reserva presencial</h2>
          <form onSubmit={crearReservaPresencial} style={estiloFormulario}>
            <label>Tipo de documento
              <select name="tipo_documento" value={formCliente.tipo_documento} onChange={cambiarCliente}>
                <option value="RUT">RUT</option>
                <option value="PASAPORTE">Pasaporte</option>
              </select>
            </label>
            {[
              ['numero_documento', 'Número de documento'],
              ['nombre', 'Nombre'],
              ['apellido', 'Apellido'],
              ['correo', 'Correo'],
              ['telefono', 'Teléfono'],
              ['licencia', 'Número de licencia'],
            ].map(([name, label]) => (
              <label key={name}>{label}
                <input name={name} value={formCliente[name]} onChange={cambiarCliente} required />
              </label>
            ))}
            <label>Fecha de nacimiento
              <input type="date" name="fecha_nacimiento" value={formCliente.fecha_nacimiento}
                onChange={cambiarCliente} required />
            </label>
            <label>Vencimiento de licencia
              <input type="date" name="licencia_vencimiento" value={formCliente.licencia_vencimiento}
                onChange={cambiarCliente} required />
            </label>
            <label>Modelo
              <select name="modelo_id" value={formReserva.modelo_id} onChange={cambiarReserva} required>
                <option value="">Selecciona un modelo</option>
                {modelos.map((modelo) => (
                  <option key={modelo.id} value={modelo.id}>
                    {modelo.marca} {modelo.nombre_modelo} · ${modelo.precio_diario}/día
                  </option>
                ))}
              </select>
            </label>
            <label>Retiro
              <input type="date" name="fecha_inicio" value={formReserva.fecha_inicio}
                onChange={cambiarReserva} required />
              <input type="time" name="hora_inicio" min="09:00" max="18:00"
                value={formReserva.hora_inicio} onChange={cambiarReserva} required />
            </label>
            <label>Devolución
              <input type="date" name="fecha_fin" value={formReserva.fecha_fin}
                onChange={cambiarReserva} required />
              <input type="time" name="hora_fin" min="09:00" max="18:00"
                value={formReserva.hora_fin} onChange={cambiarReserva} required />
            </label>
            <label className="check-row">
              <input type="checkbox" name="acepto" checked={formReserva.acepto} onChange={cambiarReserva} />
              El cliente leyó y aceptó el contrato y consentimiento en sucursal.
            </label>
            <button type="submit" className="button button-primary">Crear orden pendiente</button>
          </form>
          {reserva?.estado === 'PENDIENTE_PAGO' && (
            <button type="button" className="button button-secondary" onClick={confirmarPagoPresencial}>
              Registrar pago presencial
            </button>
          )}
        </section>
      )}

      {pestana === 'cancelaciones' && (
        <section className="card">
          <h2>Solicitudes de cancelación</h2>
          <button type="button" className="button button-secondary" onClick={cargarCancelaciones}>Actualizar</button>
          {cancelaciones.map((item) => (
            <article key={item.id} className="card">
              <h3>{item.codigo} · {item.estado}</h3>
              <p>Motivo: {item.motivo}</p>
              <p>Pagado: ${item.monto_pagado}</p>
              {item.monto_solicitado === null ? (
                <p>Monto final pendiente de cálculo por Finanzas.</p>
              ) : (
                <p>Retenido: ${item.monto_retenido} · Devolución registrada: ${item.monto_solicitado}</p>
              )}
              {item.estado === 'DERIVADA_FINANZAS' ? (
                <>
                  <button type="button" onClick={() => cargarDatosFinanzas(item.id)}>
                    Ver datos bancarios
                  </button>
                  <label>Monto transferido por Finanzas
                    <input type="number" min="1" step="1"
                      value={montosReembolso[item.id] || ''}
                      onChange={(evento) => setMontosReembolso({
                        ...montosReembolso, [item.id]: evento.target.value,
                      })} required />
                  </label>
                  <label>Código/referencia de la transferencia
                    <input value={referencias[item.id] || ''}
                      onChange={(evento) => setReferencias({ ...referencias, [item.id]: evento.target.value })}
                      placeholder="Identificador informado por Finanzas" required />
                  </label>
                  <label>Comprobante de transferencia (PDF, PNG o JPEG; máximo 8 MB)
                    <input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                      onChange={(evento) => setComprobantesReembolso({
                        ...comprobantesReembolso, [item.id]: evento.target.files?.[0] || null,
                      })} required />
                  </label>
                  <button type="button" className="button button-primary"
                    onClick={() => registrarDevolucionExterna(item.id)}>
                    Registrar transferencia y cerrar
                  </button>
                  <button type="button" className="button button-outline"
                    onClick={() => operarCancelacion(item.id, 'cerrar_sin_reembolso')}>
                    Cerrar sin devolución
                  </button>
                </>
              ) : ['PENDIENTE', 'EN_REVISION', 'APROBADA'].includes(item.estado) ? (
                <>
                  <button type="button" className="button button-outline"
                    onClick={() => cargarEstimacionCancelacion(item)}>
                    Ver estimación de referencia
                  </button>
                  {estimacionesCancelacion[item.id] && (
                    <p>
                      Referencia estimada: ${estimacionesCancelacion[item.id].monto_devolucion}.
                      El monto final lo define Finanzas.
                    </p>
                  )}
                  <button type="button" className="button button-primary"
                    onClick={() => operarCancelacion(item.id, 'derivar_finanzas')}>
                    Validar y derivar a Finanzas
                  </button>
                  <button type="button" onClick={() => operarCancelacion(
                    item.id,
                    'rechazar',
                    { motivo_rechazo: 'Solicitud rechazada por el asistente.' },
                  )}>
                    Rechazar solicitud
                  </button>
                </>
              ) : (
                <>
                  {item.codigo_comprobante && (
                    <p>Código del comprobante: {item.codigo_comprobante}</p>
                  )}
                  {item.comprobante_disponible && (
                    <button type="button" onClick={() => descargarComprobanteReembolso(
                      item.id, item.codigo,
                    )}>
                      Descargar comprobante
                    </button>
                  )}
                </>
              )}
            </article>
          ))}
          {datosFinanzas && (
            <section className="card" role="dialog" aria-modal="true">
              <h3>Datos de la devolución · uso interno</h3>
              <p>{datosFinanzas.nombre_titular} · {datosFinanzas.tipo_documento_titular || 'RUT'} {datosFinanzas.rut_titular}</p>
              <p>{datosFinanzas.banco_destino} · {datosFinanzas.tipo_cuenta}</p>
              <p>Cuenta: {datosFinanzas.numero_cuenta}</p>
              <p>Finanzas define el monto final al registrar la transferencia.</p>
              <button type="button" onClick={() => setDatosFinanzas(null)}>Cerrar</button>
            </section>
          )}
        </section>
      )}

      {pestana === 'clientes' && esAdmin && (
        <section className="card">
          <h2>Clientes</h2>
          <p>La edición de datos personales está reservada a administradores.</p>
          <button type="button" className="button button-secondary" onClick={cargarClientes}>
            Actualizar clientes
          </button>
          {clientes.map((cliente) => (
            <article key={cliente.id} className="card admin-record">
              <strong>{cliente.nombre} {cliente.apellido}</strong>
              <p>{cliente.correo} · {cliente.telefono || 'Sin teléfono'}</p>
              <p>Estado: {cliente.activo ? 'Activo' : 'Desactivado'}</p>
              <button type="button" className="button button-outline"
                onClick={() => setClienteEditando({ ...cliente })}>
                Editar cliente
              </button>
            </article>
          ))}
          {clienteEditando && (
            <form onSubmit={guardarCliente} className="form-grid admin-edit-form">
              <h3>Editar datos del cliente</h3>
              <label>Nombre
                <input value={clienteEditando.nombre}
                  onChange={(evento) => setClienteEditando({
                    ...clienteEditando, nombre: evento.target.value,
                  })} required />
              </label>
              <label>Apellido
                <input value={clienteEditando.apellido}
                  onChange={(evento) => setClienteEditando({
                    ...clienteEditando, apellido: evento.target.value,
                  })} required />
              </label>
              <label>Correo
                <input type="email" value={clienteEditando.correo}
                  onChange={(evento) => setClienteEditando({
                    ...clienteEditando, correo: evento.target.value,
                  })} required />
              </label>
              <label>Teléfono
                <input value={clienteEditando.telefono || ''}
                  onChange={(evento) => setClienteEditando({
                    ...clienteEditando, telefono: evento.target.value,
                  })} />
              </label>
              <label className="check-row">
                <input type="checkbox" checked={clienteEditando.activo}
                  onChange={(evento) => setClienteEditando({
                    ...clienteEditando, activo: evento.target.checked,
                  })} />
                Cuenta activa
              </label>
              <button type="submit" className="button button-primary">Guardar cliente</button>
              <button type="button" className="button button-outline"
                onClick={() => setClienteEditando(null)}>Cancelar</button>
            </form>
          )}
        </section>
      )}

      {pestana === 'productos' && esAdmin && (
        <section className="card">
          <h2>Productos adicionales</h2>
          <p>Los cambios afectan nuevas reservas; el precio contratado queda guardado en cada reserva.</p>
          <button type="button" className="button button-secondary" onClick={cargarProductos}>
            Actualizar productos
          </button>
          {productos.map((producto) => (
            <article key={producto.id} className="card admin-record">
              <strong>{producto.nombre}</strong>
              <p>{producto.tipo} · ${producto.precio_diario}/día · {producto.activo ? 'Activo' : 'Inactivo'}</p>
              <button type="button" className="button button-outline" onClick={() => {
                setProductoEditando(producto.id)
                setFormProducto({
                  nombre: producto.nombre,
                  tipo: producto.tipo,
                  descripcion: producto.descripcion || '',
                  precio_diario: producto.precio_diario,
                  activo: producto.activo,
                })
              }}>
                Editar producto
              </button>
            </article>
          ))}
          <form onSubmit={guardarProducto} className="form-grid admin-edit-form">
            <h3>{productoEditando ? 'Editar producto' : 'Agregar producto'}</h3>
            <label>Nombre
              <input value={formProducto.nombre}
                onChange={(evento) => setFormProducto({
                  ...formProducto, nombre: evento.target.value,
                })} required />
            </label>
            <label>Tipo
              <input value={formProducto.tipo}
                onChange={(evento) => setFormProducto({
                  ...formProducto, tipo: evento.target.value,
                })} required />
            </label>
            <label>Precio diario
              <input type="number" min="0" step="1" value={formProducto.precio_diario}
                onChange={(evento) => setFormProducto({
                  ...formProducto, precio_diario: evento.target.value,
                })} required />
            </label>
            <label>Descripción
              <textarea value={formProducto.descripcion}
                onChange={(evento) => setFormProducto({
                  ...formProducto, descripcion: evento.target.value,
                })} rows="3" />
            </label>
            <label className="check-row">
              <input type="checkbox" checked={formProducto.activo}
                onChange={(evento) => setFormProducto({
                  ...formProducto, activo: evento.target.checked,
                })} />
              Producto activo
            </label>
            <button type="submit" className="button button-primary">
              {productoEditando ? 'Guardar producto' : 'Agregar producto'}
            </button>
            {productoEditando && (
              <button type="button" className="button button-outline" onClick={() => {
                setProductoEditando(null)
                setFormProducto(productoInicial)
              }}>
                Cancelar edición
              </button>
            )}
          </form>
        </section>
      )}

      {pestana === 'vehiculos' && (
        <section className="card">
          <h2>Administrar flota</h2>
          <button type="button" className="button button-secondary" onClick={cargarVehiculos}>Actualizar</button>
          {vehiculos.map((vehiculo) => (
            <article key={vehiculo.id} className="card">
              <strong>{vehiculo.patente}</strong> · {vehiculo.modelo?.marca} {vehiculo.modelo?.nombre_modelo}
              <p>Estado: {vehiculo.estado} · Km: {vehiculo.kilometraje}</p>
              <button type="button" className="button button-outline" onClick={() => {
                setVehiculoEditando(vehiculo.id)
                setFormVehiculo({
                  patente: vehiculo.patente,
                  anio: String(vehiculo.anio),
                  color: vehiculo.color || '',
                  kilometraje: String(vehiculo.kilometraje),
                  modelo_id: String(vehiculo.modelo.id),
                  sucursal_id: String(vehiculo.sucursal_id_actual),
                  estado_operativo: estadoVehiculoCodigo[vehiculo.estado] || 'ACTIVO',
                  observaciones: vehiculo.observaciones || '',
                })
              }}>
                Editar vehículo
              </button>
            </article>
          ))}
          <form onSubmit={guardarVehiculo} className="form-grid admin-edit-form">
            <h3>{vehiculoEditando ? 'Editar vehículo' : 'Agregar vehículo'}</h3>
            <label>Patente
              <input value={formVehiculo.patente}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, patente: evento.target.value,
                })} required />
            </label>
            <label>Año
              <input type="number" min="1950" max="2100" value={formVehiculo.anio}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, anio: evento.target.value,
                })} required />
            </label>
            <label>Color
              <input value={formVehiculo.color}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, color: evento.target.value,
                })} />
            </label>
            <label>Kilometraje
              <input type="number" min="0" value={formVehiculo.kilometraje}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, kilometraje: evento.target.value,
                })} required />
            </label>
            <label>Modelo
              <select value={formVehiculo.modelo_id}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, modelo_id: evento.target.value,
                })} required>
                <option value="">Selecciona un modelo</option>
                {modelos.map((modelo) => (
                  <option key={modelo.id} value={modelo.id}>
                    {modelo.marca} {modelo.nombre_modelo}
                  </option>
                ))}
              </select>
            </label>
            <label>Sucursal
              <select value={formVehiculo.sucursal_id}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, sucursal_id: evento.target.value,
                })} required>
                <option value="">Selecciona una sucursal</option>
                {sucursales.map((sucursal) => (
                  <option key={sucursal.id} value={sucursal.id}>{sucursal.nombre}</option>
                ))}
              </select>
            </label>
            <label>Estado operativo
              <select value={formVehiculo.estado_operativo}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, estado_operativo: evento.target.value,
                })}>
                {[
                  ['ACTIVO', 'Disponible'],
                  ['EN_ARRENDAMIENTO', 'En arriendo'],
                  ['LIMPIEZA', 'Limpieza'],
                  ['MANTENCION', 'Mantención'],
                  ['FUERA_SERVICIO', 'Fuera de servicio'],
                  ['BAJA', 'Baja'],
                ].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>Observaciones
              <textarea value={formVehiculo.observaciones}
                onChange={(evento) => setFormVehiculo({
                  ...formVehiculo, observaciones: evento.target.value,
                })} rows="3" />
            </label>
            <button type="submit" className="button button-primary">
              {vehiculoEditando ? 'Guardar vehículo' : 'Agregar vehículo'}
            </button>
            {vehiculoEditando && (
              <button type="button" className="button button-outline" onClick={() => {
                setVehiculoEditando(null)
                setFormVehiculo(vehiculoInicial)
              }}>
                Cancelar edición
              </button>
            )}
          </form>
        </section>
      )}
    </main>
  )
}

export default Panel
