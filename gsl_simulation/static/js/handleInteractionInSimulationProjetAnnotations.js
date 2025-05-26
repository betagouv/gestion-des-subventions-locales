import { disableAllModalButtons, ensureButtonsAreEnabled } from "./modules/utils.js"

let isFormDirty = false;
let form = undefined;
let selectedForm = null;
let modalId = undefined;
let modal = undefined;

function closeModal() {
    if (selectedForm === undefined) {
        return
    }

    selectedForm.reset()
    dsfr(modal).modal.conceal()
    selectedForm.focus()
    selectedForm = undefined;
    modalId = undefined;
}


const openDeleteConfirmationDialog = () => {
  const noteTitle = selectedForm.dataset.noteTitle;
  modal.querySelector('#delete-note-modal-title').textContent = `Suppression de ${noteTitle}`;
  ensureButtonsAreEnabled(modal)
  dsfr(modal).modal.disclose()
}

document.addEventListener('DOMContentLoaded', function () {
  form = document.querySelector("#projet_note_form");
  const addNoteButton = document.querySelector('#add_note_button')

  if (addNoteButton){
    addNoteButton.addEventListener('click', (ev) => {
      form.style.display="block";

    })
  }

  const error = document.querySelector(".fr-error-text")
  if (error) {
    form.style.display="block";
  }

  function submitForm(event) {
  // Vérifie si Maj (Shift) + Entrée sont pressés
    if (event.key === "Enter" && (event.shiftKey || event.metaKey)) {
      event.preventDefault(); // empêche d'ajouter un saut de ligne
      isFormDirty = false;
      form.submit();
    }
  }

  form.addEventListener("keydown", function (event) {
    submitForm(event);
  });

  form.addEventListener('input', function () {
    isFormDirty = true;
  });

  form.addEventListener('submit', function () {
    isFormDirty = false;
  });

  modal = document.getElementById('delete-confirmation-modal');

  const deleteButtons = document.querySelectorAll('.delete_note_button');
  deleteButtons.forEach(function (button) {
    button.addEventListener('click', function (event) {
      event.preventDefault();
      selectedForm = event.target.closest('form');
      openDeleteConfirmationDialog(selectedForm);
  });

  const confirmDeleteButton = document.querySelector('#confirm-delete-note');
  confirmDeleteButton.addEventListener('click', function () {
      disableAllModalButtons(modal)
      selectedForm.submit();
      })
  });

  const cancelDeleteButtons = document.querySelectorAll('.close-modal');
  cancelDeleteButtons.forEach(function (button) {
    button.addEventListener('click', function (event) {
      event.preventDefault();
      closeModal();
    });
  });
})

function initFormChangeWatcher() {
    const forms = document.querySelectorAll(".projet_note_update_form");
    forms.forEach(form => {
      if (form) {
          form.addEventListener('input', function () {
              isFormDirty = true;
          });

          form.addEventListener('submit', function () {
              isFormDirty = false;
          });
      }
    });
    const isThereNoFormDisplayed = forms.length == 0
    const isProjetNoteFormHidden = window.getComputedStyle(form).display === "none";
    if (isThereNoFormDisplayed && isProjetNoteFormHidden) {
      isFormDirty = false;
    }
}

document.body.addEventListener("htmx:afterSwap", function(evt) {
    // Formulaire injecté : on attache la logique de détection de changements
    initFormChangeWatcher();  
});



    
// Avant de quitter ou rafraîchir la page
window.addEventListener('beforeunload', function (e) {
  if (isFormDirty) {
    e.preventDefault(); // Nécessaire pour certains navigateurs
  }
})