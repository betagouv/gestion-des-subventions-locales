import { handleDotationChange } from "./modules/handleDotationUpdate.js";
import { disableAllModalButtons } from "./modules/utils.js";

document.querySelectorAll(".status-radio-button").forEach((elt) => {
    elt.addEventListener("change", (ev) => {
        let target = ev.target;
        return handleStatusChange(target, target.dataset.originalValue);
      })
})

let detr_avis_commission = document.querySelector("#id_detr_avis_commission")
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

// Dotation Update

document.querySelector("#submit-dotation").addEventListener("click", (ev) => {
  ev.preventDefault();
  selectedElement = ev.target
  let form = document.querySelector("form#projet_form").closest("form")
  let fieldset = document.querySelector("#dotation-fieldset")
  const initalDotationValues = selectedElement.dataset.initialDotations.split(",")
  handleDotationChange(form, fieldset, initalDotationValues)
});


document.querySelectorAll("#confirm-dotation-update").forEach(elt => {
  elt.addEventListener("click", async (ev) => {
    disableAllModalButtons(elt.closest(".confirmation-modal"));
    let form = document.querySelector("form#projet_form").closest("form")
    form.submit()
    closeModal()
  })
})
