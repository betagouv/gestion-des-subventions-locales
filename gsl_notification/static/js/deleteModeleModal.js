import { Controller } from "stimulus"

export class DeleteModeleModal extends Controller {
  connect(){
    this.modal = document.querySelector("#delete-modele-arrete")
    this.form = document.querySelector("#delete-modele-arrete-form")
  }

  updateModaleTitleAndSubmitAction(evt){
    let btn = evt.target
    if (this.modal){
      let type = btn.dataset.modeleType;
      let title = "Suppression du modèle d’arrêté “"+ btn.dataset.modeleName  + "“"
      if (type ===  "lettre"){
        title = "Suppression du modèle de lettre de notification “"+ btn.dataset.modeleName  + "“"
      }
      this.modal.querySelector(".modal-title").innerText = title
    }
    if (this.form){
      this.form.setAttribute("action",btn.dataset.actionForm)
    }
  }
}