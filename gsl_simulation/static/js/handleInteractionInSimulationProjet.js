document.querySelectorAll(".status-radio-button").forEach((elt) => {
    elt.addEventListener("change", (ev) => {
        let target = ev.target;
        return handleStatusChange(target, target.dataset.originalValue);
      })
})

document.querySelector("#avis_commission_detr").addEventListener("change", (ev) => {
  if(ev.target) ev.target.form.submit();
})
