import { Controller } from 'stimulus'

export class FormUtils extends Controller {
  static targets = ['container']

  disableButtons (evt) {
    const container = this.hasContainerTarget ? this.containerTarget : evt.target
    this._disableAllButtons(container)
  }

  async download (evt) {
    evt.preventDefault()
    const url = evt.currentTarget.getAttribute('href')
    const container = this.hasContainerTarget ? this.containerTarget : evt.currentTarget
    this._disableAllButtons(container)

    try {
      const response = await fetch(url)
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)

      const filename = this._extractFilename(response)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(blobUrl)
    } finally {
      this._enableAllButtons(container)
    }
  }

  _disableAllButtons (container) {
    container.querySelectorAll('button').forEach(btn => {
      if (btn.type === 'submit') {
        this._disableButtonAndAddALoader(btn)
      } else {
        btn.setAttribute('disabled', '1')
      }
    })
    container.querySelectorAll('a.fr-btn').forEach(link => {
      link.dataset.formUtilsHref = link.getAttribute('href')
      link.removeAttribute('href')
      link.setAttribute('aria-disabled', 'true')
      link.classList.add('fr-icon-loader', 'fr-icon-spin')
    })
  }

  _enableAllButtons (container) {
    container.querySelectorAll('button[disabled]').forEach(btn => {
      btn.removeAttribute('disabled')
      btn.classList.remove('fr-icon-loader', 'fr-icon-spin')
    })
    container.querySelectorAll('a.fr-btn[aria-disabled]').forEach(link => {
      if (link.dataset.formUtilsHref) {
        link.setAttribute('href', link.dataset.formUtilsHref)
        delete link.dataset.formUtilsHref
      }
      link.removeAttribute('aria-disabled')
      link.classList.remove('fr-icon-loader', 'fr-icon-spin')
    })
  }

  _disableButtonAndAddALoader (btn) {
    btn.classList.add('fr-icon-loader')
    btn.classList.add('fr-icon-spin')
    btn.setAttribute('disabled', '1')
  }

  _extractFilename (response) {
    const disposition = response.headers.get('Content-Disposition')
    if (disposition) {
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (match) return match[1].replace(/['"]/g, '')
    }
    return 'download'
  }
}
