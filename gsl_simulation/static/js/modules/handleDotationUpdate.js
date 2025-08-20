// TODO => use doubleDotation Controller for simulationDetail page, then remove this file !
let newDotationValues
let initialDotationValues

const getDotationValues = (dotationFieldSet) => {
  const checkedValues = Array.from(dotationFieldSet.querySelectorAll('input[type="checkbox"]:checked')).map(checkbox => checkbox.value)
  return checkedValues
}

const getTitle = () => {
  if (newDotationValues.length === 2) {
    return 'Double dotation'
  }
  return 'Modification de la dotation'
}

const getMessage = () => {
  if (initialDotationValues.length === 2) {
    if (newDotationValues.length === 1) {
      const dotationToRemove = initialDotationValues.filter(dotation => !newDotationValues.includes(dotation)).pop()
      return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> Les enveloppes demandées étaient DETR et DSIL. Ce projet sera supprimé des simulations <strong>${dotationToRemove}</strong>.`
    }
  }

  if (newDotationValues.length === 2) {
    const newDotation = newDotationValues.filter(dotation => !initialDotationValues.includes(dotation)).pop()
    return `Ce projet sera aussi affiché dans les simulations ${newDotation}.`
  }
  if (newDotationValues.length === 1 && initialDotationValues.length === 1) {
    const dotationToRemove = initialDotationValues[0]
    const newDotation = newDotationValues[0]
    return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> L'enveloppe demandée était ${dotationToRemove}, la nouvelle enveloppe attribuée est ${newDotation}. Ce projet sera ajouté dans vos simulations ${newDotation} et sera supprimé des simulations ${dotationToRemove}.`
  }
}

const openConfirmatioModal = () => {
  modalId = 'dotation-confirmation-modal-content' // eslint-disable-line
  const modal = document.getElementById(modalId)  // eslint-disable-line
  const message = modal.querySelector('#modal-body')
  const title = modal.querySelector('#modal-title')

  const newTitle = getTitle()
  if (newTitle) {
    title.innerText = newTitle
  }
  message.innerHTML = getMessage()

  dsfr(modal).modal.disclose()
}

const mustOpenDotationUpdateConfirmationModal = (newValues, initialValues) => {
  if (newValues.length === 0) {
    return false
  }
  if (newValues.length === 1 && initialValues.length === 1 && newValues[0] === initialValues[0]) {
    return false
  }
  if (newValues.length === 2 && initialValues.length === 2) {
    return false
  }
  return true
}

function arraysEqual (a, b) {
  if (a === b) return true
  if (a == null || b == null) return false
  if (a.length !== b.length) return false

  for (let i = 0; i < a.length; ++i) {
    if (!b.includes(a[i])) return false
  }
  return true
}

export function handleDotationChange (form, fieldset, initalValues) {
  newDotationValues = getDotationValues(fieldset)
  initialDotationValues = initalValues

  if (arraysEqual(newDotationValues, initialDotationValues)) {
    return
  }

  if (mustOpenDotationUpdateConfirmationModal(newDotationValues, initialDotationValues)) {
    openConfirmatioModal()
    formButton = document.querySelector("button[type='submit']#submit-dotation")  // eslint-disable-line
  } else {
    form.submit()
  }
}
