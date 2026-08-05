import { Controller } from 'stimulus'

export class FormUtils extends Controller {
  static targets = ['container']

  disableButtons (evt) {
    const container = this.hasContainerTarget ? this.containerTarget : evt.target
    const buttons = container.querySelectorAll('button')
    buttons.forEach(btn => {
      if (btn.type === 'submit') {
        this._disableButtonAndAddALoader(btn)
      } else {
        btn.setAttribute('disabled', '1')
      }
    })
  }

  // Generic action for a link that downloads a file: spins + disables the
  // link for the duration of the fetch, so the user gets feedback while the
  // file is being generated server-side, then triggers the actual download.
  downloadAndSpin (evt) {
    evt.preventDefault()
    const link = evt.currentTarget

    if (link.classList.contains('fr-icon-spin')) {
      return
    }

    this._disableButtonAndAddALoader(link)

    fetch(link.href)
      .then(response => {
        if (!response.ok) {
          throw new Error('download-failed')
        }
        return response.blob()
      })
      .then(blob => {
        const url = window.URL.createObjectURL(blob)
        const tempLink = document.createElement('a')
        tempLink.href = url
        tempLink.download = link.dataset.filename || ''
        document.body.appendChild(tempLink)
        tempLink.click()
        tempLink.remove()
        window.URL.revokeObjectURL(url)
      })
      .catch(() => {
        window.location.href = link.href
      })
      .finally(() => {
        this._enableButtonAndRemoveLoader(link)
      })
  }

  _disableButtonAndAddALoader (el) {
    el.classList.add('fr-icon-loader')
    el.classList.add('fr-icon-spin')
    if (el.tagName === 'A') {
      el.setAttribute('aria-disabled', 'true')
    } else {
      el.setAttribute('disabled', '1')
    }
  }

  _enableButtonAndRemoveLoader (el) {
    el.classList.remove('fr-icon-loader')
    el.classList.remove('fr-icon-spin')
    if (el.tagName === 'A') {
      el.removeAttribute('aria-disabled')
    } else {
      el.removeAttribute('disabled')
    }
  }
}
