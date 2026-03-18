document.body.addEventListener('htmx:beforeRequest', (evt) => {
  if (evt.detail.elt.classList.contains('gsl-cell-edit-btn')) {
    document.querySelectorAll('.gsl-cell-edit-form').forEach((el) => el.remove())
  }
})
