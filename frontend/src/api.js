import axios from 'axios'
import { leerSesion } from './auth'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'
// Instancia con la sesión (token) adjunta a cada petición.
const api = axios.create({ baseURL: API_BASE })

export function apiError(error, fallback = 'No fue posible completar la solicitud.') {
  const data = error?.response?.data
  if (typeof data?.detail === 'string') return data.detail
  if (typeof data?.error === 'string') return data.error
  if (data && typeof data === 'object') {
    const firstError = Object.values(data).flat().find((value) => typeof value === 'string')
    if (firstError) return firstError
  }
  if (error?.code === 'ECONNABORTED') return 'El servidor tardó demasiado en responder. Intenta nuevamente.'
  if (error?.response?.status >= 500) return 'El servidor encontró un problema. Intenta nuevamente.'
  if (error?.response) return fallback
  if (error?.request) return 'No hay conexión con el servidor. Revisa que el backend esté iniciado.'
  return fallback
}

export function toList(data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.results)) return data.results
  return []
}

api.interceptors.request.use((configuracion) => {
  const sesion = leerSesion()
  if (sesion?.token) {
    configuracion.headers.Authorization = `Token ${sesion.token}`
  }
  return configuracion
})

export default api
