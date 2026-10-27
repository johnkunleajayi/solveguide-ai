import { useEffect, useRef } from 'react'
import { Check, Monitor, Moon, Sun, X } from 'lucide-react'
import type { Theme } from '../hooks/useTheme'
import { AccountPanel } from './AccountPanel'
import { PrivacySettings } from './PrivacySettings'

interface Props {
  open: boolean
  onClose: () => void
  theme: Theme
  setTheme: (theme: Theme) => void
  pointerLight: boolean
  setPointerLight: (enabled: boolean) => void
}

export function SettingsDialog({ open, onClose, theme, setTheme, pointerLight, setPointerLight }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
    const dismissBackdrop = (event: MouseEvent) => {
      if (event.target === dialog) onClose()
    }
    dialog.addEventListener('click', dismissBackdrop)
    return () => dialog.removeEventListener('click', dismissBackdrop)
  }, [open, onClose])

  return (
    <dialog ref={ref} className="settings-dialog" aria-labelledby="settings-title" aria-describedby="settings-description"
      onClose={onClose}>
      <div className="dialog-content">
        <header className="dialog-header">
          <div><span className="eyebrow">YOUR WORKSPACE</span><h2 id="settings-title">Make it yours.</h2></div>
          <button className="icon-button" aria-label="Close settings" onClick={onClose}><X size={19} aria-hidden="true" /></button>
        </header>
        <p id="settings-description" className="muted">A little less distraction. A little more focus.</p>
        <AccountPanel />
        <PrivacySettings active={open} />
        <fieldset className="appearance-fieldset">
          <legend>Appearance</legend>
          <div className="theme-options">
            {([
              { value: 'light', label: 'Light', Icon: Sun },
              { value: 'dark', label: 'Dark', Icon: Moon },
              { value: 'system', label: 'System', Icon: Monitor },
            ] as const).map(({ value, label, Icon }) => (
              <label key={value} className="theme-option" data-selected={theme === value}>
                <input type="radio" name="theme" value={value} checked={theme === value} onChange={() => setTheme(value)} />
                <span className={'theme-preview preview-' + value} aria-hidden="true"><span /><span /><span /></span>
                <span className="theme-option-label"><Icon size={15} aria-hidden="true" />{label}<Check size={13} className="theme-check" aria-hidden="true" /></span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="preference-row">
          <div><label htmlFor="pointer-light">Pointer light</label><p id="pointer-description">A subtle light for precise pointers. Uses your native cursor with reduced motion or touch.</p></div>
          <input id="pointer-light" className="switch" type="checkbox" role="switch" checked={pointerLight}
            onChange={event => setPointerLight(event.target.checked)} aria-describedby="pointer-description" />
        </div>
        <footer className="settings-footer"><span>Preferences stay on this device.</span><span>V0.1.0</span></footer>
      </div>
    </dialog>
  )
}
