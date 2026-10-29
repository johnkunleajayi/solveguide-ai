/// <reference types="vite/client" />
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrandShowcase } from './BrandShowcase'
import '../../brand/tokens.css'
import './showcase.css'

// Independent dev entry. No App, auth, native bridge, provider or preference imports.
if (import.meta.env.DEV) {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode><BrandShowcase /></React.StrictMode>,
  )
}
