document.querySelectorAll(".status-radio-button").forEach((elt) => {
    elt.addEventListener("change", (ev) => {
        let target = ev.target;
        return handleStatusChange(target, target.dataset.originalValue);
      })
})

detr_avis_commission = document.querySelector("#id_detr_avis_commission")
if (detr_avis_commission) {
    detr_avis_commission.addEventListener("change", (ev) => {
    if(ev.target) ev.target.form.submit();
  })
}

document.querySelectorAll(".form-disabled-before-value-change").forEach((elt) => {
  let button = elt.querySelector("button[type='submit']")
  if (button)(
    elt.addEventListener("change", (ev) => {
      button.disabled = false;
    })
  )
})

// Dotation Update (put it in other file)
const getDotationValues = () => {
  let dotationFieldSet = document.querySelector("#dotation-fieldset")
  const checkedValues = Array.from(dotationFieldSet.querySelectorAll('input[type="checkbox"]:checked')).map(checkbox => checkbox.value);
  return checkedValues
}

const getTitle = () => {
  const newValues = getDotationValues()
  if (newValues.length === 2) {
    return "Double dotation"
  }
}

const getMessage = (target) => {
  const initialValues = target.dataset.initialDotations.split(",")
  const newValues = getDotationValues()
  if (initialValues.length === 2) {
    if (newValues.length === 1) {
      let dotationToRemove = initialValues.filter(dotation => !newValues.includes(dotation)).pop()
      return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> Les enveloppes demandées étaient DETR et DSIL. Ce projet sera supprimé des simulations <strong>${dotationToRemove}</strong>.`
    }
  }

  if (newValues.length === 2) {
    let newDotation = newValues.filter(dotation => !initialValues.includes(dotation)).pop()
    return `Ce projet sera aussi affiché dans les simulations ${newDotation}.`
  }
  if (newValues.length === 1 && initialValues.length === 1) {
    let dotationToRemove = initialValues.pop()
    let newDotation = newValues.pop()
    return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> L'enveloppe demandée était ${dotationToRemove}, la nouvelle enveloppe attribuée est ${newDotation}. Ce projet sera ajouté dans vos simulations ${newDotation} et sera supprimé des simulations ${dotationToRemove}.`
  }
}

const openConfirmatioModal = (target) => {
  modalId = "dotation-confirmation-modal-content"
  let modal = document.getElementById(modalId)
  let message = modal.querySelector("#modal-body")
  let title = modal.querySelector("#modal-title")

  const newTitle = getTitle(target)
  if (newTitle) {
    title.innerText = newTitle
  }
  message.innerHTML = getMessage(target)

  dsfr(modal).modal.disclose()
}

const mustOpenDotationUpdateConfirmationModal = (target) => {
  let dotationValues = getDotationValues()
  let newValues = target.dataset.initialDotations.split(",")
  if (dotationValues.length === 0) {
    return false
  }
  if (dotationValues.length === 1 && newValues.length === 1 && dotationValues[0] === newValues[0]) {
    return false
  }
  if (dotationValues.length === 2 && newValues.length === 2) {
    return false
  }
  return true
}

document.querySelector("#submit-dotation").addEventListener("click", (ev) => {
  ev.preventDefault();
  if (mustOpenDotationUpdateConfirmationModal(ev.target)) {
    selectedElement = ev.target
    openConfirmatioModal(ev.target)
  } else {
    let form = document.querySelector("form#simulation_projet_form").closest("form")
    form.submit()
  }
});

document.querySelector("#confirm-dotation-update").addEventListener("click", (ev) => {
  let form = document.querySelector("form#simulation_projet_form").closest("form")
  form.submit()
  closeModal()
})