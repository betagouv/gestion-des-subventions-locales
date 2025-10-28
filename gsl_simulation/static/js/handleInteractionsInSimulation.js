'use strict'

import { handleDotationChange } from './modules/handleDotationUpdate.js'
import { disableAllModalButtons } from './modules/utils.js'
import {
  handleStatusChangeWithHtmx
} from './simulationProjetStatusConfirmation.js'

document.querySelector('.gsl-projet-table').addEventListener('change', (ev) => {
  if (ev.target.hasAttribute('hx-post') && !ev.target.disabled) {
    if (typeof htmx !== 'undefined') {
      htmx.trigger(ev.target, 'change')
    } else {
      ev.target.form.submit()
    }
    ev.preventDefault()
  }
})

document.querySelector('.gsl-projet-table').addEventListener('submit', (ev) => {
  ev.preventDefault()
})

document.querySelector('.gsl-projet-table').addEventListener('change', (ev) => {
  const target = ev.target
  if (!target.classList.contains('status-select')) {
    return
  }
  return handleStatusChangeWithHtmx(target, target.dataset.originalValue) // eslint-disable-line
})

document.addEventListener('htmx:responseError', evt => {
  const xhr = evt.detail.xhr

  if (xhr.status >= 400) {
    evt.detail.elt.form.reset()
  }
})

// Dotation Update //
let selectedForm

// Toggle dropdowns
document.querySelectorAll('.dotation-dropdown button').forEach(button => {
  button.addEventListener('click', function (event) {
    event.stopPropagation()
    const content = this.nextElementSibling

    if (content) {
      const wasContentDisplayed = content.style.display === 'grid'
      content.style.display = wasContentDisplayed ? 'none' : 'grid'

      if (wasContentDisplayed) {
        selectedElement = content // eslint-disable-line
        selectedForm = content.closest('form')
        const fieldset = content.closest('fieldset')
        const initialValues = content.dataset.initialDotations.split(',')
        handleDotationChange(selectedForm, fieldset, initialValues)
      }
    }
  })
})

document.querySelectorAll('#confirm-dotation-update').forEach(elt => {
  elt.addEventListener('click', (ev) => {
    disableAllModalButtons(elt.closest('.confirmation-modal'))
    selectedForm.submit()
    closeModal() // eslint-disable-line
    // TODO import this function from a module
  })
})
