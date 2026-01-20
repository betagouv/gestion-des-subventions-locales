import { Controller } from 'stimulus'

export class DotationDropdown extends Controller {
  static values = {
    initialDotations: { type: Array, default: [] }
  }

  static targets = ['button', 'content', 'input', 'form']

  connect () {
    // Close dropdown when clicking outside
    this.boundHandleClickOutside = this._handleClickOutside.bind(this)
    document.addEventListener('click', this.boundHandleClickOutside)
  }

  disconnect () {
    if (this.boundHandleClickOutside) {
      document.removeEventListener('click', this.boundHandleClickOutside)
    }
  }

  toggle (event) {
    event.stopPropagation()
    const isOpen = this._isOpen()

    if (isOpen) {
      this._close()
      this._handleDotationChange()
    } else {
      this._open()
    }
  }

  updateSelectedDotations () {
    const newSelectedDotations = []
    if (this.hasInputTarget) {
      this.inputTargets.forEach((input) => {
        if (input.checked) {
          newSelectedDotations.push(input.value)
        }
      })
    }
    return newSelectedDotations
  }

  // Called when checkbox changes
  checkboxChange () {
    this._updateButtonText()
  }

  // Private

  _open () {
    if (this.hasContentTarget) {
      this.contentTarget.style.display = 'grid'
    }
  }

  _close () {
    if (this.hasContentTarget) {
      this.contentTarget.style.display = 'none'
    }
  }

  _isOpen () {
    return this.hasContentTarget && this.contentTarget.style.display === 'grid'
  }

  _handleClickOutside (event) {
    // Don't close if clicking on modal
    const modal = document.getElementById(
      'dotation-confirmation-modal-content'
    )
    if (modal && modal.contains(event.target)) {
      return
    }

    if (!this.element.contains(event.target) && this._isOpen()) {
      this._close()
      this._handleDotationChange()
    }
  }

  _handleDotationChange () {
    const newDotationValues = this.updateSelectedDotations()
    const initialDotationValues = this.initialDotationsValue

    if (this._arraysEqual(newDotationValues, initialDotationValues)) {
      return
    }

    if (
      this._mustOpenConfirmationModal(newDotationValues, initialDotationValues)
    ) {
      this._openConfirmationModal(newDotationValues, initialDotationValues)
    } else {
      this._submitForm()
    }
  }

  _updateButtonText () {
    if (this.hasButtonTarget) {
      const selectedDotations = this.updateSelectedDotations()
      this.buttonTarget.textContent =
        selectedDotations.length > 0
          ? selectedDotations.join(' et ')
          : 'Sélectionner une dotation'
    }
  }

  _mustOpenConfirmationModal (newValues, initialValues) {
    if (newValues.length === 0) {
      return false
    }
    if (
      newValues.length === 1 &&
      initialValues.length === 1 &&
      newValues[0] === initialValues[0]
    ) {
      return false
    }
    if (newValues.length === 2 && initialValues.length === 2) {
      return false
    }
    return true
  }

  _arraysEqual (a, b) {
    if (a === b) return true
    if (a == null || b == null) return false
    if (a.length !== b.length) return false

    for (let i = 0; i < a.length; ++i) {
      if (!b.includes(a[i])) return false
    }
    return true
  }

  _openConfirmationModal (newValues, initialValues) {
    const modalId = 'dotation-confirmation-modal-content'
    const modal = document.getElementById(modalId)
    if (!modal) return

    const message = modal.querySelector('#modal-body')
    const title = modal.querySelector('#modal-title')

    const newTitle = this._getTitle(newValues)
    if (newTitle && title) {
      title.innerText = newTitle
    }
    if (message) {
      message.innerHTML = this._getMessage(newValues, initialValues)
    }

    this._setConfimationButtonForm(modal)

    const cancelButtons = modal.querySelectorAll('.close-modal')
    cancelButtons.forEach((button) => {
      button.addEventListener('click', () => {
        this._closeModalAndResetForm(modal)
      })
    })

    // Open modal using DSFR
    if (typeof dsfr !== 'undefined') {
      dsfr(modal).modal.disclose()
    }
  }

  _closeModalAndResetForm (modal) {
    if (typeof dsfr !== 'undefined' && modal) {
      dsfr(modal).modal.conceal()
    }
    if (this.hasFormTarget) {
      this.formTarget.reset()
    }
    this._updateButtonText()
  }

  _setConfimationButtonForm (modal) {
    const confirmationButton = modal.querySelector('#confirm-dotation-update')
    if (confirmationButton) {
      confirmationButton.onclick = () => {
        this._submitForm()
      }
    }
  }

  _getTitle (selectedDotations) {
    if (selectedDotations.length === 2) {
      return 'Double dotation'
    }
    return 'Modification de la dotation'
  }

  _getMessage (newValues, initialValues) {
    if (initialValues.length === 2) {
      if (newValues.length === 1) {
        const dotationToRemove = initialValues
          .filter((dotation) => !newValues.includes(dotation))
          .pop()
        return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> Les enveloppes demandées étaient DETR et DSIL. Ce projet sera supprimé des simulations <strong>${dotationToRemove}</strong>.`
      }
    }

    if (newValues.length === 2) {
      const newDotation = newValues
        .filter((dotation) => !initialValues.includes(dotation))
        .pop()
      return `Ce projet sera aussi affiché dans les simulations ${newDotation}.`
    }
    if (newValues.length === 1 && initialValues.length === 1) {
      const dotationToRemove = initialValues[0]
      const newDotation = newValues[0]
      return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> L'enveloppe demandée était ${dotationToRemove}, la nouvelle enveloppe attribuée est ${newDotation}. Ce projet sera ajouté dans vos simulations ${newDotation} et sera supprimé des simulations ${dotationToRemove}.`
    }
  }

  _submitForm () {
    if (this.hasFormTarget) {
      this.formTarget.submit()
    }
  }
}
