import { Controller } from 'stimulus'

// Deals with non-user errors (50x, 40x other than 422, network failure…) and try
// to insert an error near the htmx target, so to stay near the user attention.
export class HtmxError extends Controller {
  connect () {
    document.body.addEventListener('htmx:beforeRequest', this.clear)
    // `htmx:responseError` = non-2xx status ; `htmx:sendError` = network failure.
    document.body.addEventListener('htmx:responseError', this.onResponseError)
    document.body.addEventListener('htmx:sendError', this.onSendError)
  }

  disconnect () {
    document.body.removeEventListener('htmx:beforeRequest', this.clear)
    document.body.removeEventListener('htmx:responseError', this.onResponseError)
    document.body.removeEventListener('htmx:sendError', this.onSendError)
  }

  clear = () => {
    document.querySelectorAll('[data-htmx-error]').forEach((alert) => alert.remove())
  }

  onSendError = (event) => {
    this.alert(event.detail.target, this.build('Connexion indisponible, veuillez réessayer.'))
  }

  onResponseError = (event) => {
    const status = event.detail.xhr.status
    const message = status === 403 ? "Vous n'êtes pas autorisé à effectuer cette action." : 'Une erreur est survenue, veuillez réessayer.'
    this.alert(event.detail.target, this.build(message))
  }

  alert (target, alert) {
    // Try to insert near the htmx context, and fallback to global context.
    if (target && target.isConnected && target !== document.body && target.parentElement) {
      target.insertAdjacentElement('beforebegin', alert)
    } else {
      const messages = document.getElementById('messages')
      ;(messages || document.body).prepend(alert)
    }
  }

  build (message) {
    const alert = document.createElement('div')
    alert.className = 'fr-alert fr-alert--error fr-alert--sm fr-mb-2w'
    alert.setAttribute('role', 'alert')
    alert.dataset.htmxError = ''
    alert.dataset.controller = 'auto-dismiss'
    alert.dataset.autoDismissDelay = '6000'

    const paragraph = document.createElement('p')
    paragraph.textContent = message
    alert.appendChild(paragraph)

    return alert
  }
}
