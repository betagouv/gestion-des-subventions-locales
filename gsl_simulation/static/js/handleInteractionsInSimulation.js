'use strict'

document.querySelector(".gsl-projet-table").addEventListener("change", (ev) => {
    if (ev.target.hasAttribute("hx-post") && !ev.target.disabled) {
        if (typeof htmx !== 'undefined') {
            htmx.trigger(ev.target, 'change');
        }
        else {
            ev.target.form.submit();
        }
        ev.preventDefault();
    }
})

document.querySelector(".gsl-projet-table").addEventListener("submit", (ev) => {
    ev.preventDefault()
})

document.querySelector(".gsl-projet-table").addEventListener("change", (ev) => {
    let target = ev.target;
    if (!target.classList.contains("status-select")) {
        return;
    }
    return handleStatusChangeWithHtmx(target, target.dataset.originalValue);
})

document.addEventListener('htmx:responseError', evt => {
    const xhr = evt.detail.xhr;
  
    if (xhr.status >= 400) {
        evt.detail.elt.form.reset()
    }
  });
  

// Dotation Update
let selectedForm = undefined
// Toggle dropdowns
document.querySelectorAll('.dotation-dropdown button').forEach(button => {
    button.addEventListener('click', function (event) {
        event.stopPropagation();
        let content = this.nextElementSibling;
        if (content) {
            let wasContentDisplayed = content.style.display === 'grid'
            content.style.display = wasContentDisplayed ? 'none' : 'grid';
            if (wasContentDisplayed) {
                selectedElement = content;
                selectedForm = content.closest("form")
                let fieldset = content.closest("fieldset")
                let initialValues = content.dataset.initialDotations.split(",")
                handleDotationChange(selectedForm, fieldset, initialValues)
            }
              
        }
    });
});

// // Close dotation dropdowns + handle change when clicking outside
// document.addEventListener('click', function (event) {
//     if (dotationContentSelectedElement) {
//         if (!dotationContentSelectedElement.contains(event.target)) {
            
//             // dotationContentSelectedElement.querySelector('.filter-content').style.display = 'none';
//             // dotationContentSelectedElement = undefined
//         }
//     }
// });
  

// document.querySelector("#submit-dotation").addEventListener("click", (ev) => {
//     ev.preventDefault();
//     selectedElement = ev.target
//     let form = document.querySelector("form#projet_form").closest("form")
//     let fieldset = document.querySelector("#dotation-fieldset")
//     const initalDotationValues = selectedElement.dataset.initialDotations.split(",")
//     handleDotationChange(form, fieldset, initalDotationValues)
//   });
  

document.querySelector("#confirm-dotation-update").addEventListener("click", (ev) => {
    selectedForm.submit()
    closeModal()
  })