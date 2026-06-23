import { Controller } from 'stimulus'

export class RadioNavigate extends Controller {
  navigate (event) {
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
