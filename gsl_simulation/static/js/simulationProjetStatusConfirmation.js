let selectedElement = null;

const VALID = "valid";
const CANCELLED = "cancelled";
const DISMISSED = "dismissed";
const PROCESSING = "draft";
const PROVISOIRE = "provisoire";

const STATUSES_WITH_OTHER_SIMULATION_IMPACT = [VALID, CANCELLED, DISMISSED];

STATUS_TO_MODAL_ID = {
    "valid": "accept-confirmation-modal",
    "cancelled": "refuse-confirmation-modal",
    "draft": "processing-confirmation-modal",
    "dismissed": "dismiss-confirmation-modal",
    "provisoire": "provisoire-confirmation-modal",
}

STATUS_TO_FRENCH_WORD = {
    "valid": "validé",
    "cancelled": "annulé",
    "dismissed": "classé sans suite",
}

function mustOpenConfirmationModal(newValue, originalValue) {
    if (STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(newValue)) return true;
    if (newValue === PROCESSING && STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(originalValue)) return true;
    if (newValue === PROVISOIRE && STATUSES_WITH_OTHER_SIMULATION_IMPACT.includes(originalValue)) return true;
    return false;
}

function replaceProcessingModalContentText(originalValue, modalContentId) {
    processingConfirmationModalContent = document.getElementById(modalContentId)
    const newText = processingConfirmationModalContent.innerHTML.replace("TO_REPLACE", STATUS_TO_FRENCH_WORD[originalValue])
    processingConfirmationModalContent.innerHTML = newText
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
        replaceProcessingModalContentText(originalValue, `${status}-confirmation-modal-content`)
    }

    modal = document.getElementById(modalId)
    dsfr(modal).modal.disclose()
}

function closeModal(modalId) {
    modal = document.getElementById(modalId)
    selectedElement.form.reset()
    dsfr(modal).modal.conceal()
    selectedElement.focus()
    selectedElement = null;
}

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