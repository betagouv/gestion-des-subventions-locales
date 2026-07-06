import { Controller } from 'stimulus'

export class ProjetNotes extends Controller {
  static targets = ['addForm']

  connect () {
    this._dirty = false
    this._pendingCancelButton = null
    this._pendingDeleteForm = null
    this._boundBeforeUnload = this._handleBeforeUnload.bind(this)
    window.addEventListener('beforeunload', this._boundBeforeUnload)
    if (this.hasAddFormTarget && this.addFormTarget.querySelector('.fr-error-text')) {
      this.addFormTarget.style.display = 'block'
    }
    _bindModalConfirm('delete-confirmation-modal', (modal) => {
      _disableButtons(modal)
      this._pendingDeleteForm?.submit()
      this._pendingDeleteForm = null
    })
    _bindModalConfirm('cancel-update-confirmation-modal', (modal) => {
      _disableButtons(modal)
      dsfr(modal).modal.conceal()
      this._pendingCancelButton?.dispatchEvent(new Event('cancel'))
      this._pendingCancelButton = null
    })
  }

  disconnect () {
    window.removeEventListener('beforeunload', this._boundBeforeUnload)
  }

  showAddForm () {
    this.addFormTarget.style.display = 'block'
  }

  trackInput () {
    this._dirty = true
  }

  clearDirty () {
    this._dirty = false
  }

  handleKeydown (evt) {
    if (evt.key === 'Enter' && (evt.shiftKey || evt.metaKey)) {
      evt.preventDefault()
      evt.target.form?.submit()
    }
  }

  openDeleteModal ({ detail: { form, title } }) {
    const modal = document.getElementById('delete-confirmation-modal')
    if (!modal) return
    const titleEl = modal.querySelector('.modal-title')
    if (titleEl) titleEl.textContent = `Suppression de ${title}`
    this._pendingDeleteForm = form
    _enableButtons(modal)
    dsfr(modal).modal.disclose()
  }

  openCancelModal ({ detail: { button } }) {
    const modal = document.getElementById('cancel-update-confirmation-modal')
    if (!modal) return
    this._pendingCancelButton = button
    _enableButtons(modal)
    dsfr(modal).modal.disclose()
  }

  _handleBeforeUnload (evt) {
    const hasDirtyCard = !!this.element.querySelector(
      '[data-controller*="projet-note-card"][data-projet-note-card-dirty-value="true"]'
    )
    if (this._dirty || hasDirtyCard) {
      evt.preventDefault()
      evt.returnValue = ''
    }
  }
}

function _bindModalConfirm (modalId, onConfirm) {
  const modal = document.getElementById(modalId)
  if (!modal) return
  modal.querySelector('.confirm')?.addEventListener('click', (evt) => {
    evt.preventDefault()
    onConfirm(modal)
  })
}

function _enableButtons (modal) {
  modal.querySelectorAll('button').forEach(btn => { btn.disabled = false })
}

function _disableButtons (modal) {
  modal.querySelectorAll('button').forEach(btn => { btn.disabled = true })
}
