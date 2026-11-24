import { useEffect, useRef, useState } from 'react'

function GoogleCredentialButton({ onCredential, disabled = false }) {
  const container = useRef(null)
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
  const [mensaje, setMensaje] = useState(
    () => clientId ? '' : 'Falta configurar VITE_GOOGLE_CLIENT_ID para habilitar Google.',
  )

  useEffect(() => {
    if (!clientId) return undefined

    let intentos = 0
    const timer = window.setInterval(() => {
      const google = window.google
      if (!google?.accounts?.id || !container.current) {
        intentos += 1
        if (intentos >= 100) {
          window.clearInterval(timer)
          setMensaje('No se pudo cargar el servicio de inicio de sesión de Google.')
        }
        return
      }

      window.clearInterval(timer)
      google.accounts.id.initialize({
        client_id: clientId,
        callback: (respuesta) => {
          if (!disabled && respuesta.credential) onCredential(respuesta.credential)
        },
      })
      google.accounts.id.renderButton(container.current, {
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        width: 320,
      })
    }, 100)

    return () => window.clearInterval(timer)
  }, [clientId, disabled, onCredential])

  return (
    <div>
      <div ref={container} aria-disabled={disabled} />
      {mensaje && <p role="status">{mensaje}</p>}
    </div>
  )
}

export default GoogleCredentialButton
