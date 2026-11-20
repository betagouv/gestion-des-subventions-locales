import { Controller } from 'stimulus'

export class FormatMontant extends Controller {
  static targets = ['field']
  static values = {
    suffix: { type: String, default: '' },
    minimumFractionDigits: { type: Number, default: 2 }
  }

  connect () {
    this._format(this.fieldTarget)
  }

  format (event) {
    this._format(event.target)
  }

  _format (field) {
    const n = parseFloat(
      field.value.replace(',', '.').replace(/\s/g, '').replace('€', '')
    )
    if (!isNaN(n)) {
      field.value = n.toLocaleString('fr-FR', {
        minimumFractionDigits: this.minimumFractionDigitsValue,
        maximumFractionDigits: 2
      }) + this.suffixValue
    }
  }
}
