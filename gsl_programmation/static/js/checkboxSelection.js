import { Controller } from 'stimulus'

export class CheckboxSelection extends Controller {
  static values = {
    allCheckboxesSelected: { type: Boolean, default: false }, // todo rename allPageProjetsSelected
    allProjetsSelected: { type: Boolean, default: false },
    toNotifyProjetsCount: Number,
    activateAllProjetsSelection: { type: Boolean, default: false }
  }

  static targets = ['globalButton', 'button', 'link', 'selectAllRow', 'selectAllRowText', 'selectAllButton']
  // todo rename globalButton to globalCheckbox or pageButton ?
  connect () {
    this._checkIfAllCheckboxesAreSelected()
    this._updateHref()
  }

  toggleSelectAllAPageProjets () {
    const newValue = !this.allCheckboxesSelectedValue
    this.allCheckboxesSelectedValue = newValue
    if (newValue) {
      this._updateAllCheckboxes(true)
    } else {
      this._updateAllCheckboxes(false)
    }
    this._updateHref()
  }

  toggleSelectAllProjets () {
    this.allProjetsSelectedValue = !this.allProjetsSelectedValue
    if (this.allProjetsSelectedValue === false) {
      this._updateAllCheckboxes(false)
    }
    this._updateHref()
  }

  toggleProjetCheckbox (evt) {
    const eltValue = evt.target.checked
    if (eltValue === false) {
      this.allCheckboxesSelectedValue = false
    } else {
      this._checkIfAllCheckboxesAreSelected()
    }
    this._updateHref()
  }

  // Hook sur la valeur

  allCheckboxesSelectedValueChanged () {
    console.log('allCheckboxesSelectedValueChanged')
    this._updateACheckbox(this.globalButtonTarget, this.allCheckboxesSelectedValue)
    if (this.allCheckboxesSelectedValue === true) {
      this._displaySelectAllRow()
    } else {
      this._hideSelectAllRow()
      this.allProjetsSelectedValue = false
      console.log('this.allProjetsSelectedValue = false')
      this._updateHref()
    }
  }

  allProjetsSelectedValueChanged () {
    if (this.allProjetsSelectedValue) {
      this.selectAllRowTextTarget.innerText = `Les ${this.toNotifyProjetsCountValue} projets "à notifier" ont été sélectionnés.`
      this.selectAllButtonTarget.innerText = 'Effacer la sélection'
    } else {
      this.allCheckboxesSelectedValue = false
      this.selectAllRowTextTarget.innerText = `Les ${this.buttonTargets.length} projets "à notifier" de la page ont été sélectionnés.`
      this.selectAllButtonTarget.innerText = `Sélectionner l'ensemble des projets "à notifier" (${this.toNotifyProjetsCountValue})`
    }
  }

  // Private

  _updateHref () {
    const baseUrl = this.linkTarget.dataset.baseUrl
    console.log(this.allProjetsSelectedValue)
    if (this.allProjetsSelectedValue) {
      this.linkTarget.href = `${baseUrl}${window.location.search}`
      return
    }
    const selectedIds = this.buttonTargets
      .filter((b) => b.checked)
      .map((b) => b.id.split('-')[1])

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

  _displaySelectAllRow () {
    if (this.activateAllProjetsSelectionValue) {
      this.selectAllRowTarget.style.display = 'contents'
    }
  }

  _hideSelectAllRow () {
    this.selectAllRowTarget.style.display = 'none'
  }
}
