import { Controller } from 'stimulus'

// Attached to a form that fills a DSFR modal through htmx. The modal must open
// on submit rather than when the response arrives, otherwise clicking seems to
// do nothing while the request runs. The submit button can't double as the
// modal's DSFR disclosure button, so click the hidden one instead.
export class OpenModalOnSubmit extends Controller {
  static values = { buttonId: String }

  open () {
    document.getElementById(this.buttonIdValue)?.click()
  }
}
