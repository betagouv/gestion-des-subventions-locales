import { Controller } from "stimulus"


const TYPE_TO_TITLE = {
  "modele_arrete": "du modèle d’arrêté",
  "modele_lettre": "du modèle de lettre de notification",
  "arrete":"de l'arrêté",
  "lettre":"de la lettre de notification",
  "arrete_signe":"de l'arrêté signé",
  "annexe":"de l'annexe"
}


const TYPE_TO_BODY = {
  "modele_arrete": "Êtes-vous sûr de vouloir supprimer ce modèle d'arrêté ?<br><b>⚠️ Les autres utilisateurs ayant accès à ce modèle ne pourront plus l’utiliser ni le voir.</b>",
  "modele_lettre": "Êtes-vous sûr de vouloir supprimer ce modèle de lettre de notification ?<br><b>⚠️ Les autres utilisateurs ayant accès à ce modèle ne pourront plus l’utiliser ni le voir.</b>",
  "arrete": "Êtes-vous sûr de vouloir supprimer cet arrêté ?<br>Cette action est irréversible.",
  "lettre": "Êtes-vous sûr de vouloir supprimer cette lettre de notification ?<br>Cette action est irréversible.",
  "arrete_signe": "Êtes-vous sûr de vouloir supprimer cet arrêté signé ?<br>Cette action est irréversible.",
  "annexe": "Êtes-vous sûr de vouloir supprimer cette annexe ?<br>Cette action est irréversible."
}

export class DeleteNotificationDocumentModal extends Controller {
  static values = {
    modalId:String,
    formId:String
  }

  connect(){
    console.log("this.modalIdValue", this.modalIdValue)
    console.log("this.formIdValue", this.formIdValue)
    this.modal = document.getElementById(this.modalIdValue)
    this.form = document.getElementById(this.formIdValue)
    console.log(this.modal)
    console.log(this.form)
  }

  updateModaleTitleAndSubmitAction(evt){
    let btn = evt.target
    if (this.modal){
      let type = btn.dataset.type;
      console.log(type)
      let title = "Suppression " + TYPE_TO_TITLE[type] + " “" + btn.dataset.name + "“"
      this.modal.querySelector(".modal-title").innerText = title;
      this.modal.querySelector(".modal-body").innerHTML = TYPE_TO_BODY[type]
    }
    if (this.form){
      console.log(btn.dataset.actionForm)
      this.form.setAttribute("action", btn.dataset.actionForm)
    }
  }
}