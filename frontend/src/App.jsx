import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ProveedorSesion, useSesion } from './sesion'
import Cancelacion from './pages/Cancelacion'
import Checkout from './pages/Checkout'
import Flota from './pages/Flota'
import Home from './pages/Home'
import Informacion from './pages/Informacion'
import Login from './pages/Login'
import Panel from './pages/Panel'
import ResultadoPago from './pages/ResultadoPago'
import ResultadoReserva from './pages/ResultadoReserva'

function Navegacion() {
  const location = useLocation()
  const navigate = useNavigate()
  const { sesion, cerrar } = useSesion()
  const checkoutPath = location.pathname === '/checkout'
  const identidad = sesion?.cliente
    ? `${sesion.cliente.nombre} ${sesion.cliente.apellido}`.trim()
    : sesion?.usuario?.nombre || sesion?.nombre || ''

  return (
    <header className="site-header">
      <Link className="brand" to="/" aria-label="Rentacar, ir al inicio">
        <span className="brand-mark">R</span>
        <span>rentacar<span className="brand-period">.</span></span>
      </Link>
      <nav className="main-nav" aria-label="Navegación principal">
        <Link className={location.pathname === '/' ? 'active' : ''} to="/">Inicio</Link>
        <Link className={location.pathname === '/flota' ? 'active' : ''} to="/flota">Reservar</Link>
        <Link className={location.pathname === '/cancelacion' ? 'active' : ''} to="/cancelacion">Cancelar reserva</Link>
        <Link to="/informacion/quienes">Quiénes somos</Link>
        <Link to="/informacion/sucursal">Sucursales</Link>
        {sesion?.tipo === 'trabajador' && <Link to="/panel">Panel</Link>}
        {!checkoutPath && <Link className="header-action" to="/flota">Encuentra tu auto <span aria-hidden="true">↗</span></Link>}
        {sesion
          ? <>
              <span className="nav-identity" title={identidad}>Hola, {identidad}</span>
              <button
                type="button"
                className="nav-button nav-logout"
                onClick={() => {
                  cerrar()
                  navigate('/')
                }}
              >
                SALIR
              </button>
            </>
          : <Link className={`login-nav-link ${location.pathname === '/login' ? 'active' : ''}`} to="/login">Iniciar sesión</Link>}
      </nav>
    </header>
  )
}

function Contenido() {
  return (
    <div className="site-shell">
      <Navegacion />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/flota" element={<Flota />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/cancelacion" element={<Cancelacion />} />
        <Route path="/resultado-pago" element={<ResultadoPago />} />
        <Route path="/reserva-generada" element={<ResultadoReserva />} />
        <Route path="/login" element={<Login />} />
        <Route path="/panel" element={<Panel />} />
        <Route path="/informacion/:tipo" element={<Informacion />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <footer className="site-footer">
        <Link className="brand footer-brand" to="/">
          <span className="brand-mark">R</span>
          <span>rentacar<span className="brand-period">.</span></span>
        </Link>
        <span>Tu próximo viaje comienza aquí.</span>
        <Link to="/informacion/privacidad">Privacidad y condiciones</Link>
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ProveedorSesion>
        <Contenido />
      </ProveedorSesion>
    </BrowserRouter>
  )
}
