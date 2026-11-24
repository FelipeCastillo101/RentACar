import { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../api'
import GoogleCredentialButton from '../components/GoogleCredentialButton'
import { useSesion } from '../sesion'

function Registro() {
  const { iniciar } = useSesion()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  const registrarseConGoogle = useCallback(async (credential) => {
    setError('')
    try {
      const respuesta = await api.post('/api/auth/google/', { credential })
      const cliente = respuesta.data.cliente
      iniciar({
        token: respuesta.data.token,
        expires_at: Date.now() + (Number(respuesta.data.expires_in) || 3600) * 1000,
        tipo: 'cliente',
        rol: null,
        nombre: `${cliente.nombre} ${cliente.apellido}`,
        cliente,
      })
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo crear la cuenta con Google.')
    }
  }, [iniciar, navigate])

  return (
    <section style={{ maxWidth: '480px', margin: '0 auto' }}>
      <h1>Crear cuenta de cliente</h1>
      <p>
        La cuenta se crea con Google. Tus datos de identidad y licencia se solicitan
        únicamente al completar una reserva.
      </p>
      <GoogleCredentialButton onCredential={registrarseConGoogle} />
      {error && <p role="alert" style={{ color: '#c00' }}>{error}</p>}
      <p style={{ marginTop: '16px' }}>
        ¿Ya tienes cuenta? <Link to="/login">Ingresar</Link>
      </p>
    </section>
  )
}

export default Registro
