import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import api, { apiError, toList } from '../api'
import { useSesion } from '../sesion'

const pesos = (monto) => new Intl.NumberFormat('es-CL', {
  style: 'currency',
  currency: 'CLP',
  maximumFractionDigits: 0,
}).format(Number(monto) || 0)

const diasEntre = (inicio, fin, horaInicio, horaFin) => {
  if (!inicio || !fin) return 1
  const retiro = new Date(`${inicio}T${horaInicio || '09:00'}:00`)
  const devolucion = new Date(`${fin}T${horaFin || '18:00'}:00`)
  return Math.max(1, Math.ceil((devolucion - retiro) / 86400000))
}

const datosIniciales = {
  nombre: '',
  apellido: '',
  correo: '',
  telefono: '',
  tipo_documento: 'RUT',
  numero_documento: '',
  fecha_nacimiento: '',
  licencia: '',
  licencia_vencimiento: '',
}

function Checkout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { sesion } = useSesion()
  const { autoSeleccionado, fechaInicio, fechaFin, horaInicio = '09:00', horaFin = '18:00' } = location.state || {}
  const [paso, setPaso] = useState(1)
  const [seguros, setSeguros] = useState([])
  const [productos, setProductos] = useState([])
  const [catalogosCargando, setCatalogosCargando] = useState(true)
  const [errorCatalogo, setErrorCatalogo] = useState('')
  const [segurosElegidos, setSegurosElegidos] = useState([])
  const [productosElegidos, setProductosElegidos] = useState([])
  const [tipoDocumentoSolicitado, setTipoDocumentoSolicitado] = useState('BOLETA')
  const [facturacion, setFacturacion] = useState({
    rut_receptor: '',
    razon_social: '',
    giro: '',
    direccion: '',
    comuna: '',
    correo: '',
  })
  const [cliente, setCliente] = useState(() => ({
    ...datosIniciales,
    nombre: sesion?.cliente?.nombre || '',
    apellido: sesion?.cliente?.apellido || '',
    correo: sesion?.cliente?.correo || '',
    telefono: sesion?.cliente?.telefono || '',
    fecha_nacimiento: sesion?.cliente?.fecha_nacimiento || '',
  }))
  const [contratoAceptado, setContratoAceptado] = useState(false)
  const [politicaCancelacionAceptada, setPoliticaCancelacionAceptada] = useState(false)
  const [datosDeclarados, setDatosDeclarados] = useState(false)
  const [mostrarContrato, setMostrarContrato] = useState(false)
  const [procesando, setProcesando] = useState(false)
  const [error, setError] = useState('')
  const [reservaCreada, setReservaCreada] = useState(null)
  const [tokenPagoInvitado, setTokenPagoInvitado] = useState('')

  useEffect(() => {
    if (!autoSeleccionado) {
      navigate('/flota', { replace: true })
      return
    }
    if (sesion?.tipo === 'trabajador') {
      navigate('/panel', { replace: true })
      return
    }
    if (sesion?.tipo !== 'cliente') {
      navigate('/login', {
        replace: true,
        state: {
          redirectTo: '/checkout',
          reservationState: location.state,
        },
      })
      return
    }

    let activa = true
    Promise.all([
      api.get('/api/seguros/'),
      api.get('/api/productos/'),
    ])
      .then(([segurosResponse, productosResponse]) => {
        if (!activa) return
        setSeguros(toList(segurosResponse.data).filter((opcion) => opcion.activo !== false))
        setProductos(toList(productosResponse.data).filter((opcion) => opcion.activo !== false))
      })
      .catch((requestError) => {
        if (activa) setErrorCatalogo(apiError(requestError, 'No se pudieron cargar los seguros y adicionales.'))
      })
      .finally(() => {
        if (activa) setCatalogosCargando(false)
      })
    return () => { activa = false }
  }, [autoSeleccionado, location.state, navigate, sesion])

  const dias = useMemo(
    () => diasEntre(fechaInicio, fechaFin, horaInicio, horaFin),
    [fechaInicio, fechaFin, horaInicio, horaFin],
  )

  const precioBase = Number(autoSeleccionado?.precio_diario) || 0
  const subtotalSeguros = seguros
    .filter((seguro) => segurosElegidos.includes(String(seguro.id)))
    .reduce((total, seguro) => total + (Number(seguro.precio_diario) || 0) * dias, 0)
  const subtotalProductos = productos
    .filter((producto) => productosElegidos.includes(String(producto.id)))
    .reduce((total, producto) => total + (Number(producto.precio_diario) || 0) * dias, 0)
  const totalEstimado = precioBase * dias + subtotalSeguros + subtotalProductos

  const cambiarCliente = (event) => {
    const { name, value } = event.target
    setCliente((actual) => ({ ...actual, [name]: value }))
  }

  const cambiarFacturacion = (event) => {
    const { name, value } = event.target
    setFacturacion((actual) => ({ ...actual, [name]: value }))
  }

  const alternar = (seleccionados, setSeleccionados, id) => {
    const valor = String(id)
    setSeleccionados(seleccionados.includes(valor)
      ? seleccionados.filter((seleccionado) => seleccionado !== valor)
      : [...seleccionados, valor])
  }

  const validarDatos = () => {
    const hoy = new Date()
    const nacimiento = cliente.fecha_nacimiento ? new Date(`${cliente.fecha_nacimiento}T00:00:00`) : null
    const minimoNacimiento = new Date(hoy.getFullYear() - 18, hoy.getMonth(), hoy.getDate())
    if (!nacimiento || nacimiento > minimoNacimiento) return 'El arrendatario debe tener al menos 18 años.'
    if (!cliente.licencia_vencimiento || new Date(`${cliente.licencia_vencimiento}T00:00:00`) <= hoy) {
      return 'La licencia de conducir debe estar vigente.'
    }
    if (tipoDocumentoSolicitado === 'FACTURA') {
      const requeridos = ['rut_receptor', 'razon_social', 'giro', 'direccion', 'comuna', 'correo']
      if (requeridos.some((campo) => !facturacion[campo].trim())) {
        return 'Completa todos los datos de facturación para solicitar factura.'
      }
    }
    return ''
  }

  const irAWebpay = async (reserva, tokenInvitado) => {
    if (tokenInvitado) {
      sessionStorage.setItem('rentcar-payment-access', tokenInvitado)
    }
    const { data: pago } = await api.post('/api/crear-pago/', {
      reserva_id: reserva.id,
      ...(tokenInvitado ? { payment_access_token: tokenInvitado } : {}),
    })
    const formulario = document.createElement('form')
    formulario.method = 'POST'
    formulario.action = pago.url
    formulario.style.display = 'none'
    const campoToken = document.createElement('input')
    campoToken.type = 'hidden'
    campoToken.name = 'token_ws'
    campoToken.value = pago.token
    formulario.appendChild(campoToken)
    document.body.appendChild(formulario)
    formulario.submit()
  }

  const confirmarReserva = async (event) => {
    event.preventDefault()
    setError('')
    if (!contratoAceptado || !politicaCancelacionAceptada || !datosDeclarados) {
      setError('Debes aceptar el contrato, la política de cancelación y declarar que tus datos son reales.')
      return
    }
    const validacion = validarDatos()
    if (validacion) {
      setError(validacion)
      setPaso(2)
      return
    }
    if (catalogosCargando || errorCatalogo) {
      setError('No es posible continuar hasta cargar correctamente el catálogo de seguros y adicionales.')
      setPaso(1)
      return
    }

    setProcesando(true)
    try {
      if (reservaCreada) {
        await irAWebpay(reservaCreada, tokenPagoInvitado)
        return
      }
      const payloadReserva = {
        modelo_id: autoSeleccionado.id,
        fecha_hora_retiro: `${fechaInicio}T${horaInicio}:00`,
        fecha_hora_devolucion: `${fechaFin}T${horaFin}:00`,
        canal: 'WEB',
        seguros: segurosElegidos.map(Number),
        productos: productosElegidos.map((id) => ({ id: Number(id), cantidad: 1 })),
        tipo_documento_solicitado: tipoDocumentoSolicitado,
        ...(tipoDocumentoSolicitado === 'FACTURA' ? { datos_facturacion: facturacion } : {}),
        tipo_documento: cliente.tipo_documento,
        numero_documento: cliente.numero_documento.trim(),
        licencia: cliente.licencia.trim(),
        licencia_vencimiento: cliente.licencia_vencimiento,
        fecha_nacimiento: cliente.fecha_nacimiento,
        nombre: cliente.nombre.trim(),
        apellido: cliente.apellido.trim(),
        correo: cliente.correo.trim(),
        telefono: cliente.telefono.trim(),
        firma_condiciones: true,
      }
      const reservaResponse = await api.post('/api/reservas/', payloadReserva)
      if (!reservaResponse.data?.id) throw new Error('El servidor no devolvió el identificador de la reserva.')
      const reserva = reservaResponse.data
      const tokenInvitado = reserva.payment_access_token || ''
      setReservaCreada(reserva)
      setTokenPagoInvitado(tokenInvitado)
      await irAWebpay(reserva, tokenInvitado)
    } catch (requestError) {
      setError(apiError(
        requestError,
        reservaCreada
          ? 'La reserva quedó guardada, pero no se pudo abrir Webpay. Puedes reintentar el pago.'
          : requestError.message || 'No se pudo generar la reserva.',
      ))
      setProcesando(false)
    }
  }

  if (!autoSeleccionado) return null

  return (
    <div className="checkout-page section-wrap">
      <div className="checkout-heading">
        <Link className="back-link" to="/flota" state={{ fechaInicio, fechaFin }}>← Volver a los vehículos</Link>
        <p className="eyebrow">CASI LISTO PARA VIAJAR</p>
        <h1>Completa tu reserva.</h1>
      </div>

      <div className="checkout-progress" aria-label={`Paso ${paso} de 3`}>
        {[
          ['1', 'Opcionales'],
          ['2', 'Tus datos'],
          ['3', 'Confirmar reserva'],
        ].map(([numero, titulo]) => (
          <div className={`progress-step ${paso >= Number(numero) ? 'current' : ''}`} key={numero}>
            <span>{numero}</span><strong>{titulo}</strong>
          </div>
        ))}
      </div>

      <div className="checkout-layout">
        <section className="checkout-main">
          {paso === 1 && (
            <div className="checkout-panel">
              <p className="eyebrow">PASO 1 · PERSONALIZA TU VIAJE</p>
              <h2>¿Quieres sumar algo más?</h2>
              <p className="panel-intro">Selecciona los seguros y accesorios que quieras agregar. El precio se calculará para tus días de arriendo.</p>

              {catalogosCargando && <div className="notice notice-loading" role="status">Cargando opciones disponibles…</div>}
              {errorCatalogo && (
                <div className="notice notice-error" role="alert">
                  {errorCatalogo}
                  <button className="text-button" type="button" onClick={() => window.location.reload()}>Volver a cargar</button>
                </div>
              )}
              {!catalogosCargando && !errorCatalogo && seguros.length === 0 && productos.length === 0 && (
                <div className="notice">No hay seguros ni accesorios disponibles. Puedes continuar sin adicionales.</div>
              )}

              {seguros.length > 0 && (
                <div className="option-group">
                  <div className="option-heading"><h3>Seguros</h3><span>Opcional</span></div>
                  <div className="option-list">
                    {seguros.map((seguro) => {
                      const checked = segurosElegidos.includes(String(seguro.id))
                      return (
                        <label className={`option-card ${checked ? 'option-selected' : ''}`} key={seguro.id}>
                          <input type="checkbox" checked={checked} onChange={() => alternar(segurosElegidos, setSegurosElegidos, seguro.id)} />
                          <span className="custom-check" aria-hidden="true">✓</span>
                          <span className="option-content">
                            <strong>{seguro.nombre}</strong>
                            <span>{seguro.descripcion || 'Protección adicional para tu viaje.'}</span>
                            {seguro.deducible_monto != null && <small>Deducible: {pesos(seguro.deducible_monto)}</small>}
                          </span>
                          <span className="option-price">{pesos(seguro.precio_diario)}<small> / día</small></span>
                        </label>
                      )
                    })}
                  </div>
                </div>
              )}

              {productos.length > 0 && (
                <div className="option-group">
                  <div className="option-heading"><h3>Accesorios y adicionales</h3><span>Opcional</span></div>
                  <div className="option-list">
                    {productos.map((producto) => {
                      const checked = productosElegidos.includes(String(producto.id))
                      return (
                        <label className={`option-card ${checked ? 'option-selected' : ''}`} key={producto.id}>
                          <input type="checkbox" checked={checked} onChange={() => alternar(productosElegidos, setProductosElegidos, producto.id)} />
                          <span className="custom-check" aria-hidden="true">✓</span>
                          <span className="option-content">
                            <strong>{producto.nombre}</strong>
                            <span>{producto.descripcion || producto.tipo || 'Adicional para tu reserva.'}</span>
                          </span>
                          <span className="option-price">{pesos(producto.precio_diario)}<small> / día</small></span>
                        </label>
                      )
                    })}
                  </div>
                </div>
              )}
              <div className="checkout-step-actions">
                <span>Podrás revisar el total antes de confirmar la reserva.</span>
                <button className="button button-dark" type="button" disabled={catalogosCargando || Boolean(errorCatalogo)} onClick={() => setPaso(2)}>Continuar <span aria-hidden="true">→</span></button>
              </div>
            </div>
          )}

          {paso === 2 && (
            <div className="checkout-panel">
              <p className="eyebrow">PASO 2 · DATOS DEL ARRENDATARIO</p>
              <h2>Cuéntanos quién conduce.</h2>
              <p className="panel-intro">Ingresa los datos reales del conductor principal. Los revisaremos al momento de retirar el vehículo.</p>
              <form className="checkout-form" onSubmit={(event) => {
                event.preventDefault()
                const validacion = validarDatos()
                if (validacion) setError(validacion)
                else {
                  setError('')
                  setPaso(3)
                }
              }}>
                <div className="form-grid">
                  <label className="field"><span>Nombre</span><input autoComplete="given-name" name="nombre" value={cliente.nombre} readOnly required /></label>
                  <label className="field"><span>Apellido</span><input autoComplete="family-name" name="apellido" value={cliente.apellido} readOnly required /></label>
                  <label className="field"><span>Correo electrónico</span><input autoComplete="email" type="email" name="correo" value={cliente.correo} readOnly required /></label>
                  <label className="field"><span>Teléfono</span><input autoComplete="tel" type="tel" name="telefono" value={cliente.telefono} onChange={cambiarCliente} required /></label>
                  <label className="field">
                    <span>Tipo de documento</span>
                    <select name="tipo_documento" value={cliente.tipo_documento} onChange={cambiarCliente}>
                      <option value="RUT">RUT</option>
                      <option value="PASAPORTE">Pasaporte</option>
                    </select>
                  </label>
                  <label className="field"><span>{cliente.tipo_documento === 'RUT' ? 'RUT' : 'Número de pasaporte'}</span><input autoComplete="off" name="numero_documento" value={cliente.numero_documento} onChange={cambiarCliente} required /></label>
                  <label className="field"><span>Fecha de nacimiento</span><input type="date" name="fecha_nacimiento" max={new Date(new Date().setFullYear(new Date().getFullYear() - 18)).toISOString().slice(0, 10)} value={cliente.fecha_nacimiento} onChange={cambiarCliente} required /></label>
                  <label className="field"><span>Numero de licencia</span><input name="licencia" value={cliente.licencia} onChange={cambiarCliente} required /></label>
                  <label className="field"><span>Vencimiento de licencia</span><input type="date" name="licencia_vencimiento" value={cliente.licencia_vencimiento} onChange={cambiarCliente} required /></label>
                </div>

                <div className="document-choice">
                  <p className="eyebrow">DOCUMENTO DE COMPRA</p>
                  <h3>¿Necesitas boleta o factura?</h3>
                  <div className="choice-row">
                    {[
                      ['BOLETA', 'Boleta', 'Para una compra personal.'],
                      ['FACTURA', 'Factura', 'Para una empresa o contribuyente.'],
                    ].map(([value, title, caption]) => (
                      <label className={`choice-card ${tipoDocumentoSolicitado === value ? 'choice-selected' : ''}`} key={value}>
                        <input type="radio" name="tipo_documento_solicitado" value={value} checked={tipoDocumentoSolicitado === value} onChange={() => setTipoDocumentoSolicitado(value)} />
                        <span><strong>{title}</strong><small>{caption}</small></span>
                      </label>
                    ))}
                  </div>
                  {tipoDocumentoSolicitado === 'FACTURA' && (
                    <div className="form-grid invoice-grid">
                      <label className="field"><span>RUT receptor</span><input name="rut_receptor" value={facturacion.rut_receptor} onChange={cambiarFacturacion} required /></label>
                      <label className="field"><span>Razón social</span><input name="razon_social" value={facturacion.razon_social} onChange={cambiarFacturacion} required /></label>
                      <label className="field"><span>Giro</span><input name="giro" value={facturacion.giro} onChange={cambiarFacturacion} required /></label>
                      <label className="field"><span>Correo de facturación</span><input type="email" name="correo" value={facturacion.correo} onChange={cambiarFacturacion} required /></label>
                      <label className="field"><span>Dirección</span><input name="direccion" value={facturacion.direccion} onChange={cambiarFacturacion} required /></label>
                      <label className="field"><span>Comuna</span><input name="comuna" value={facturacion.comuna} onChange={cambiarFacturacion} required /></label>
                    </div>
                  )}
                  <p className="field-note">La boleta o factura no se emite en este paso. No ingreses datos de tarjetas en este formulario.</p>
                </div>
                <div className="checkout-step-actions">
                  <button className="button button-outline" type="button" onClick={() => setPaso(1)}>← Opcionales</button>
                  <button className="button button-dark" type="submit">Revisar contrato <span aria-hidden="true">→</span></button>
                </div>
              </form>
            </div>
          )}

          {paso === 3 && (
            <div className="checkout-panel">
              <p className="eyebrow">PASO 3 · REVISA Y CONFIRMA</p>
              <h2>Un último paso antes de salir.</h2>
              <p className="panel-intro">Lee las condiciones y confirma que la información entregada es correcta.</p>
              <button className="contract-preview-button" type="button" onClick={() => setMostrarContrato(true)}>
                <span className="contract-icon" aria-hidden="true">▤</span>
                <span><strong>Contrato de arriendo</strong><small>Revisar condiciones del servicio</small></span>
                <span aria-hidden="true">↗</span>
              </button>
              <label className="consent-row">
                <input type="checkbox" checked={contratoAceptado} onChange={(event) => setContratoAceptado(event.target.checked)} />
                <span>He leído y acepto el contrato y las condiciones del arriendo.</span>
              </label>
              <label className="consent-row">
                <input type="checkbox" checked={datosDeclarados} onChange={(event) => setDatosDeclarados(event.target.checked)} />
                <span>Confirmo que mis datos son reales, completos y corresponden al conductor que retirará el vehículo.</span>
              </label>
              <div className="notice">
                <strong>Política de cancelación y devolución</strong>
                <p>
                  El retracto solicitado dentro de 10 días desde la reserva y antes de iniciar el servicio
                  se cotiza con devolución total. En otros casos: más de 48 horas, devolución total; entre
                  24 y 48 horas, retención de un día de tarifa; con menos de 24 horas, dos días; si el cliente no se presenta,
                  tres días. La retención no supera el monto pagado. Las solicitudes se revisan y las
                  devoluciones aprobadas se ejecutan por transferencia.
                </p>
                <small>Este criterio debe validarse con asesoría legal antes de operar comercialmente.</small>
              </div>
              <label className="consent-row">
                <input type="checkbox" checked={politicaCancelacionAceptada}
                  onChange={(event) => setPoliticaCancelacionAceptada(event.target.checked)} />
                <span>Leí y acepto la política de cancelación y devolución informada.</span>
              </label>
              <div className="payment-note">
                <span className="payment-shield" aria-hidden="true">✓</span>
                <p>Se abrirá Webpay en su entorno académico para completar el pago. No ingreses datos de tarjeta en este sitio.</p>
              </div>
              <div className="checkout-step-actions">
                <button className="button button-outline" type="button" onClick={() => setPaso(2)}>← Tus datos</button>
                <button className="button button-dark" type="button" disabled={procesando} onClick={confirmarReserva}>
                  {procesando ? 'Abriendo Webpay…' : reservaCreada ? 'Reintentar pago en Webpay' : 'Reservar y pagar con Webpay'} <span aria-hidden="true">→</span>
                </button>
              </div>
            </div>
          )}

          {error && <div className="notice notice-error" role="alert">{error}</div>}
        </section>

        <aside className="reservation-summary">
          <p className="eyebrow">RESUMEN DE TU VIAJE</p>
          <div className="summary-car">
            {autoSeleccionado.imagen || autoSeleccionado.imagen_url
              ? <img src={autoSeleccionado.imagen || autoSeleccionado.imagen_url} alt="" />
              : <div className="vehicle-placeholder"><span>RENTACAR</span></div>}
            <div>
              <span>{autoSeleccionado.categoria_nombre || autoSeleccionado.categoria?.nombre || 'Vehículo'}</span>
              <strong>{autoSeleccionado.marca} {autoSeleccionado.nombre_modelo || autoSeleccionado.modelo}</strong>
            </div>
          </div>
          <div className="summary-dates">
            <div><span>Retiro</span><strong>{fechaInicio} · {horaInicio}</strong></div>
            <div><span>Devolución</span><strong>{fechaFin} · {horaFin}</strong></div>
            <div><span>Duración</span><strong>{dias} {dias === 1 ? 'día' : 'días'}</strong></div>
          </div>
          <div className="summary-costs">
            <div><span>Arriendo · {dias} días</span><strong>{pesos(precioBase * dias)}</strong></div>
            {subtotalSeguros > 0 && <div><span>Seguros seleccionados</span><strong>{pesos(subtotalSeguros)}</strong></div>}
            {subtotalProductos > 0 && <div><span>Accesorios seleccionados</span><strong>{pesos(subtotalProductos)}</strong></div>}
          </div>
          <div className="summary-total"><span>Total estimado</span><strong>{pesos(totalEstimado)}</strong></div>
          <p className="summary-disclaimer">El total definitivo lo calcula el servidor y queda registrado con la reserva.</p>
          <div className="summary-guarantee">
            <span aria-hidden="true">ⓘ</span>
            <p>Garantía a presentar en sucursal: <strong>{pesos(autoSeleccionado.garantia_monto)}</strong></p>
          </div>
        </aside>
      </div>

      {mostrarContrato && (
        <div className="modal-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setMostrarContrato(false)
        }}>
          <section className="contract-modal" role="dialog" aria-modal="true" aria-labelledby="contract-title">
            <button className="icon-button modal-close" type="button" onClick={() => setMostrarContrato(false)} aria-label="Cerrar contrato">×</button>
            <p className="eyebrow">VERSIÓN VIGENTE</p>
            <h2 id="contract-title">Contrato y condiciones de arriendo</h2>
            <div className="contract-copy">
              <p>Al confirmar, el cliente solicita el arriendo del vehículo seleccionado para las fechas y sucursales informadas. El precio y los adicionales quedan registrados en la orden de compra.</p>
              <p>El conductor declara tener al menos 18 años y contar con una licencia vigente. Al retirar el vehículo deberá presentar su documento de identidad, licencia y los medios de garantía solicitados por la sucursal.</p>
              <p>El cliente se compromete a utilizar y devolver el vehículo en las condiciones acordadas. Los daños, multas, combustible y demás hallazgos se revisan al momento de la devolución conforme a las condiciones del servicio.</p>
              <p>Este paso solo registra la reserva pendiente. No realiza cobros ni solicita datos de tarjeta. Las solicitudes sin pago expiran automáticamente a los 15 minutos.</p>
              <p>La política de cancelación y devolución se muestra antes del pago y forma parte de las condiciones aceptadas.</p>
              <p>El cliente autoriza el tratamiento de los datos ingresados para administrar esta solicitud de reserva y las comunicaciones relacionadas.</p>
            </div>
            <button className="button button-dark" type="button" onClick={() => {
              setMostrarContrato(false)
              setContratoAceptado(true)
            }}>Volver y aceptar condiciones</button>
          </section>
        </div>
      )}
    </div>
  )
}

export default Checkout
