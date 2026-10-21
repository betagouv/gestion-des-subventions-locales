import { Controller } from 'stimulus'

export class ModeleArreteForm extends Controller {
  static targets = ['form']

  confirmaCancel () {
    window.addEventListener('beforeunload', e => {
      e.preventDefault()
      e.returnValue = ''
    })
  }

  removeRequiredWhenGoingAtPreviousStep () {
    this.formTarget.querySelectorAll('[required]').forEach(function (element) {
      element.required = false
    })
  }
}
