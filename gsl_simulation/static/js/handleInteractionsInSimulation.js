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
  
    if (xhr.status == 400) {
        evt.detail.elt.form.reset()
    }
  });
  