import { Controller } from 'stimulus'

export class BindAmountFields extends Controller {
  static targets = ['assiette', 'montant', 'taux']
  static values = {
    coutTotal: String
  }

  connect () {
    this.totalEligible = this._getTotalEligible()
    this._formatAllFields()
  }

  // Format handlers
  formatAssiette () {
    this.assietteTarget.value = this._formatMontant(this.assietteTarget.value)
  }

  formatMontant () {
    this.montantTarget.value = this._formatMontant(this.montantTarget.value)
  }

  formatTaux () {
    this.tauxTarget.value = this._formatTaux(this.tauxTarget.value)
  }

  // Input handlers for calculations
  onAssietteInput () {
    const assiette = this._parseValue(this.assietteTarget.value)
    // Update totalEligible when assiette changes
    if (!isNaN(assiette)) {
      this.totalEligible = assiette
    } else {
      this.totalEligible = this._parseValue(this.coutTotalValue)
      this.onMontantInput()
    }
    const montant = this._parseValue(this.montantTarget.value)
    if (!isNaN(assiette) && !isNaN(montant)) {
      const taux = (montant / assiette) * 100
      this.tauxTarget.value = taux.toLocaleString('fr-FR', {
        minimumFractionDigits: 3,
        maximumFractionDigits: 3
      })
    }
  }

  onMontantInput () {
    const montant = this._parseValue(this.montantTarget.value)
    if (!isNaN(montant)) {
      const taux = (montant / this.totalEligible) * 100
      this.tauxTarget.value = taux.toLocaleString('fr-FR', {
        minimumFractionDigits: 3,
        maximumFractionDigits: 3
      })
    }
  }

  onTauxInput () {
    const taux = this._parseValue(this.tauxTarget.value)
    if (!isNaN(taux)) {
      const montant = (taux / 100) * this.totalEligible
      this.montantTarget.value = montant.toLocaleString('fr-FR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      })
    }
  }

  // Form submission handler
  onSubmit (event) {
    // Clean fields before submission
    [this.montantTarget, this.tauxTarget, this.assietteTarget].forEach(
      (input) => {
        if (input && input.value) {
          input.value = input.value.replace(/\s/g, '').replace(',', '.')
        }
      }
    )
  }

  // Private methods
  _parseValue (val) {
    return parseFloat(val.replace(',', '.').replace(/\s/g, ''))
  }

  _formatMontant (val) {
    const n = this._parseValue(val)
    return isNaN(n)
      ? ''
      : n.toLocaleString('fr-FR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      })
  }

  _formatTaux (val) {
    const n = this._parseValue(val)
    return isNaN(n)
      ? ''
      : n.toLocaleString('fr-FR', {
        minimumFractionDigits: 3,
        maximumFractionDigits: 3
      })
  }

  _getTotalEligible () {
    const assietteValue = this.assietteTarget.value
    if (assietteValue) {
      return this._parseValue(assietteValue)
    }
    return this._parseValue(this.coutTotalValue)
  }

  _formatAllFields () {
    this.assietteTarget.value = this._formatMontant(this.assietteTarget.value)
    this.montantTarget.value = this._formatMontant(this.montantTarget.value)
    this.tauxTarget.value = this._formatTaux(this.tauxTarget.value)
  }
}
