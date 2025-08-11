import { Controller } from "stimulus"

export class ChooseDocumentType extends Controller {
  static targets = ["radio", "button"]
  static values = {
    radioSelected: String
  }

  setSelectedValue(evt){
    this.radioSelectedValue = evt.target.value;
    console.log(this.radioSelectedValue)
    this.buttonTarget.href = this.buttonTarget.dataset.href + this.radioSelectedValue
  }

  // next() {
  //   console.log(this.buttonTarget.dataset.href)
  //   window.location.href = this.buttonTarget.dataset.href
  // }
}