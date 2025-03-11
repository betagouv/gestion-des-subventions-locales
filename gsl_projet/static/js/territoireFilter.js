
document.querySelectorAll('.territoire-type-r input[type="checkbox"], .territoire-type-d input[type="checkbox"], .territoire-type-a input[type="checkbox"]').forEach(checkbox => {
  checkbox.addEventListener('change', function() { console.log("changed !", this)});
});

document.querySelectorAll('.territoire-type-a input[type="checkbox"]').forEach(checkbox => {
  checkbox.addEventListener('change', updateDepartementalCheckboxStates);
});
document.querySelectorAll('.territoire-type-d input[type="checkbox"]').forEach(checkbox => {
  checkbox.addEventListener('change', updateRegionalCheckboxStates);
});

function updateRegionalCheckboxStates() {
  document.querySelectorAll('.territoire-type-r input[type="checkbox"]').forEach(parentCheckbox => updateCheckboxState(parentCheckbox));
}

function updateDepartementalCheckboxStates() {
  document.querySelectorAll('.territoire-type-d input[type="checkbox"]').forEach(parentCheckbox => updateDepartementalCheckboxState(parentCheckbox));
}


function updateCheckboxState(checkbox) {
  const parentName = checkbox.dataset.region || checkbox.dataset.departement;
  if (!parentName) return;

  const childCheckboxes = document.querySelectorAll(`input[data-parent='${parentName}']`);
  const checkedChildren = [...childCheckboxes].filter(cb => cb.checked);
  const allChecked = checkedChildren.length === childCheckboxes.length;
  const someChecked = checkedChildren.length > 0 && !allChecked;

  checkbox.checked = allChecked;
  checkbox.indeterminate = someChecked;
}

function updateDepartementalCheckboxState(checkbox){
  updateCheckboxState(checkbox);
  updateRegionalCheckboxStates()
}

// Gestion du clic sur un parent pour cocher/décocher ses enfants
document.querySelectorAll('.territoire-type-r input[type="checkbox"], .territoire-type-d input[type="checkbox"]').forEach(parentCheckbox => {
  parentCheckbox.addEventListener('change', function () {updateDepartementalChildCheckboxes(this)});
});
document.querySelectorAll('.territoire-type-r input[type="checkbox"]').forEach(parentCheckbox => {
  parentCheckbox.addEventListener('change', function () {updateAllRegionalChildCheckboxes(this)});
});

function updateAllRegionalChildCheckboxes(target) {
  const parentName = target.dataset.region || target.dataset.departement;
  if (!parentName) return;

  const childCheckboxes = document.querySelectorAll(`input[data-parent='${parentName}']`);
  childCheckboxes.forEach(child => {
      child.indeterminate = false;
      child.checked = target.checked;
      
      const departementName = child.dataset.departement;
      if (!departementName) return;

      const grandChildCheckboxes = document.querySelectorAll(`input[data-parent='${departementName}']`);
      grandChildCheckboxes.forEach(grandChild => {
          grandChild.checked = target.checked;
          grandChild.checked = target.checked;
      }
      )
  })
}

function updateDepartementalChildCheckboxes(target) {
  const parentName = target.dataset.departement;
  if (!parentName) return;

  const childCheckboxes = document.querySelectorAll(`input[data-parent='${parentName}']`);
  childCheckboxes.forEach(child => {
      child.checked = target.checked;
  })
  
}

// Initialisation de l'état des parents au chargement
updateDepartementalCheckboxStates()
updateRegionalCheckboxStates();
