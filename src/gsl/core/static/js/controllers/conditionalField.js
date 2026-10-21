import { Controller } from 'stimulus'

// Declared on a checkbox: shows/hides the dependent field whose id is given by
// `data-conditional-field-for`, depending on whether the checkbox is checked.
export class ConditionalField extends Controller {
  connect () {
    this._apply()
  }

  toggle () {
    this._apply()
  }

  _apply () {
    const field = document.getElementById(this.element.dataset.conditionalFieldFor)
    const group = field && field.closest('.fr-input-group')
    if (group) group.classList.toggle('fr-hidden', !this.element.checked)
  }
}
