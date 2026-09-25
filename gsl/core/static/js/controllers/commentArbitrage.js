import { Controller } from 'stimulus'

export class CommentArbitrage extends Controller {
  static targets = ['button', 'display', 'edit']

  showEdit () {
    this.displayTarget.classList.add('fr-hidden')
    this.editTarget.classList.remove('fr-hidden')
    this.buttonTarget.classList.add('fr-hidden')
  }

  showDisplay () {
    this.displayTarget.classList.remove('fr-hidden')
    this.editTarget.classList.add('fr-hidden')
    this.buttonTarget.classList.remove('fr-hidden')
  }

  submitOnCmdEnter (event) {
    if (event.metaKey && event.key === 'Enter') {
      event.preventDefault()
      this.editTarget.querySelector('form').requestSubmit()
    }
  }
}
