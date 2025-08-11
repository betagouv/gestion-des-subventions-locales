import { Controller } from "stimulus"

export class ChooseDocumentType extends Controller {
  static targets = ["radio", "button"]
  static values = {
    radioSelected: String
  }

  setSelectedValue(evt){
    this.radioSelectedValue = evt.target.value;
    this.buttonTarget.href = this.buttonTarget.dataset.href.replace("type", this.radioSelectedValue)
  }
}