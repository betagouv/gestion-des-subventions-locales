import { Controller } from 'stimulus'

export class FormUtils extends Controller {
  static targets = ['container']

  disableButtons (evt) {
    const container = this.hasContainerTarget ? this.containerTarget : evt.target
    const buttons = container.querySelectorAll('button')
    buttons.forEach(btn => {
      if (btn.type === 'submit') {
        this._disableButtonAndAddALoader(btn)
      } else {
        btn.setAttribute('disabled', '1')
      }
    })
  }

  _disableButtonAndAddALoader (btn) {
    btn.classList.add('fr-icon-loader')
    btn.classList.add('fr-icon-spin')
    btn.setAttribute('disabled', '1')
  }
}
