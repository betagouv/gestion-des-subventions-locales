document.body.addEventListener('htmx:beforeRequest', (evt) => {
  if (evt.detail.elt.classList.contains('gsl-cell-edit-btn')) {
    document.querySelectorAll('.gsl-cell-edit-form').forEach((el) => el.remove())
  }
})

document.body.addEventListener('keydown', (evt) => {
  if (evt.key === 'Enter' && (evt.metaKey || evt.ctrlKey)) {
    const form = evt.target.closest('.gsl-cell-edit-form')
    if (form) {
      evt.preventDefault()
      form.requestSubmit()
    }
  }
})
