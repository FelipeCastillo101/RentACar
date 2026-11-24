import { useCallback, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import api from '../api'
import { useSesion } from '../sesion'
import GoogleCredentialButton from '../components/GoogleCredentialButton'

function Login() {
  const { iniciar } = useSesion()
  const navigate = useNavigate()
  const location = useLocation()
  const [correo, setCorreo] = useState('')
  const [password, setPassword] = useState('')
  const [codigo, setCodigo] = useState('')
  const [challengeId, setChallengeId] = useState('')
  const [codigoSolicitado, setCodigoSolicitado] = useState(false)
  const [mostrarAccesoPersonal, setMostrarAccesoPersonal] = useState(false)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const guardarSesion = useCallback((datos) => {
    const cliente = datos.cliente || null
    iniciar({
      token: datos.token,
      expires_at: Date.now() + (Number(datos.expires_in) || 3600) * 1000,
      tipo: datos.tipo,
      rol: datos.rol || null,
      nombre: datos.usuario?.nombre
        || (cliente ? `${cliente.nombre} ${cliente.apellido}` : ''),
      cliente,
      usuario: datos.usuario || null,
    })
    const destino = datos.tipo === 'trabajador'
      ? '/panel'
      : location.state?.redirectTo || '/'
    navigate(destino, {
      state: datos.tipo === 'trabajador' ? undefined : location.state?.reservationState,
      replace: true,
    })
  }, [iniciar, location.state, navigate])

  const ingresarTrabajador = async (evento) => {
    evento.preventDefault()
    setCargando(true)
    setError('')
    try {
      const respuesta = await api.post('/api/auth/login/', { correo, password })
      setChallengeId(respuesta.data.challenge_id)
      setCodigoSolicitado(true)
      setPassword('')
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo iniciar sesión.')
    } finally {
      setCargando(false)
    }
  }

  const verificarCodigoTrabajador = async (evento) => {
    evento.preventDefault()
    setCargando(true)
    setError('')
    try {
      const respuesta = await api.post('/api/auth/verify-code/', {
        challenge_id: challengeId,
        code: codigo,
      })
      guardarSesion(respuesta.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo verificar el código.')
    } finally {
      setCargando(false)
    }
  }

  const ingresarConGoogle = useCallback(async (credential) => {
    setCargando(true)
    setError('')
    try {
      const respuesta = await api.post('/api/auth/google/', { credential })
      guardarSesion(respuesta.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo iniciar sesión con Google.')
    } finally {
      setCargando(false)
    }
  }, [guardarSesion])

  return (
    <main className="page login-page">
      <div className="login-columns">
        <section className="card login-card">
          <p className="eyebrow">ACCESO PARA CLIENTES</p>
          <h1>Continúa con Google.</h1>
          <p>Inicia sesión con Google para guardar tus datos y reservar vehículos.</p>
          <GoogleCredentialButton onCredential={ingresarConGoogle} disabled={cargando} />
        </section>

        <section className="card login-card staff-login-card">
          <p className="eyebrow">ACCESO INTERNO</p>
          <h2>Personal de sucursal</h2>
          {!mostrarAccesoPersonal ? (
            <button
              type="button"
              className="button button-outline"
              onClick={() => setMostrarAccesoPersonal(true)}
            >
              Acceso para personal
            </button>
          ) : codigoSolicitado ? (
            <>
              <p>Ingresa el código enviado al correo {correo}.</p>
              <form onSubmit={verificarCodigoTrabajador} className="login-form">
                <label>Código de verificación
                  <input
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    maxLength={6}
                    value={codigo}
                    onChange={(evento) => setCodigo(evento.target.value.replace(/\D/g, ''))}
                    required
                  />
                </label>
                {error && <p role="alert" className="form-error">{error}</p>}
                <button className="button button-primary" type="submit" disabled={cargando}>
                  {cargando ? 'Verificando…' : 'Verificar código'}
                </button>
                <button
                  className="login-text-button"
                  type="button"
                  onClick={() => {
                    setCodigoSolicitado(false)
                    setChallengeId('')
                    setCodigo('')
                    setError('')
                  }}
                >
                  Volver al ingreso
                </button>
              </form>
            </>
          ) : (
            <form onSubmit={ingresarTrabajador} className="login-form">
              <label>Correo
                <input
                  type="email"
                  autoComplete="username"
                  value={correo}
                  onChange={(evento) => setCorreo(evento.target.value)}
                  required
                />
              </label>
              <label>Contraseña
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(evento) => setPassword(evento.target.value)}
                  required
                />
              </label>
              {error && <p role="alert" className="form-error">{error}</p>}
              <button className="button button-primary" type="submit" disabled={cargando}>
                {cargando ? 'Validando…' : 'Continuar'}
              </button>
            </form>
          )}
        </section>
      </div>
    </main>
  )
}

export default Login
