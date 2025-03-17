'use strict'

if (htmx !== undefined) {
    document.querySelector(".gsl-projet-table").addEventListener("change", (ev) => {
        if (ev.target.hasAttribute("hx-post") && !ev.target.disabled) {
            htmx.trigger(ev.target, 'change');
            ev.preventDefault();
        }
    })

    document.querySelector(".gsl-projet-table").addEventListener("submit", (ev) => {
        ev.preventDefault()
    })
}

