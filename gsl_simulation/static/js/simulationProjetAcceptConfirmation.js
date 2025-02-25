let selectedElement = null;

function handleStatusChange(select) {
    if (select.value === "valid") {
        showConfirmationModal(select);
    } else {
        htmx.trigger(select.form, 'status-confirmed');  // Déclenche le PATCH HTMX
    }
}

function showConfirmationModal(select) {
    selectedElement = select;
    modal = document.getElementById('accept-confimation-modal')
    dsfr(modal).modal.disclose()
}

function closeModal() {
    modal = document.getElementById('accept-confimation-modal')
    selectedElement.form.reset()
    dsfr(modal).modal.conceal()
    selectedElement.focus()
    selectedElement = null;
}

document.getElementById('confirmChange').addEventListener('click', function () {
    if (selectedElement) {
        selectedElement.form.submit();
    }
    else {
        closeModal();
    }
});