document.addEventListener('DOMContentLoaded', function() {
  modal = document.querySelector("#delete-modele-arrete")
  form = document.querySelector("#delete-modele-arrete-form")
  document.querySelectorAll("button[data-modele-name]").forEach(btn => btn.addEventListener("click", (evt) => {
    if (modal){
      let type = btn.dataset.modeleType;
      let title = "Suppression du modèle d’arrêté “"+ btn.dataset.modeleName  + "“"
      if (type ===  "lettre"){
        title = "Suppression du modèle de lettre de notification “"+ btn.dataset.modeleName  + "“"
      }
      modal.querySelector(".modal-title").innerText = title
    }
    if (form){
      form.setAttribute("action",btn.dataset.actionForm)
    }
    }))
})