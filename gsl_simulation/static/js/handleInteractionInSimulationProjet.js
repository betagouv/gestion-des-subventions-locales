document.querySelectorAll(".status-radio-button").forEach((elt) => {
    elt.addEventListener("change", (ev) => {
        let target = ev.target;
        return handleStatusChange(target, target.dataset.originalValue);
      })
})

document.querySelector("#avis_commission_detr").addEventListener("change", (ev) => {
  if(ev.target) ev.target.form.submit();
})

document.querySelector("#is-in-qpv-and-is-attached-to-a-crte-form").addEventListener("change", (ev) => {
  disableIsInQPVAndIsAttachedToACrteSubmitButtonIfValuesHasChanged()
})

function disableIsInQPVAndIsAttachedToACrteSubmitButtonIfValuesHasChanged(){
  const button=document.querySelector("#submit-is-in-qpv-and-is-attached-to-a-crte");

  original_is_in_qpv = button.dataset.isInQpv == "True"
  original_is_attached_to_a_crte = button.dataset.isAttachedToACrte == "True"
  
  current_is_in_qpv = document.querySelector("#is-in-qpv").checked
  current_is_attached_to_a_crte = document.querySelector("#is-attached-to-a-crte").checked

  if(current_is_in_qpv !== original_is_in_qpv || current_is_attached_to_a_crte !== original_is_attached_to_a_crte){
    button.disabled = false;
  } else {
    button.disabled = true;
  }
}
disableIsInQPVAndIsAttachedToACrteSubmitButtonIfValuesHasChanged()