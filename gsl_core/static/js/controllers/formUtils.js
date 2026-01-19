import { Controller } from 'stimulus'

export class FormUtils extends Controller {
  static targets = ['form']

  disableButton () {
    const btn = this.element.querySelector('button[type="submit"]')
    if (!btn) {
      return
    }

    // Store original icon class if not already stored
    if (!btn.dataset.originalIcon) {
      // Find the icon class (fr-icon-*)
      const iconClass = Array.from(btn.classList).find(
        (cls) => cls.startsWith('fr-icon-') && !cls.includes('refresh')
      )
      if (iconClass) {
        btn.dataset.originalIcon = iconClass
      } else {
        // Default icon if none found
        btn.dataset.originalIcon = 'fr-icon-check-line'
      }
    }

    // Replace icon with spinner (refresh icon)
    if (btn.dataset.originalIcon) {
      btn.classList.remove(btn.dataset.originalIcon)
    }
    btn.classList.add('fr-icon-refresh-line')
    btn.classList.add('fr-icon-spin')
    btn.setAttribute('disabled', '1')
  }

  enableButton (evt) {
    const btn = this.element.querySelector('button[type="submit"]')
    if (!btn) {
      return
    }

    // Restore original icon
    if (btn.dataset.originalIcon) {
      btn.classList.remove('fr-icon-refresh-line', 'fr-icon-spin')
      btn.classList.add(btn.dataset.originalIcon)
    }

    // Re-enable button
    btn.removeAttribute('disabled')
  }
}
