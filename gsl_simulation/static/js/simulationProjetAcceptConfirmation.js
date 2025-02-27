let selectedElement = null;

function handleStatusChange(select) {
    if (["valid", "cancelled"].includes(select.value)) {
        showConfirmationModal(select, select.value);
    } else {
        htmx.trigger(select.form, 'status-confirmed');  // Déclenche le PATCH HTMX
    }
}

function showConfirmationModal(select, status) {
    switch (status) {
        case "valid":
            modalId = 'accept-confirmation-modal';
            break;
        case "cancelled":
            modalId = 'refuse-confirmation-modal';
            break;
    }
    selectedElement = select;
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