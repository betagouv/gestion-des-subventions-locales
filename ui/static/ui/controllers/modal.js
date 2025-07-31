import { Controller } from "stimulus"

export class Modal extends Controller {
  static values = {
    formId: String,
    dialogId: String
  }

  connect(){
    this.form = this._getForm()
    this.dialog = this._getDialog()
  }

  close(evt) {
    evt.preventDefault();
    dsfr(this.dialog).modal.conceal();
    this.form.reset();
    this.form.focus();
  }

  submit(evt) {
    evt.preventDefault();
    this.dialog.querySelectorAll("button").forEach(btn => btn.disabled = true);
    this.form.submit();
  }


  // Private
  _getForm() {
    if (this.hasFormIdValue){
      const form = document.getElementById(this.formIdValue)
      if (!Boolean(form)){
        throw new Error("No form found with formId : " + this.formIdValue)
      }
      return form
    }
    else {
      throw new Error("No formId")

    }
  }

  _getDialog() {
    if (this.hasDialogIdValue){
      const dialog = document.getElementById(this.dialogIdValue)
      if (!Boolean(dialog)){
        throw new Error("No dialog found with dialogId : " + this.dialogIdValue)
      }
      return dialog
    }
    else {
      throw new Error("No dialogId")

    }
  }
}
