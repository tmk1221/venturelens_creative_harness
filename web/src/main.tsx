import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
// T25: the original post-transcript-first look, ported verbatim (styles.css copied unchanged
// to legacy-look.css). Loaded after index.css so its dark-by-default rules win for the
// transcript/visuals classes; other routes still use their Tailwind classes, which carry
// higher specificity than legacy-look.css's bare-element selectors and so are unaffected.
import './legacy-look.css'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
