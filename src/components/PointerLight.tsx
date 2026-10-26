import { useEffect, useRef } from 'react'

interface Props { enabled: boolean }

// Browser-only interaction primitive: no React renders or native APIs in the pointer loop.
export function PointerLight({ enabled }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const light = ref.current
    if (!light) return
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)')
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const contrast = window.matchMedia('(forced-colors: active)')
    let eligible = false
    let frame = 0
    let previousTime = 0
    let x = 0
    let y = 0
    let targetX = 0
    let targetY = 0
    let visible = false
    let pressed = false
    let interactive = false
    let surface: HTMLElement | null = null
    let bounds: DOMRect | null = null

    const clearSurface = () => {
      if (surface) {
        delete surface.dataset.lit
        surface.style.removeProperty('--spot-x')
        surface.style.removeProperty('--spot-y')
      }
      surface = null
      bounds = null
    }
    const hideVisual = () => {
      visible = false
      light.dataset.visible = 'false'
      cancelAnimationFrame(frame)
      frame = 0
      previousTime = 0
      clearSurface()
    }
    const hide = () => { pressed = false; light.dataset.pressed = 'false'; hideVisual() }
    const configure = () => {
      eligible = enabled && fine.matches && !reduced.matches && !contrast.matches
      if (eligible) document.documentElement.dataset.pointerEnhanced = 'true'
      else { delete document.documentElement.dataset.pointerEnhanced; hide() }
    }
    const paint = (time: number) => {
      if (!eligible || !visible) { frame = 0; return }
      const elapsed = previousTime ? Math.min(time - previousTime, 32) : 16
      previousTime = time
      const ease = 1 - Math.exp(-elapsed / 44)
      x += (targetX - x) * ease
      y += (targetY - y) * ease
      light.style.transform = 'translate3d(' + x + 'px,' + y + 'px,0)'
      if (surface && bounds) {
        surface.style.setProperty('--spot-x', (x - bounds.left) + 'px')
        surface.style.setProperty('--spot-y', (y - bounds.top) + 'px')
      }
      if (Math.abs(targetX - x) + Math.abs(targetY - y) > 0.1) frame = requestAnimationFrame(paint)
      else { frame = 0; previousTime = 0 }
    }
    const move = (event: PointerEvent) => {
      if (!eligible || !event.isPrimary || event.pointerType === 'touch') { hide(); return }
      const target = event.target instanceof Element ? event.target : null
      if (!target?.closest('.app-shell')) { hide(); return }
      interactive = !!target.closest('button,a[href],input,label,summary,[role="button"]')
      light.dataset.interactive = String(interactive)
      // Let text selection proceed with an unobstructed native I-beam.
      if (pressed && !interactive) { hideVisual(); return }
      targetX = event.clientX
      targetY = event.clientY
      if (!visible) { x = targetX; y = targetY }
      visible = true
      light.dataset.visible = 'true'
      const nextSurface = target.closest<HTMLElement>('[data-spotlight]')
      if (nextSurface !== surface) {
        clearSurface()
        surface = nextSurface
        // Read geometry once on entry, never in the animation loop.
        if (surface) { bounds = surface.getBoundingClientRect(); surface.dataset.lit = 'true' }
      }
      if (!frame) frame = requestAnimationFrame(paint)
    }
    const down = (event: PointerEvent) => {
      if (!eligible || event.pointerType === 'touch' || event.button !== 0) return
      pressed = true
      light.dataset.pressed = 'true'
    }
    const up = () => { pressed = false; light.dataset.pressed = 'false' }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) hide() }
    const keyboard = (event: KeyboardEvent) => { if (event.key === 'Tab') hide() }

    configure()
    fine.addEventListener('change', configure)
    reduced.addEventListener('change', configure)
    contrast.addEventListener('change', configure)
    document.addEventListener('pointermove', move, { passive: true })
    document.addEventListener('pointerdown', down, { passive: true })
    document.addEventListener('pointerup', up, { passive: true })
    document.addEventListener('pointercancel', hide)
    document.addEventListener('pointerout', leave, { passive: true })
    document.addEventListener('keydown', keyboard)
    document.addEventListener('scroll', hide, { passive: true, capture: true })
    window.addEventListener('blur', hide)
    window.addEventListener('resize', hide)
    return () => {
      hide()
      delete document.documentElement.dataset.pointerEnhanced
      fine.removeEventListener('change', configure)
      reduced.removeEventListener('change', configure)
      contrast.removeEventListener('change', configure)
      document.removeEventListener('pointermove', move)
      document.removeEventListener('pointerdown', down)
      document.removeEventListener('pointerup', up)
      document.removeEventListener('pointercancel', hide)
      document.removeEventListener('pointerout', leave)
      document.removeEventListener('keydown', keyboard)
      document.removeEventListener('scroll', hide, true)
      window.removeEventListener('blur', hide)
      window.removeEventListener('resize', hide)
    }
  }, [enabled])

  return <div ref={ref} className="pointer-light" aria-hidden="true" data-visible="false">
    <span className="pointer-aura" /><span className="pointer-ring" />
  </div>
}
