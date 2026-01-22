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

document.addEventListener('DOMContentLoaded', function () {
  const checkbox = document.querySelector(
    'input[data-toggle="contrat-local"]'
  )
  const checkbox2 = document.querySelector(
    'input[data-toggle="autre-zonage-local"]'
  )
  const wrapper = document.getElementById('contrat_local-wrapper')
  const wrapper2 = document.getElementById('autre_zonage_local-wrapper')

  function toggleContratLocal () {
    if (checkbox.checked) {
      wrapper.classList.remove('fr-hidden')
    } else {
      wrapper.classList.add('fr-hidden')
    }
  }

  function toggleAutreZonageLocal () {
    if (checkbox2.checked) {
      wrapper2.classList.remove('fr-hidden')
    } else {
      wrapper2.classList.add('fr-hidden')
    }
  }

  // Initialisation (important si form rechargé avec erreurs)
  toggleContratLocal()
  toggleAutreZonageLocal()
  checkbox.addEventListener('change', toggleContratLocal)
  checkbox2.addEventListener('change', toggleAutreZonageLocal)
})
