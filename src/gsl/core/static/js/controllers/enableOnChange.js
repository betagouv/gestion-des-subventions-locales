import { Controller } from 'stimulus'

// Enables a form's (disabled) submit buttons once one of its fields changes.
// Works both for buttons inside the form and for buttons linked via a `form`
// attribute (scattered inputs sharing a hidden <form>).
export class EnableOnChange extends Controller {
  enable (evt) {
    const form = evt.target.form
    if (!form) return
    const selector = "button[type='submit']"
    form.querySelectorAll(selector).forEach(btn => { btn.disabled = false })
    if (form.id) {
      document
        .querySelectorAll(`${selector}[form='${form.id}']`)
        .forEach(btn => { btn.disabled = false })
    }
  }
}
