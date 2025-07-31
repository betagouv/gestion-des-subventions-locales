document.addEventListener('DOMContentLoaded', function() {
  modal = document.querySelector("#delete-modele-arrete")
  form = document.querySelector("#delete-modele-arrete-form")
  document.querySelectorAll("button[data-modele-name]").forEach(btn => btn.addEventListener("click", (evt) => {
    if (modal){
      modal.querySelector(".modal-title").innerText = "Suppression du modèle d’arrêté “"+ btn.dataset.modeleName  + "“"
    }
    if (form){
      form.setAttribute("action",btn.dataset.actionForm)
    }
    }))
})