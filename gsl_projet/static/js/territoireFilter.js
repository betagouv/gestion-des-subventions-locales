// Gestion des impacts des enfants sur les parents
document.querySelectorAll('.territoire-type-a input[type="checkbox"]').forEach(checkbox => {
  checkbox.addEventListener('change', updateDepartementalCheckboxStatesFromItsArrondissements)
})
document.querySelectorAll('.territoire-type-d input[type="checkbox"]').forEach(checkbox => {
  checkbox.addEventListener('change', updateRegionalCheckboxFromDepartement)
})

function updateRegionalCheckboxFromDepartement () {
  document.querySelectorAll('.territoire-type-r input[type="checkbox"]').forEach(parentCheckbox => updateCheckboxStateDependingOnChild(parentCheckbox))
}

function updateDepartementalCheckboxStatesFromItsArrondissements () {
  document.querySelectorAll('.territoire-type-d input[type="checkbox"]').forEach(parentCheckbox => updateDepartementalCheckboxState(parentCheckbox))
}

function updateDepartementalCheckboxState (checkbox) {
  updateCheckboxStateDependingOnChild(checkbox)
  updateRegionalCheckboxFromDepartement()
}

function updateCheckboxStateDependingOnChild (checkbox) {
  const parentName = checkbox.dataset.region || checkbox.dataset.departement
  if (!parentName) return

  const childCheckboxes = document.querySelectorAll(`input[data-parent='${parentName}']`)
  const checkedChildren = [...childCheckboxes].filter(cb => cb.checked)
  const indeterminatedChildren = [...childCheckboxes].filter(cb => cb.indeterminate)
  const allChecked = checkedChildren.length === childCheckboxes.length
  const someChecked = checkedChildren.length > 0 && !allChecked
  const someIndeterminated = indeterminatedChildren.length > 0

  checkbox.checked = allChecked
  checkbox.indeterminate = someChecked || someIndeterminated
}

// Gestion du clic sur un parent pour cocher/décocher ses enfants
document.querySelectorAll('.territoire-type-d input[type="checkbox"]').forEach(parentCheckbox => {
  parentCheckbox.addEventListener('change', function () { updateDepartementalChildCheckboxes(this) })
})
document.querySelectorAll('.territoire-type-r input[type="checkbox"]').forEach(parentCheckbox => {
  parentCheckbox.addEventListener('change', function () { updateAllRegionalChildCheckboxes(this) })
})

function updateDepartementalChildCheckboxes (target) {
  const parentName = target.dataset.departement
  if (!parentName) return

  const childCheckboxes = document.querySelectorAll(`input[data-parent='${parentName}']`)
  childCheckboxes.forEach(child => {
    child.checked = target.checked
  })
}

function updateAllRegionalChildCheckboxes (target) {
  const parentName = target.dataset.region
  if (!parentName) return

  const childCheckboxes = document.querySelectorAll(`input[data-parent='${parentName}']`)
  childCheckboxes.forEach(child => {
    child.indeterminate = false
    child.checked = target.checked

    const departementName = child.dataset.departement
    if (!departementName) return

    const grandChildCheckboxes = document.querySelectorAll(`input[data-parent='${departementName}']`)
    grandChildCheckboxes.forEach(grandChild => {
      grandChild.checked = target.checked
      grandChild.checked = target.checked
    }
    )
  })
}

// Initialisation de l'état des parents au chargement
updateDepartementalCheckboxStatesFromItsArrondissements()
updateRegionalCheckboxFromDepartement()
