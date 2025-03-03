let selectedElement = null;

const VALID = "valid";
const CANCELLED = "cancelled";
const PROCESSING = "draft";

STATUS_TO_MODAL_ID = {
    "valid": "accept-confirmation-modal",
    "cancelled": "refuse-confirmation-modal",
    "draft": "processing-confirmation-modal",
}

STATUS_TO_FRENCH_WORD = {
    "valid": "validé",
    "cancelled": "annulé",
}

function mustOpenConfirmationModal(newValue, originalValue) {
    if ([VALID, CANCELLED].includes(newValue)) return true;
    if (newValue === PROCESSING && (originalValue === VALID || originalValue === CANCELLED)) return true;
    return false;
}

function replaceProcessingModalContentText(originalValue) {
    processingConfirmationModalContent = document.getElementById("processing-confirmation-modal-content")
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
    if (status === PROCESSING) {
        replaceProcessingModalContentText(originalValue)
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