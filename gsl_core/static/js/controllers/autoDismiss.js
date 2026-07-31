import { Controller } from 'stimulus'

// Removes its element after a short delay. Handy for transient htmx feedback
// (e.g. a success badge) that should not stay on the page.
export class AutoDismiss extends Controller {
  connect () {
    const delay = parseInt(this.element.dataset.autoDismissDelay || '3000', 10)
    this.timeout = setTimeout(() => this.element.remove(), delay)
  }

  disconnect () {
    clearTimeout(this.timeout)
  }
}
