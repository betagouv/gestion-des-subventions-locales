import { Controller } from 'stimulus'

export class FormatMontant extends Controller {
  static targets = ['field']

  connect () {
    this._format(this.fieldTarget)
  }

  format (event) {
    this._format(event.target)
  }

  _format (field) {
    const n = parseFloat(field.value.replace(',', '.').replace(/\s/g, ''))
    if (!isNaN(n)) {
      field.value = n.toLocaleString('fr-FR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      })
    }
  }
}
