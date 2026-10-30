import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { MonitorPanel } from './components/MonitorPanel'
import { initializeTheme } from './hooks/useTheme'
import './styles.css'

initializeTheme()
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{new URLSearchParams(window.location.search).get('panel')==='monitor' ? <MonitorPanel/> : <App />}</React.StrictMode>,
)
