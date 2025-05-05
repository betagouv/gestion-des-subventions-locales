document.querySelectorAll(".status-radio-button").forEach((elt) => {
    elt.addEventListener("change", (ev) => {
        let target = ev.target;
        return handleStatusChange(target, target.dataset.originalValue);
      })
})

document.querySelector("#id_detr_avis_commission").addEventListener("change", (ev) => {
  if(ev.target) ev.target.form.submit();
})

document.querySelectorAll(".form-disabled-before-value-change").forEach((elt) => {
  let button = elt.querySelector("button[type='submit']")
  
  elt.addEventListener("change", (ev) => {
    button.disabled = false;
  })
})