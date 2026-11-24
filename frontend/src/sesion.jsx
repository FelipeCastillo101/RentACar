import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { borrarSesion, guardarSesion, leerSesion } from './auth'

const SesionContext = createContext(null)

export function ProveedorSesion({ children }) {
  const [sesion, setSesion] = useState(() => leerSesion())

  const iniciar = (datos) => {
    guardarSesion(datos)
    setSesion(datos)
  }

  const cerrar = () => {
    borrarSesion()
    setSesion(null)
  }

  useEffect(() => {
    if (!sesion) return undefined
    const restante = Number(sesion.expires_at) - Date.now()
    const timer = window.setTimeout(cerrar, Math.max(0, restante))
    return () => window.clearTimeout(timer)
  }, [sesion])

  useEffect(() => {
    const sincronizarSesion = (evento) => {
      if (evento.key === 'rentcar_sesion') setSesion(leerSesion())
    }
    window.addEventListener('storage', sincronizarSesion)
    return () => window.removeEventListener('storage', sincronizarSesion)
  }, [])

  const valor = useMemo(() => ({ sesion, iniciar, cerrar }), [sesion])
  return <SesionContext.Provider value={valor}>{children}</SesionContext.Provider>
}

export function useSesion() {
  return useContext(SesionContext)
}
