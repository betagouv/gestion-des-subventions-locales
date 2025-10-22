'use strict'

import htmx from '../vendor/htmx.esm.js'

let selectedElement
let modalId

// Used in handleInteractionInSimulationProjet.js
let formButton // eslint-disable-line

const VALID = 'valid'
const CANCELLED = 'cancelled'
const DISMISSED = 'dismissed'
const PROCESSING = 'draft'
const PROVISIONALLY_ACCEPTED = 'provisionally_accepted'
const STATUS_PROVISIONALLY_REFUSED = 'provisionally_refused'

const STATUSES_WITH_OTHER_SIMULATION_IMPACT = [VALID, CANCELLED, DISMISSED]
const STATUSES_WITHOUT_OTHER_SIMULATION_IMPACT = [PROCESSING, PROVISIONALLY_ACCEPTED, STATUS_PROVISIONALLY_REFUSED]

const STATUS_TO_MODAL_ID = {
  valid: 'accept-confirmation-modal',
  cancelled: 'refuse-confirmation-modal',
  draft: 'processing-confirmation-modal',
  dismissed: 'dismiss-confirmation-modal',
  provisionally_accepted: 'provisionally_accepted-confirmation-modal',
  provisionally_refused: 'provisionally_refused-confirmation-modal'
}

const STATUS_TO_FRENCH_WORD = {
  valid: 'validé',
  cancelled: 'refusé',
  dismissed: 'classé sans suite'
}

function mustOpenConfirmationModal (newValue, originalValue) {
  if (STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(newValue)) return true
  if (STATUSES_WITHOUT_OTHER_SIMULATION_IMPACT.includes(newValue) && STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(originalValue)) return true
  return false
}

export function handleStatusChangeWithHtmx (select, originalValue) { // eslint-disable-line no-unused-vars
  if (mustOpenConfirmationModal(select.value, originalValue)) {
    showConfirmationModal(select, originalValue)
  } else {
    if (typeof htmx !== 'undefined') htmx.trigger(select.form, 'status-confirmed') // Déclenche le PATCH HTMX
    else select.form.submit()
  }
}

export function handleStatusChange (select, originalValue) { // eslint-disable-line no-unused-vars
  if (mustOpenConfirmationModal(select.value, originalValue)) {
    showConfirmationModal(select, originalValue)
  } else {
    select.form.submit()
  }
}

function showConfirmationModal (select, originalValue) {
  const status = select.value
  modalId = STATUS_TO_MODAL_ID[status]
  if (modalId === undefined) {
    console.log('No modal for this status', status)
    return
  }
  selectedElement = select
  if (STATUSES_WITHOUT_OTHER_SIMULATION_IMPACT.includes(status)) {
    const modalContentId = `${status}-confirmation-modal-content`
    _replaceInitialStatusModalContentText(originalValue, modalContentId)
    if (originalValue === DISMISSED) _removeFromProgrammationText(modalContentId)
  }

  const modal = document.getElementById(modalId)
  _associateFieldMotivationToForm(select, modal)
  _ensureButtonsAreEnabled(select, modal)
  dsfr(modal).modal.disclose()
  htmx.trigger(select.querySelector('[value=' + status + ']'), modalId) // Load HTMX modals contents
}

function _associateFieldMotivationToForm (select, modal) {
  if (modal) {
    const formId = select.closest('form').id
    const motivationField = modal.querySelector('#motivation')
    if (motivationField) {
      motivationField.setAttribute('form', formId)
    }
  }
}

function _replaceInitialStatusModalContentText (originalValue, modalContentId) {
  const confirmationModalContent = document.getElementById(modalContentId)
  const newText = STATUS_TO_FRENCH_WORD[originalValue]
  confirmationModalContent.querySelector('.initial-status').innerHTML = newText
}

function _removeFromProgrammationText (modalContentId) {
  const confirmationModalContent = document.getElementById(modalContentId)
  try {
    confirmationModalContent.querySelector('.remove-from-programmation').remove()
  } catch (e) {
    console.log('No element to remove')
  }
}

function _ensureButtonsAreEnabled (modal) {
  const buttons = modal.querySelectorAll('button')
  buttons.forEach((button) => {
    button.disabled = false
  })
}

function _disableAllModalButtons (modal) {
  const buttons = modal.querySelectorAll('button')
  buttons.forEach((button) => {
    button.disabled = true
  })
}

function closeModal () {
  if (modalId === undefined) {
    return
  }

  const modal = document.getElementById(modalId)
  selectedElement.form.reset()
  dsfr(modal).modal.conceal()
  selectedElement.focus()
  if (formButton) {
    formButton.disabled = true
  }
  selectedElement = undefined
  modalId = undefined
}

//
// Event listeners
//

document.querySelectorAll('.close-modal').forEach((el) => {
  el.addEventListener('click', () => {
    closeModal()
  })
})

document.querySelectorAll('#confirmChange').forEach((e) => {
  e.addEventListener('click', function () {
    _disableAllModalButtons(this.closest('.confirmation-modal'))
    if (selectedElement) {
      selectedElement.form.submit()
    } else {
      closeModal()
    }
  })
})

document.addEventListener('keydown', function (event) {
  if (event.key === 'Escape' && selectedElement) {
    closeModal()
  }
})

document.querySelectorAll('.confirmation-modal').forEach((elt) => {
  elt.addEventListener('dsfr.conceal', (ev) => {
    closeModal()
  })
})
