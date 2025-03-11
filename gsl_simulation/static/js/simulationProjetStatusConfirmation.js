'use strict';

let selectedElement = null;

const VALID = "valid";
const CANCELLED = "cancelled";
const DISMISSED = "dismissed";
const PROCESSING = "draft";
const PROVISOIRE = "provisoire";

const STATUSES_WITH_OTHER_SIMULATION_IMPACT = [VALID, CANCELLED, DISMISSED];

const STATUS_TO_MODAL_ID = {
    "valid": "accept-confirmation-modal",
    "cancelled": "refuse-confirmation-modal",
    "draft": "processing-confirmation-modal",
    "dismissed": "dismiss-confirmation-modal",
    "provisoire": "provisoire-confirmation-modal",
}

const STATUS_TO_FRENCH_WORD = {
    "valid": "validé",
    "cancelled": "refusé",
    "dismissed": "classé sans suite",
}

function mustOpenConfirmationModal(newValue, originalValue) {
    if (STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(newValue)) return true;
    if (newValue === PROCESSING && STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(originalValue)) return true;
    if (newValue === PROVISOIRE && STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(originalValue)) return true;
    return false;
}

function replaceInitialStatusModalContentText(originalValue, modalContentId) {
    const confirmationModalContent = document.getElementById(modalContentId)
    confirmationModalContent.querySelector(".initial-status").innerHTML= STATUS_TO_FRENCH_WORD[originalValue]
}

function handleStatusChange(select, originalValue) {
    if (mustOpenConfirmationModal(select.value, originalValue)) {
        showConfirmationModal(select, originalValue);
    } else {
        htmx.trigger(select.form, 'status-confirmed');  // Déclenche le PATCH HTMX
    }
}

function showConfirmationModal(select, originalValue) {
    const status = select.value;
    const modalId = STATUS_TO_MODAL_ID[status];
    if (modalId === undefined) {
        return
    }
    selectedElement = select;
    if ([PROCESSING, PROVISOIRE].includes(status)) {
        replaceInitialStatusModalContentText(originalValue, `${status}-confirmation-modal-content`)
    }

    const modal = document.getElementById(modalId)
    dsfr(modal).modal.disclose()
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId)
    selectedElement.form.reset()
    dsfr(modal).modal.conceal()
    selectedElement.focus()
    selectedElement = null;
}
document.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener('click', () => {
        closeModal(el.dataset.closeModal);
    });
})
document.querySelectorAll('#confirmChange').forEach((e) => {
    e.addEventListener('click', function () {
        if (selectedElement) {
            selectedElement.form.submit();
        }
        else {
            closeModal();
        }
    })
});

document.querySelector(".gsl-projet-table").addEventListener("change", (ev) => {
    let target = ev.target;
    if (!target.classList.contains("status-select")) {
        return;
    }
    return handleStatusChange(target, target.value);
})