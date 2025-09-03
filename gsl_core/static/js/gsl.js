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
