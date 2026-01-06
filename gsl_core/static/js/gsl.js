// Make notice closable again
document.querySelectorAll('.fr-notice button.fr-btn--close').forEach((elt) => {
  elt.addEventListener('click', (evt) => {
    const notice = elt.parentNode.parentNode.parentNode
    notice.parentNode.removeChild(notice)
  })
})

// Close dropdowns when clicking outside
document.addEventListener('click', function (event) {
  document.querySelectorAll('.gsl-dropdown').forEach(dropdown => {
    if (!dropdown.contains(event.target)) {
      dropdown.querySelector('.gsl-dropdown-content').style.display = 'none'
    }
  })
})

// Close DSFR dropdowns and other collapse when clicking outside.
// I have the feeling this should not be necessary, and DSFR should handle this itself,
// but we may have a bug introduced by our own JS, or simply the DSFR does not do that
document.addEventListener('click', function (event) {
  document.querySelectorAll('.fr-collapse--expanded').forEach(menu => {
    if (!menu.contains(event.target)) {
      dsfr(menu).collapse.conceal()
    }
  })
})

// Toggle dropdowns
document.querySelectorAll('.gsl-dropdown button').forEach(button => {
  button.addEventListener('click', function (event) {
    event.stopPropagation()
    const content = this.nextElementSibling
    if (content) {
      content.style.display = content.style.display === 'grid' ? 'none' : 'grid'
    }
  })
})
