import { Controller } from 'stimulus'

export class RadioNavigate extends Controller {
  static values = {
    baseUrl: String
  }

  navigate (event) {
    const value = event.target.value
    window.location.href = value
      ? `${this.baseUrlValue}?dotation=${value}`
      : this.baseUrlValue
  }
}
