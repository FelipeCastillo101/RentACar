const LLAVE = 'rentcar_sesion'

export function leerSesion() {
  try {
    const crudo = localStorage.getItem(LLAVE)
    const sesion = crudo ? JSON.parse(crudo) : null
    if (
      !sesion?.token
      || !Number.isFinite(Number(sesion.expires_at))
      || Number(sesion.expires_at) <= Date.now()
    ) {
      localStorage.removeItem(LLAVE)
      return null
    }
    return sesion
  } catch {
    localStorage.removeItem(LLAVE)
    return null
  }
}

export function guardarSesion(datos) {
  localStorage.setItem(LLAVE, JSON.stringify(datos))
}

export function borrarSesion() {
  localStorage.removeItem(LLAVE)
}
