import { Controller } from 'stimulus'

export class CheckboxSelection extends Controller {
  static values = {
    // When true, submits empty IDs when all are selected (view uses URL filters as fallback)
    emptyMeansAll: { type: Boolean, default: false },
    userId: { type: Number, default: 0 }
  }

  static targets = [
    'pageCheckbox',
    'rowCheckbox',
    'counter',
    'counterWrapper',
    'idsInput',
    'selectAllButton',
    'actionButton'
  ]

  initialize () {
    this.selectedIds = new Set()
    const jsonEl = document.getElementById('checkbox-selection-selectable-ids')
    this.selectableIds = jsonEl ? JSON.parse(jsonEl.textContent) : []
    this._loadFromStorage()
  }

  connect () {
    this._restoreCheckboxStates()
    this.rowCheckboxTargets.forEach((checkbox) => {
      if (checkbox.checked) {
        this.selectedIds.add(parseInt(checkbox.value, 10))
      }
    })
    this._refresh()
  }

  toggleRow (event) {
    const id = parseInt(event.target.value, 10)
    if (event.target.checked) {
      this.selectedIds.add(id)
    } else {
      this.selectedIds.delete(id)
    }
    this._refresh()
  }

  togglePageSelection (event) {
    const checked = event.target.checked
    this.rowCheckboxTargets.forEach((checkbox) => {
      this._setCheckbox(checkbox, checked)
      const id = parseInt(checkbox.value, 10)
      if (checked) {
        this.selectedIds.add(id)
      } else {
        this.selectedIds.delete(id)
      }
    })
    this._refresh()
  }

  toggleSelectAll () {
    if (this.selectedIds.size >= this.selectableIds.length) {
      this.selectedIds.clear()
      this.rowCheckboxTargets.forEach((c) => this._setCheckbox(c, false))
    } else {
      this.selectableIds.forEach((id) => this.selectedIds.add(id))
      this.rowCheckboxTargets.forEach((c) => this._setCheckbox(c, true))
    }
    this._refresh()
  }

  beforeSubmit (event) {
    if (this.selectedIds.size === 0) {
      event.preventDefault()
      return
    }
    this._syncIdsInputs()
  }

  pageCheckboxTargetConnected () {
    this._restoreCheckboxStates()
    this._refresh()
  }

  _refresh () {
    const count = this.selectedIds.size
    const allSelected = count > 0 && count >= this.selectableIds.length

    if (this.hasCounterTarget) {
      this.counterTarget.textContent = count
    }
    if (this.hasCounterWrapperTarget) {
      this.counterWrapperTarget.classList.toggle('fr-text-mention--grey', count === 0)
    }
    this.actionButtonTargets.forEach((btn) => { btn.disabled = count === 0 })
    if (this.hasSelectAllButtonTarget) {
      this.selectAllButtonTarget.textContent = allSelected
        ? 'Désélectionner tous les projets'
        : `Sélectionner tous les ${this.selectableIds.length} projets`
    }
    if (this.hasPageCheckboxTarget) {
      const visible = this.rowCheckboxTargets
      const allChecked = visible.length > 0 && visible.every((c) => c.checked)
      this._setCheckbox(this.pageCheckboxTarget, allChecked)
    }
    this._syncIdsInputs()
    this._saveToStorage()
  }

  _setCheckbox (element, value) {
    element.checked = value
    element.setAttribute('data-fr-js-checkbox-input', value)
  }

  _syncIdsInputs () {
    const allSelected = this.selectedIds.size >= this.selectableIds.length && this.selectableIds.length > 0
    const value = (this.emptyMeansAllValue && allSelected)
      ? ''
      : Array.from(this.selectedIds).join(',')
    this.idsInputTargets.forEach((input) => { input.value = value })
  }

  _storageKey () {
    return `checkboxSelection-${this.userIdValue}-${window.location.pathname}`
  }

  _saveToStorage () {
    if (this.selectedIds.size === 0) {
      sessionStorage.removeItem(this._storageKey())
    } else {
      sessionStorage.setItem(this._storageKey(), Array.from(this.selectedIds).join(','))
    }
  }

  _loadFromStorage () {
    const stored = sessionStorage.getItem(this._storageKey())
    if (!stored) return
    stored.split(',').forEach((id) => {
      const parsed = parseInt(id, 10)
      if (!isNaN(parsed) && this.selectableIds.includes(parsed)) {
        this.selectedIds.add(parsed)
      }
    })
  }

  _restoreCheckboxStates () {
    this.rowCheckboxTargets.forEach((checkbox) => {
      if (this.selectedIds.has(parseInt(checkbox.value, 10))) {
        this._setCheckbox(checkbox, true)
      }
    })
  }
}
