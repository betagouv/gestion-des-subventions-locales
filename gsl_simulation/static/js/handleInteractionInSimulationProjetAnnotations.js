import { disableAllModalButtons, ensureButtonsAreEnabled } from "./modules/utils.js"


// for modal
let deleteModal = null;
let cancelModal = null;
let cancelUpdateButton = null;

let addForm = null;
const formStates = {};

let selectedForm = null;
let selectedModal = null;


function closeModal({ cancelling = false } = {}) {
    if (!selectedForm) return;

    dsfr(selectedModal).modal.conceal();
    selectedForm.focus();
    if (cancelling) {
        formStates[selectedForm.id] = false;
        if (cancelUpdateButton) htmx.trigger(cancelUpdateButton, 'cancel');
        cancelUpdateButton = undefined
    }
    selectedForm = null;
    selectedModal = null;
}

function openDeleteConfirmationDialog() {
    if (!selectedForm) return;
    selectedModal = deleteModal;
    const noteTitle = selectedForm.dataset.noteTitle || '';
    deleteModal.querySelector('#modal-title').textContent = `Suppression de ${noteTitle}`;
    ensureButtonsAreEnabled(deleteModal);
    dsfr(deleteModal).modal.disclose();
}

function openConfirmationModal(formTemp) {
    selectedForm = formTemp;
    selectedModal = cancelModal;
    ensureButtonsAreEnabled(cancelModal);
    dsfr(cancelModal).modal.disclose();
}

function handleFormInput(formId) {
    formStates[formId] = true;
}

function handleFormSubmit(formId) {
    formStates[formId] = false;
}

function handleFormKeydown(event) {
    // Maj+Entrée ou Cmd+Entrée pour soumettre
    if (event.key === "Enter" && (event.shiftKey || event.metaKey)) {
        event.preventDefault();
        event.target.form.submit();
    }
}

function addListenersToForm(formElem) {
    const formId = formElem.id;
    formElem.addEventListener('input', () => { handleFormInput(formId) });
    formElem.addEventListener('submit', () => { handleFormSubmit(formId) });
    formElem.addEventListener("keydown", (event) => handleFormKeydown(event))

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
        formElem.addEventListener('input', () => handleFormInput(formElem.id));
        formElem.addEventListener('submit', () => handleFormSubmit(formElem.id));
    });
}

function isAnyDirtyForm() {
    return Object.values(formStates).some(v => v === true)
}

document.addEventListener('DOMContentLoaded', () => {
    addForm = document.querySelector("#projet_note_form");
    const addNoteButton = document.querySelector('#add_note_button');
    deleteModal = document.getElementById('delete-confirmation-modal');
    cancelModal = document.getElementById('cancel-update-confirmation-modal');

    if (addNoteButton && addForm) {
        addNoteButton.addEventListener('click', () => {
            addForm.style.display = "block";
        });
    }

    if (addForm) {
        const error = document.querySelector(".fr-error-text");
        if (error) addForm.style.display = "block";
        addForm.addEventListener("keydown", handleFormKeydown);
        addForm.addEventListener('input', () => handleFormInput(addForm.id));
        addForm.addEventListener('submit', () => handleFormSubmit(addForm.id));
    }

    document.querySelectorAll('.delete_note_button').forEach(button => {
        button.addEventListener('click', event => {
            event.preventDefault();
            selectedForm = event.target.closest('form');
            openDeleteConfirmationDialog();
        });
    });

    if (deleteModal) {
        const confirmDeleteButton = deleteModal.querySelector('#confirm');
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
        const confirmCancelButton = cancelModal.querySelector('#confirm');
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
    if (isAnyDirtyForm()) {
        e.preventDefault();
        e.returnValue = '';
    }
});