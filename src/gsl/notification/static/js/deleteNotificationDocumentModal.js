import { Controller } from 'stimulus'

export class DeleteNotificationDocumentModal extends Controller {
  static values = {
    modalId: String,
    formId: String,
    warning: String
  }

  connect () {
    this.modal = document.getElementById(this.modalIdValue)
    this.form = document.getElementById(this.formIdValue)
  }

  updateModaleTitleAndSubmitAction (evt) {
    const btn = evt.target
    if (this.modal) {
      this.modal.querySelector('.modal-title').innerText = btn.dataset.deleteTitle
      this.modal.querySelector('.modal-body').innerHTML = btn.dataset.deleteQuestion + '<br>' + this.warningValue
    }
    if (this.form) {
      this.form.setAttribute('action', btn.dataset.formAction)
    }
  }
}
