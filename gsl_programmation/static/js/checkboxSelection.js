import { Controller } from 'stimulus'

export class CheckboxSelection extends Controller {
  static values = {
    allPageProjetsSelected: { type: Boolean, default: false },
    allProjetsSelected: { type: Boolean, default: false },
    toNotifyProjetsCount: Number,
    activateAllProjetsSelection: { type: Boolean, default: false }
  }

  static targets = ['pageCheckbox', 'button', 'generateButton', 'idsInput', 'selectAllRow', 'selectAllRowText', 'selectAllButton']

  connect () {
    this._checkIfAllCheckboxesAreSelected()
    this._updateGenerateButton()
  }

  toggleSelectAllAPageProjets () {
    const newValue = !this.allPageProjetsSelectedValue
    this.allPageProjetsSelectedValue = newValue
    if (newValue) {
      this._updateAllCheckboxes(true)
    } else {
      this._updateAllCheckboxes(false)
    }
    this._updateGenerateButton()
  }

  toggleSelectAllProjets () {
    this.allProjetsSelectedValue = !this.allProjetsSelectedValue
    if (this.allProjetsSelectedValue === false) {
      this._updateAllCheckboxes(false)
    }
    this._updateGenerateButton()
  }

  toggleProjetCheckbox (evt) {
    const eltValue = evt.target.checked
    if (eltValue === false) {
      this.allPageProjetsSelectedValue = false
    } else {
      this._checkIfAllCheckboxesAreSelected()
    }
    this._updateGenerateButton()
  }

  // Hook sur les valeurs

  allPageProjetsSelectedValueChanged () {
    this._updateACheckbox(this.pageCheckboxTarget, this.allPageProjetsSelectedValue)
    if (this.allPageProjetsSelectedValue === true) {
      this._displaySelectAllRow()
    } else {
      this._hideSelectAllRow()
      this.allProjetsSelectedValue = false
      this._updateGenerateButton()
    }
  }

  allProjetsSelectedValueChanged () {
    if (this.allProjetsSelectedValue) {
      this.selectAllRowTextTarget.innerText = `Les ${this.toNotifyProjetsCountValue} projets "à notifier" ont été sélectionnés.`
      this.selectAllButtonTarget.innerText = 'Effacer la sélection'
    } else {
      this.allPageProjetsSelectedValue = false
      this.selectAllRowTextTarget.innerText = `Les ${this.buttonTargets.length} projets "à notifier" de la page ont été sélectionnés.`
      this.selectAllButtonTarget.innerText = `Sélectionner l'ensemble des projets "à notifier" (${this.toNotifyProjetsCountValue})`
    }
  }

  // Private

  _updateGenerateButton () {
    if (!this.hasGenerateButtonTarget) return

    if (this.allProjetsSelectedValue) {
      // IDs vide → la vue utilise les filtres de l'URL en fallback
      this.idsInputTarget.value = ''
      this.generateButtonTarget.disabled = false
      return
    }

    const selectedIds = this.buttonTargets
      .filter((b) => b.checked)
      .map((b) => b.id.split('-')[1])

    this.idsInputTarget.value = selectedIds.join(',')
    this.generateButtonTarget.disabled = selectedIds.length === 0
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
      this.allPageProjetsSelectedValue = true
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
