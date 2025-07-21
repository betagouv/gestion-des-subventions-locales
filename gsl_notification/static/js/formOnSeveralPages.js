'use strict';

document.addEventListener('DOMContentLoaded', function remove_required_when_going_at_previous_step() {
    const form = document.getElementById('multipage_form');
    const previous_button = document.getElementById("previous_button");
    if (!previous_button) {
        return;
    }

    previous_button.addEventListener("click", function() {
        form.querySelectorAll("[required]").forEach(function (element) {
            element.required = false;
        })
    })
})