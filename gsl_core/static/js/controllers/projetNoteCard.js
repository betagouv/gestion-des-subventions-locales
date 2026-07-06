import { Controller } from 'stimulus'

export class ProjetNoteCard extends Controller {
  static values = { dirty: Boolean }

  trackInput () {
    this.dirtyValue = true
  }

  clearDirty () {
    this.dirtyValue = false
  }

  handleKeydown (evt) {
    if (evt.key === 'Enter' && (evt.shiftKey || evt.metaKey)) {
      evt.preventDefault()
      evt.target.form?.submit()
    }
  }

  confirmDelete (evt) {
    evt.preventDefault()
    const form = evt.target.closest('form')
    const title = form?.dataset.noteTitle || ''
    this.dispatch('delete-requested', { detail: { form, title }, bubbles: true })
  }

  confirmCancel (evt) {
    evt.preventDefault()
    const button = evt.currentTarget
    if (this.dirtyValue) {
      this.dispatch('cancel-requested', { detail: { button }, bubbles: true })
    } else {
      button.dispatchEvent(new Event('cancel'))
    }
  }
}
