
document.addEventListener('DOMContentLoaded', function () {
  const form = document.querySelector("#projet_note_form");
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
      form.submit();          // soumet le formulaire
    }
  }

  const input = form.querySelector("input");
  const textarea = form.querySelector("textarea");
  form.addEventListener("keydown", function (event) {
    submitForm(event);
  });
  // textarea.addEventListener("keydown", function (event) {
  //   submitForm(event);
  // });
})