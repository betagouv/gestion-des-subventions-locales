import { Controller } from 'stimulus'

export class FormUtils extends Controller {
  static targets = ['form', 'container']

  submitFormAndDisableButton (evt) {
    const btn = evt.target
    btn.classList.add('fr-icon-loader')
    btn.classList.add('fr-icon-spin')
    btn.setAttribute('disabled', '1')
    btn.setAttribute('data-action', 'form-utils#enableButton')
    if (this.formTarget) this.formTarget.submit()
  }

  disableButtons () {
    if (!this.containerTarget) return
    const buttons = this.containerTarget.querySelectorAll('button')
    buttons.forEach(btn => {
      btn.setAttribute('disabled', '1')
    })
  }

  enableButton (evt) { // not used for now
    const btn = evt.target
    btn.classList.remove('fr-icon-loader', 'fr-icon-spin')
    btn.removeAttribute('disabled')
    btn.setAttribute('data-action', 'form-utils#submitFormAndDisableButton')
  }
}
