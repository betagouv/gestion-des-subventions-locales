import { Controller } from 'stimulus'

export class QrCodeToggle extends Controller {
  static targets = ['checkbox', 'link']

  connect () {
    this._sync()
  }

  toggle () {
    this._sync()
  }

  _sync () {
    const withQr = this.checkboxTarget.checked
    this.linkTargets.forEach(link => {
      const url = new URL(link.href, window.location.origin)
      if (withQr) {
        url.searchParams.delete('with_qr_code')
      } else {
        url.searchParams.set('with_qr_code', '0')
      }
      link.setAttribute('href', url.pathname + url.search)
    })
  }
}
