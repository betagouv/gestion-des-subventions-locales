import { Controller } from 'stimulus'

// Attached to a DSFR <dialog>. htmx polling (hx-trigger="every ...") started
// while the dialog was open otherwise keeps ticking in the background once
// the user closes it (close button, backdrop click, Escape) — DSFR only
// hides the dialog, it doesn't remove it or its content from the DOM.
//
// On the dialog's "dsfr.conceal" event, discard any polling element found
// inside it: replacing it with an empty placeholder (same id, so it stays
// available as an hx-target next time the dialog's flow is relaunched)
// removes it from the DOM, which is what makes htmx stop rescheduling it.
export class CancelPollOnModalClose extends Controller {
  cancel () {
    this.element.querySelectorAll('[hx-trigger*="every"]').forEach((elt) => {
      const placeholder = document.createElement('div')
      if (elt.id) placeholder.id = elt.id
      elt.replaceWith(placeholder)
    })
  }
}
