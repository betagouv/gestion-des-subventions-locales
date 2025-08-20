import { Controller } from 'stimulus'

export class CheckboxSelection extends Controller {
  static values = {
    allCheckboxesSelected: { type: Boolean, default: false }
  }

  static targets = ['globalButton', 'button', 'link']

  connect () {
    this._checkIfAllCheckboxesAreSelected()
    this._updateHref()
  }

  toggle () {
    const newValue = !this.allCheckboxesSelectedValue
    this.allCheckboxesSelectedValue = newValue
    if (newValue) {
      this._updateAllCheckboxes(true)
    } else {
      this._updateAllCheckboxes(false)
    }
    this._updateHref()
  }

  updateAllCheckboxesSelected (evt) {
    const eltValue = evt.target.checked
    if (eltValue === false) {
      this.allCheckboxesSelectedValue = false
    } else {
      this._checkIfAllCheckboxesAreSelected()
    }
    this._updateHref()
  }

  allCheckboxesSelectedValueChanged () {
    this._updateACheckbox(this.globalButtonTarget, this.allCheckboxesSelectedValue)
  }

  // Private

  _updateHref () {
    const selectedIds = this.buttonTargets
      .filter((b) => b.checked)
      .map((b) => b.id.split('-')[1])

    const baseUrl = this.linkTarget.dataset.baseUrl

    if (selectedIds.length > 0) {
      this.linkTarget.href = `${baseUrl}?ids=${selectedIds.join(',')}`
    } else {
      this.linkTarget.removeAttribute('href')
    }
  }

  _updateAllCheckboxes (value) {
    this.buttonTargets.forEach(element => this._updateACheckbox(element, value))
  }

  _updateACheckbox (elt, value) {
    elt.checked = value
    elt.setAttribute('data-fr-js-checkbox-input', value)
  }

  _checkIfAllCheckboxesAreSelected () {
    if (this.buttonTargets.every(b => b.checked)) {
      this.allCheckboxesSelectedValue = true
    }
  }
}
