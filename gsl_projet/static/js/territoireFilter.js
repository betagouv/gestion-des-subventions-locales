document.querySelectorAll('#filter-territoire .territoire-type-a').forEach(checkbox => {
  checkbox.addEventListener('change', updateParentState);
})

const parentCheckbox = document.querySelector(".territoire-type-d input[type='checkbox']");
const childCheckboxes = document.querySelectorAll(".territoire-type-a input[type='checkbox']");

function updateParentState(event) {
  const checkedChildren = [...childCheckboxes].filter(checkbox => checkbox.checked);

 if (checkedChildren.length === 0) {
      parentCheckbox.checked = false;
      parentCheckbox.classList.remove("indeterminate");
  } else if (checkedChildren.length === childCheckboxes.length) {
      parentCheckbox.checked = true;
      parentCheckbox.classList.remove("indeterminate");
  } else {
      parentCheckbox.checked = false;
      parentCheckbox.classList.add("indeterminate");
  }
}
  childCheckboxes.forEach(checkbox => {
    checkbox.addEventListener("change", updateParentState);
});

parentCheckbox.addEventListener("change", function () {
    const isChecked = parentCheckbox.checked;
    childCheckboxes.forEach(child => {
        child.checked = isChecked;
    });
    updateParentState();
})

updateParentState()