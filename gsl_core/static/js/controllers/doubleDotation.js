import { Controller } from "stimulus"

export class DoubleDotation extends Controller {
  static values = {
   initialDotations: {type:Array, default: []},
   selectedDotations: {type:Array, default: []},
  }
  static targets = [ "input", "form" ]

  initialize(){
    this.updateSelectedDotations()
  }

  updateSelectedDotations(){
    const newSelectedDotations = []
    this.inputTargets.forEach(elt => {
      const input = elt.children[0].children[0]
      if (input.checked) {
        newSelectedDotations.push(input.value)
      }
    });
    this.selectedDotationsValue = newSelectedDotations;
  }


  mustOpenConfirmationModal(){
    this.updateSelectedDotations();
    if (this.selectedDotationsValue.length === 0) {
      return false
    }
    if (this.selectedDotationsValue.length === 1 && this.initialDotationsValue.length === 1 && this.selectedDotationsValue[0] === this.initialDotationsValue[0]) {
      return false
    }
    if (this.selectedDotationsValue.length === 2 && this.initialDotationsValue.length === 2) {
      return false
    }
    return true
  }

  sumbit(evt){
    evt.preventDefault();
    if (this.mustOpenConfirmationModal()) {
      this._openConfirmatioModal()
    } else {
      let form = document.querySelector("form#projet_form").closest("form")
      form.submit()
    }
  }

  // Private

  _openConfirmatioModal() {
    modalId = "dotation-confirmation-modal-content"
    let modal = document.getElementById(modalId)
    let message = modal.querySelector(".modal-body")
    let title = modal.querySelector(".modal-title")

    const newTitle = this._getTitle()
    if (newTitle) {
      title.innerText = newTitle
    }
    message.innerHTML = this._getMessage()

    dsfr(modal).modal.disclose()
  }

  _getTitle() {
    if (this.selectedDotationsValue.length === 2) {
      return "Double dotation"
    }
    return "Modification de la dotation"
  }

  _getMessage() {
    if (this.initialDotationsValue.length === 2) {
      if (this.selectedDotationsValue.length === 1) {
        let dotationToRemove = this.initialDotationsValue.filter(dotation => !this.selectedDotationsValue.includes(dotation)).pop()
        return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> Les enveloppes demandées étaient DETR et DSIL. Ce projet sera supprimé des simulations <strong>${dotationToRemove}</strong>.`
      }
    }

    if (this.selectedDotationsValue.length === 2) {
      let newDotation = this.selectedDotationsValue.filter(dotation => !this.initialDotationsValue.includes(dotation)).pop()
      return `Ce projet sera aussi affiché dans les simulations ${newDotation}.`
    }
    if (this.selectedDotationsValue.length === 1 && this.initialDotationsValue.length === 1) {
      let dotationToRemove = this.initialDotationsValue[0]
      let newDotation = this.selectedDotationsValue[0]
      return `<strong>Vous souhaitez modifier la dotation de financement choisie par le demandeur.</strong> L'enveloppe demandée était ${dotationToRemove}, la nouvelle enveloppe attribuée est ${newDotation}. Ce projet sera ajouté dans vos simulations ${newDotation} et sera supprimé des simulations ${dotationToRemove}.`
    }
  }
}
