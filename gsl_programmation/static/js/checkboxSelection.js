import { Controller } from "stimulus"

export class CheckboxSelection extends Controller {
  static values = {
   allCheckboxesSelected: {type:Boolean, default: false},
  }

  static targets = [ "globalButton", "button" ]

  connect(){
    console.log("Connect, this.globalButtonTarget.checked :", this.globalButtonTarget.checked)
    this.allCheckboxesSelectedValue = this.globalButtonTarget.checked
  }

  toggle(){
    const newValue = !this.allCheckboxesSelectedValue
    console.log("TOGGLE ", this.allCheckboxesSelectedValue, " => ", newValue)
    this.allCheckboxesSelectedValue = newValue
    if (newValue) {
      this._updateAllCheckboxes(true)
    }
    else {
      this._updateAllCheckboxes(false)
    }
  }

  updateAllCheckboxesSelected(evt){
    const eltValue = evt.target.checked
    if (eltValue == false){
      this.allCheckboxesSelectedValue = false
    }
    else {
      if (this.buttonTargets.every(b => b.checked)) {
        this.allCheckboxesSelectedValue = true
      }
    }
    
  }

  allCheckboxesSelectedValueChanged() {
    console.log("allCheckboxesSelectedValueChanged", this.allCheckboxesSelectedValue)
    this._updateACheckbox(this.globalButtonTarget, this.allCheckboxesSelectedValue)
  }

  _updateAllCheckboxes(value) {
    console.log("_updateAllCheckboxes", value)
    this.buttonTargets.forEach(element => this._updateACheckbox(element, value));
  }

  _updateACheckbox(elt, value){
    elt.checked= value
    elt.setAttribute("data-fr-js-checkbox-input", value)
  }
}