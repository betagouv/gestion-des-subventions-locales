'use strict'

if (htmx !== undefined) {
    document.querySelector(".gsl-projet-table").addEventListener("keyup", (ev) => {
        if (ev.key !== "Enter") {
            return;
        }

        if (ev.target.hasAttribute("hx-post") && !ev.target.disabled) {
            htmx.trigger(ev.target, 'change');
            ev.preventDefault();
        }
    })

    document.querySelector(".gsl-projet-table").addEventListener("submit", (ev) => {
        ev.preventDefault()
    })
}

