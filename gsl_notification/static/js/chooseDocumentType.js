import { Controller } from 'stimulus'

export class ChooseDocumentType extends Controller {
  static targets = ['radio', 'button']

  connect () {
    this.radioTargets.forEach(elt => {
      if (elt.checked) {
        this._updateHrefButton(elt.value)
      }
    })
  }

  setSelectedValue (evt) {
    this._updateHrefButton(evt.target.value)
  }

  _updateHrefButton (value) {
    this.buttonTarget.href = this.buttonTarget.dataset.href.replace('type', value)
  }
}
