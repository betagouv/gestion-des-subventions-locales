const detrAvisCommission = document.querySelector('#id_detr_avis_commission')
if (detrAvisCommission) {
  detrAvisCommission.addEventListener('change', (ev) => {
    if (ev.target) ev.target.form.submit()
  })
}

document
  .querySelectorAll('.form-disabled-before-value-change')
  .forEach((elt) => {
    const button = elt.querySelector("button[type='submit']")
    if (button) {
      elt.addEventListener('change', (ev) => {
        button.disabled = false
      })
    }
  })
