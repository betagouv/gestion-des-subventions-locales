import { Controller } from 'stimulus'

export class BulkSelection extends Controller {
  static targets = ['allCheckbox', 'rowCheckbox', 'counter', 'counterWrapper', 'menuButton', 'action']

  connect () {
    this.refresh()
  }

  // Also called for rows re-rendered out of band, which must keep their selection.
  rowCheckboxTargetConnected (checkbox) {
    const storedIds = sessionStorage.getItem(this.storageKey)?.split(',') ?? []
    checkbox.checked = storedIds.includes(checkbox.value)
  }

  get storageKey () {
    return `bulkSelection-${window.location.pathname}`
  }

  toggleAll () {
    for (const checkbox of this.rowCheckboxTargets) {
      checkbox.checked = this.allCheckboxTarget.checked
    }
    this.refresh()
  }

  clearSelection () {
    for (const checkbox of this.rowCheckboxTargets) {
      checkbox.checked = false
    }
    this.refresh()
  }

  refresh () {
    const checked = this.rowCheckboxTargets.filter((checkbox) => checkbox.checked)
    const total = this.rowCheckboxTargets.length
    sessionStorage.setItem(this.storageKey, checked.map((checkbox) => checkbox.value).join(','))
    this.counterTarget.textContent = checked.length
    this.counterWrapperTarget.classList.toggle('fr-text-mention--grey', !checked.length)
    this.menuButtonTarget.disabled = !checked.length
    this.allCheckboxTarget.checked = total > 0 && checked.length === total
    this.allCheckboxTarget.indeterminate = checked.length > 0 && checked.length < total
    for (const action of this.actionTargets) {
      const ids = checked
        .filter((checkbox) => checkbox.dataset.actions.split(' ').includes(action.dataset.actionName))
        .map((checkbox) => checkbox.value)
      action.querySelector('[data-bulk-ids]').value = ids.join(',')
      const count = action.querySelector('[data-bulk-count]')
      if (count) count.textContent = ids.length
      action.querySelector('[type=submit]').disabled = !ids.length
    }
  }
}
