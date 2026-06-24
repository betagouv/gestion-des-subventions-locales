import { Controller } from 'stimulus'

export class RadioNavigate extends Controller {
  onKeydown (event) {
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
      this._skipNextChange = true
    }
  }

  navigate (event) {
    if (this._skipNextChange) {
      this._skipNextChange = false
      return
    }
    const url = new URL(window.location.href)
    const value = event.target.value
    if (value) {
      url.searchParams.set('dotation', value)
    } else {
      url.searchParams.delete('dotation')
    }
    window.location.href = url.toString()
  }
}
