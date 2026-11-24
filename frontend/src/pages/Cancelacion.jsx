import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { useSesion } from '../sesion'

const pesos = (monto) => new Intl.NumberFormat('es-CL', {
  style: 'currency',
  currency: 'CLP',
  maximumFractionDigits: 0,
}).format(Number(monto) || 0)

function Cancelacion() {
  const { sesion } = useSesion()
  const [error, setError] = useState('')
  const [enviado, setEnviado] = useState(null)
  const [cotizacion, setCotizacion] = useState(null)
  const [cotizando, setCotizando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [datos, setDatos] = useState({
    codigo: '', motivo: '', banco_destino: '', tipo_cuenta: 'vista',
    numero_cuenta: '', tipo_documento_titular: 'RUT',
    rut_titular: '', nombre_titular: '',
  })

  const cambiar = (evento) => {
    const { name, value } = evento.target
    setDatos((actual) => ({ ...actual, [name]: value }))
    if (name === 'codigo') setCotizacion(null)
  }

  const consultarCotizacion = async () => {
    setError('')
    setCotizacion(null)
    setCotizando(true)
    try {
      const respuesta = await api.get('/api/cancelaciones/cotizacion/', {
        params: { codigo: datos.codigo.trim() },
      })
      setCotizacion(respuesta.data)
    } catch (err) {
      const detalle = err.response?.data
      setError(typeof detalle?.detail === 'string'
        ? detalle.detail
        : Object.values(detalle || {}).flat().join(' ') || 'No se pudo calcular la devolución.')
    } finally {
      setCotizando(false)
    }
  }

  const enviar = async (evento) => {
    evento.preventDefault()
    setError('')
    if (!cotizacion) {
      setError('Primero consulta el monto estimado de devolución.')
      return
    }
    setEnviando(true)
    try {
      const respuesta = await api.post('/api/cancelaciones/', datos)
      setEnviado(respuesta.data)
    } catch (err) {
      const detalle = err.response?.data
      setError(typeof detalle?.detail === 'string'
        ? detalle.detail
        : Object.values(detalle || {}).flat().join(' ') || 'No se pudo enviar la solicitud.')
    } finally {
      setEnviando(false)
    }
  }

  if (!sesion) {
    return (
      <section className="page section-wrap">
        <h1>Cancelación y devolución</h1>
        <p>Inicia sesión con Google para consultar y cancelar una reserva asociada a tu correo.</p>
        <Link className="button button-dark" to="/login" state={{ redirectTo: '/cancelacion' }}>
          Iniciar sesión
        </Link>
      </section>
    )
  }

  if (enviado) {
    return (
      <section className="page section-wrap">
        <h1>{enviado.solicitud_preexistente ? 'Solicitud ya registrada' : 'Solicitud enviada'}</h1>
        <p role="status">
          {enviado.solicitud_preexistente
            ? `Ya existía una solicitud para la reserva ${enviado.codigo}. No se creó otra. Estado: ${enviado.estado}.`
            : `Recibimos tu solicitud para la reserva ${enviado.codigo}. Estado: ${enviado.estado}.`}
        </p>
        <p>
          Monto pagado: {pesos(enviado.monto_pagado)}.
          {!enviado.solicitud_preexistente
            && ' El monto final de devolución queda pendiente de revisión por el asistente y Finanzas.'}
        </p>
        {enviado.aviso && <p role="alert">{enviado.aviso}</p>}
        {!enviado.solicitud_preexistente && (
          <p>El equipo validará el código y los datos. Finanzas definirá y ejecutará la transferencia.</p>
        )}
        <Link to="/">Regresar al menú</Link>
      </section>
    )
  }

  return (
    <main className="page section-wrap">
      <h1>Cancelación y devolución</h1>
      <p>Inicia sesión con Google y verifica que el código de reserva pertenezca a tu cuenta.</p>
      <div className="notice">
        <strong>Política informada antes del pago</strong>
        <p>
          Si solicitas el retracto dentro de los 10 días desde la reserva y antes de iniciar el servicio,
          se cotiza la devolución total. En otros casos: más de 48 horas, devolución total; entre 24 y 48
          horas, se retiene un día de tarifa; con menos de 24 horas, dos días; si el cliente no se presenta, tres días.
          La retención no supera lo pagado. La solicitud queda sujeta a revisión.
        </p>
        <small>Este criterio debe validarse con asesoría legal antes de operar comercialmente.</small>
      </div>
      <form onSubmit={enviar} style={{ display: 'grid', gap: '12px', maxWidth: '620px' }}>
        <label>Código de reserva
          <input name="codigo" value={datos.codigo} onChange={cambiar} required
            placeholder="RC-000001" style={{ display: 'block', width: '100%', padding: '8px' }} />
        </label>
        <button className="button button-outline" type="button" disabled={cotizando || !datos.codigo.trim()}
          onClick={consultarCotizacion}>
          {cotizando ? 'Verificando…' : 'Verificar código y reserva'}
        </button>
        {cotizacion && (
          <div className="card" role="status">
            {cotizacion.solicitud_preexistente ? (
              <>
                <strong>Ya existe una solicitud para la reserva {cotizacion.codigo}.</strong>
                <p>Estado: {cotizacion.estado}. El equipo ya recibió la solicitud; no la envíes nuevamente.</p>
              </>
            ) : (
              <>
                <strong>{cotizacion.vehiculo} · {cotizacion.codigo}</strong>
                <p>Pagado: {pesos(cotizacion.monto_pagado)}</p>
                <p>Retención estimada: {pesos(cotizacion.monto_retenido)}</p>
                <p>Referencia preliminar: {pesos(cotizacion.monto_devolucion)}</p>
                <small>{cotizacion.fundamento} El monto final lo define Finanzas.</small>
              </>
            )}
          </div>
        )}
        {(!cotizacion || !cotizacion.solicitud_preexistente) && (
          <label>Motivo de la solicitud
            <textarea name="motivo" value={datos.motivo} onChange={cambiar} required rows="4"
              style={{ display: 'block', width: '100%' }} />
          </label>
        )}
        {cotizacion && (
          !cotizacion.solicitud_preexistente && (
          <>
            <p>
              Ingresa una cuenta bancaria a tu nombre. El número de cuenta se cifra al guardarlo.
              Si eres extranjero, puedes identificarte con tu pasaporte; Finanzas revisará que
              el titular y los datos de la cuenta coincidan antes de transferir.
            </p>
            <label>Banco destino
              <input name="banco_destino" value={datos.banco_destino} onChange={cambiar} required
                placeholder="Ej: Banco de Chile" style={{ display: 'block', width: '100%', padding: '8px' }} />
            </label>
            <label>Tipo de cuenta
              <select name="tipo_cuenta" value={datos.tipo_cuenta} onChange={cambiar}
                style={{ display: 'block', width: '100%', padding: '8px' }}>
                <option value="vista">Cuenta vista</option>
                <option value="corriente">Cuenta corriente</option>
                <option value="ahorro">Cuenta de ahorro</option>
              </select>
            </label>
            <label>Número de cuenta
              <input name="numero_cuenta" value={datos.numero_cuenta} onChange={cambiar}
                autoComplete="off" inputMode="text" pattern="[A-Za-z0-9]+" required
                style={{ display: 'block', width: '100%', padding: '8px' }} />
            </label>
            <label>Documento del titular
              <select name="tipo_documento_titular" value={datos.tipo_documento_titular}
                onChange={cambiar} required
                style={{ display: 'block', width: '100%', padding: '8px' }}>
                <option value="RUT">RUT chileno</option>
                <option value="PASAPORTE">Pasaporte</option>
              </select>
            </label>
            <label>{datos.tipo_documento_titular === 'PASAPORTE'
              ? 'Número de pasaporte'
              : 'RUT del titular'}
              <input name="rut_titular" value={datos.rut_titular} onChange={cambiar}
                maxLength={30} autoComplete="off" required
                placeholder={datos.tipo_documento_titular === 'PASAPORTE'
                  ? 'Número indicado en el pasaporte'
                  : '12.345.678-9'}
                style={{ display: 'block', width: '100%', padding: '8px' }} />
            </label>
            <label>Nombre del titular
              <input name="nombre_titular" value={datos.nombre_titular} onChange={cambiar} required
                style={{ display: 'block', width: '100%', padding: '8px' }} />
            </label>
          </>
          )
        )}
        {error && <p role="alert" style={{ color: '#c00' }}>{error}</p>}
        {cotizacion && !cotizacion.solicitud_preexistente && (
          <button className="button button-dark" type="submit" disabled={enviando}>
            {enviando ? 'Enviando solicitud…' : 'Enviar solicitud de cancelación'}
          </button>
        )}
      </form>
    </main>
  )
}

export default Cancelacion
