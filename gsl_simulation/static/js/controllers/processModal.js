import { Controller } from 'stimulus'

export class ProcessModal extends Controller {
  static targets = ['confirmationButton']

  initialize () {
    this.disableButton()
  }

  updateButton (event) {
    console.log(event)
    if (event.target.value.length > 0) {
      this.enableButton()
    } else {
      this.disableButton()
    }
  }

  disableButton () {
    this.confirmationButtonTarget.setAttribute('disabled', '1')
  }

  enableButton () {
    this.confirmationButtonTarget.removeAttribute('disabled')
  }
}
