import { Controller } from 'stimulus'

export class SkipDocumentToggle extends Controller {
  static targets = ['select', 'checkbox']

  connect () {
    this._sync()
  }

  toggle () {
    this._sync()
  }

  _sync () {
    this.selectTarget.disabled = this.checkboxTarget.checked
  }
}
