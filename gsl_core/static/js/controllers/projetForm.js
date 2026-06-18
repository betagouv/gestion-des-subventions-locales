import { Controller } from 'stimulus'

export class ProjetForm extends Controller {
  static targets = [
    'contratLocalCheckbox',
    'contratLocalWrapper',
    'autreZonageLocalCheckbox',
    'autreZonageLocalWrapper'
  ]

  connect () {
    if (this.hasContratLocalCheckboxTarget && this.hasContratLocalWrapperTarget) {
      this._toggle(this.contratLocalWrapperTarget, this.contratLocalCheckboxTarget.checked)
    }
    if (this.hasAutreZonageLocalCheckboxTarget && this.hasAutreZonageLocalWrapperTarget) {
      this._toggle(this.autreZonageLocalWrapperTarget, this.autreZonageLocalCheckboxTarget.checked)
    }
  }

  enableSubmit (evt) {
    const button = evt.currentTarget.querySelector("button[type='submit']")
    if (button) button.disabled = false
  }

  submitOnChange (evt) {
    const formId = evt.target.getAttribute('form')
    const form = formId ? document.getElementById(formId) : evt.target.closest('form')
    if (form) form.submit()
  }

  toggleContratLocal (evt) {
    this._toggle(this.contratLocalWrapperTarget, evt.target.checked)
  }

  toggleAutreZonageLocal (evt) {
    this._toggle(this.autreZonageLocalWrapperTarget, evt.target.checked)
  }

  _toggle (wrapper, show) {
    wrapper.classList.toggle('fr-hidden', !show)
  }
}
