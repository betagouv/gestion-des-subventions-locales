'use strict';

let selectedElement = undefined;
let modalId = undefined

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

function handleStatusChangeWithHtmx(select, originalValue) {
    if (mustOpenConfirmationModal(select.value, originalValue)) {
        showConfirmationModal(select, originalValue);
    } else {
        if (typeof htmx !== 'undefined') htmx.trigger(select.form, 'status-confirmed');  // Déclenche le PATCH HTMX
        else select.form.submit();
    }
}

function handleStatusChange(select, originalValue) {
    if (mustOpenConfirmationModal(select.value, originalValue)) {
        showConfirmationModal(select, originalValue);
    } else {
        select.form.submit();
    }
}

function showConfirmationModal(select, originalValue) {
    const status = select.value;
    modalId = STATUS_TO_MODAL_ID[status];
    if (modalId === undefined) {
        console.log("No modal for this status", status)
        return
    }
    selectedElement = select;
    if ([PROCESSING, PROVISOIRE].includes(status)) {
        const modalContentId = `${status}-confirmation-modal-content`
        _replaceInitialStatusModalContentText(originalValue, modalContentId)
        if (originalValue === DISMISSED) _removeFromProgrammationText(modalContentId)
    }

    const modal = document.getElementById(modalId)
    dsfr(modal).modal.disclose()
}


function _replaceInitialStatusModalContentText(originalValue, modalContentId) {
    const confirmationModalContent = document.getElementById(modalContentId)
    const newText = STATUS_TO_FRENCH_WORD[originalValue]
    confirmationModalContent.querySelector(".initial-status").innerHTML= newText
}

function _removeFromProgrammationText(modalContentId) {
    const confirmationModalContent = document.getElementById(modalContentId)
    try {
        confirmationModalContent.querySelector(".remove-from-programmation").remove()
    }
    catch (e) {
        console.log("No element to remove")
    }
}

function closeModal() {
    if (modalId === undefined) {
        return
    }

    const modal = document.getElementById(modalId)
    selectedElement.form.reset()
    dsfr(modal).modal.conceal()
    selectedElement.focus()
    selectedElement = undefined;
    modalId = undefined;
}

document.querySelectorAll(".close-modal").forEach((el) => {
    el.addEventListener('click', () => {
        closeModal();
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

document.addEventListener('keydown', function(event) {
    if (event.key === 'Enter' && selectedElement) {
        selectedElement.form.submit();
    }
    if (event.key === "Escape" && selectedElement) {
        closeModal()
    }
});
