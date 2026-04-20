import { Controller } from 'stimulus'

export class BulkStatusChange extends Controller {
  static targets = [
    'pageCheckbox',
    'rowCheckbox',
    'counter',
    'counterWrapper',
    'idsInput',
    'selectAllButton',
    'applyButton'
  ]

  connect () {
    this.selectedIds = new Set()
    const selectableJson = document.getElementById('bulk-status-change-selectable-ids')
    this.selectableIds = selectableJson ? JSON.parse(selectableJson.textContent) : []
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
      this.rowCheckboxTargets.forEach((checkbox) => {
        this._setCheckbox(checkbox, false)
      })
    } else {
      this.selectableIds.forEach((id) => this.selectedIds.add(id))
      this.rowCheckboxTargets.forEach((checkbox) => {
        this._setCheckbox(checkbox, true)
      })
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

  _refresh () {
    const count = this.selectedIds.size
    if (this.hasCounterTarget) {
      this.counterTarget.textContent = count
    }
    if (this.hasCounterWrapperTarget) {
      this.counterWrapperTarget.classList.toggle('fr-text-mention--grey', count === 0)
    }
    if (this.hasApplyButtonTarget) {
      this.applyButtonTarget.disabled = count === 0
    }
    if (this.hasSelectAllButtonTarget) {
      const allSelected = count > 0 && count >= this.selectableIds.length
      this.selectAllButtonTarget.textContent = allSelected
        ? 'Désélectionner tous les projets'
        : `Sélectionner tous les ${this.selectableIds.length} projets`
    }
    if (this.hasPageCheckboxTarget) {
      const visible = this.rowCheckboxTargets
      const allChecked =
        visible.length > 0 && visible.every((c) => c.checked)
      this._setCheckbox(this.pageCheckboxTarget, allChecked)
    }
    this._syncIdsInputs()
  }

  _setCheckbox (element, value) {
    element.checked = value
    element.setAttribute('data-fr-js-checkbox-input', value)
  }

  _syncIdsInputs () {
    const value = Array.from(this.selectedIds).join(',')
    this.idsInputTargets.forEach((input) => {
      input.value = value
    })
  }
}
