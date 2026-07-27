import { Controller } from 'stimulus'

export class ProjetForm extends Controller {
  static targets = [
    'contratLocalCheckbox',
    'contratLocalInput',
    'autreZonageLocalCheckbox',
    'autreZonageLocalInput'
  ]

  connect () {
    if (this.hasContratLocalCheckboxTarget && this.hasContratLocalInputTarget) {
      this._toggle(this.contratLocalInputTarget, this.contratLocalCheckboxTarget.checked)
    }
    if (this.hasAutreZonageLocalCheckboxTarget && this.hasAutreZonageLocalInputTarget) {
      this._toggle(this.autreZonageLocalInputTarget, this.autreZonageLocalCheckboxTarget.checked)
    }
  }

  enableSubmit (evt) {
    const form = evt.target.form
    if (!form) return
    document.querySelectorAll(`button[type='submit'][form='${form.id}']`)
      .forEach(btn => { btn.disabled = false })
  }

  submitOnChange (evt) {
    const formId = evt.target.getAttribute('form')
    const form = formId ? document.getElementById(formId) : evt.target.closest('form')
    if (form) form.submit()
  }

  toggleContratLocal (evt) {
    this._toggle(this.contratLocalInputTarget, evt.target.checked)
  }

  toggleAutreZonageLocal (evt) {
    this._toggle(this.autreZonageLocalInputTarget, evt.target.checked)
  }

  _toggle (input, show) {
    input.closest('.fr-input-group').classList.toggle('fr-hidden', !show)
  }
}
