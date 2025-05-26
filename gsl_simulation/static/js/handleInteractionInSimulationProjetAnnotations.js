import { disableAllModalButtons, ensureButtonsAreEnabled } from "./modules/utils.js"

let isFormDirty = false;
const formStates = {};
let mainForm = null;
let selectedForm = null;
let selectedModal = null;
let deleteModal = null;
let cancelModal = null;
let cancelUpdateButton = null;

function closeModal({ reset = false, cancelling = false } = {}) {
    if (!selectedForm) return;

    if (reset) selectedForm.reset();
    dsfr(selectedModal).modal.conceal();
    selectedForm.focus();
    selectedForm = null;
    selectedModal = null;
    if (cancelling) {
        isFormDirty = false;
        if (cancelUpdateButton) htmx.trigger(cancelUpdateButton, 'cancel');
        cancelUpdateButton = undefined
    }
}

function openDeleteConfirmationDialog() {
    if (!selectedForm) return;
    selectedModal = deleteModal;
    const noteTitle = selectedForm.dataset.noteTitle || '';
    deleteModal.querySelector('#delete-note-modal-title').textContent = `Suppression de ${noteTitle}`;
    ensureButtonsAreEnabled(deleteModal);
    dsfr(deleteModal).modal.disclose();
}

function openConfirmationModal(formTemp) {
    selectedForm = formTemp;
    selectedModal = cancelModal;
    ensureButtonsAreEnabled(cancelModal);
    dsfr(cancelModal).modal.disclose();
}

function handleFormInput() {
    isFormDirty = true;
}

function handleFormSubmit() {
    isFormDirty = false;
}

function handleFormKeydown(event) {
    // Maj+Entrée ou Cmd+Entrée pour soumettre
    if (event.key === "Enter" && (event.shiftKey || event.metaKey)) {
        event.preventDefault();
        isFormDirty = false;
        event.target.form.submit();
    }
}

function addListenersToForm(formElem) {
    const formId = formElem.id;
    formElem.addEventListener('input', () => { formStates[formId] = true; });
    formElem.addEventListener('submit', () => { formStates[formId] = false; });

    formElem.querySelectorAll(".cancel-button").forEach(button => {
      button.addEventListener('click', evt => {
            evt.preventDefault();
            cancelUpdateButton = button;
            if (formStates[formId]) {
                openConfirmationModal(formElem);
            } else {
                htmx.trigger(button, 'cancel');
            }
        });
    });
}

function initFormChangeWatcher() {
    const forms = document.querySelectorAll(".projet_note_update_form");
    forms.forEach(formElem => {
        formElem.addEventListener('input', handleFormInput);
        formElem.addEventListener('submit', handleFormSubmit);
    });
    const isThereNoFormDisplayed = forms.length === 0;
    const isProjetNoteFormHidden = mainForm && window.getComputedStyle(mainForm).display === "none";
    if (isThereNoFormDisplayed && isProjetNoteFormHidden) {
        isFormDirty = false;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    mainForm = document.querySelector("#projet_note_form");
    const addNoteButton = document.querySelector('#add_note_button');
    deleteModal = document.getElementById('delete-confirmation-modal');
    cancelModal = document.getElementById('cancel-update-confirmation-modal');

    if (addNoteButton && mainForm) {
        addNoteButton.addEventListener('click', () => {
            mainForm.style.display = "block";
        });
    }

    if (mainForm) {
        const error = document.querySelector(".fr-error-text");
        if (error) mainForm.style.display = "block";
        mainForm.addEventListener("keydown", handleFormKeydown);
        mainForm.addEventListener('input', handleFormInput);
        mainForm.addEventListener('submit', handleFormSubmit);
    }

    document.querySelectorAll('.delete_note_button').forEach(button => {
        button.addEventListener('click', event => {
            event.preventDefault();
            selectedForm = event.target.closest('form');
            openDeleteConfirmationDialog();
        });
    });

    if (deleteModal) {
        const confirmDeleteButton = deleteModal.querySelector('#confirm-delete-note');
        if (confirmDeleteButton) {
            confirmDeleteButton.addEventListener('click', () => {
                disableAllModalButtons(deleteModal);
                if (selectedForm) selectedForm.submit();
            });
        }
    }

    document.querySelectorAll('.close-modal').forEach(button => {
        button.addEventListener('click', event => {
            event.preventDefault();
            closeModal();
        });
    });

    if (cancelModal) {
        const confirmCancelButton = cancelModal.querySelector('#confirm-cancel-update');
        if (confirmCancelButton) {
            confirmCancelButton.addEventListener('click', evt => {
                evt.preventDefault();
                disableAllModalButtons(cancelModal);
                closeModal({ cancelling: true });
            });
        }
    }
});

document.body.addEventListener("htmx:afterSwap", evt => {
    initFormChangeWatcher();
    const updateForm = evt.target.querySelector(".projet_note_update_form");
    if (updateForm) addListenersToForm(updateForm);
    const deleteButton = evt.target.querySelector('.delete_note_button')
    if (deleteButton) {
      deleteButton.addEventListener('click', event => {
            event.preventDefault();
            selectedForm = event.target.closest('form');
            openDeleteConfirmationDialog();
        });
    }
});

// Avant de quitter ou rafraîchir la page
window.addEventListener('beforeunload', e => {
    if (isFormDirty) {
        e.preventDefault();
        e.returnValue = '';
    }
});