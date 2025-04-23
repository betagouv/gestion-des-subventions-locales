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