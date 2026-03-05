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

// Persist column visibility choices in localStorage
document.querySelectorAll('.gsl-column-visibility-dropdown[data-table-id]')
  .forEach(dropdown => {
    const tableId = dropdown.dataset.tableId
    const storageKey = 'gsl-columns-hidden-' + tableId
    const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]')

    // Restore saved state
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey))
      if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
        // New format: object {cssKey: true/false} — only override known columns
        checkboxes.forEach(checkbox => {
          const cssKey = checkbox.id.replace('toggle-col-', '')
          if (cssKey in saved) {
            checkbox.checked = saved[cssKey]
          }
        })
      } else if (Array.isArray(saved)) {
        // Legacy format: array of hidden column keys — migrate
        saved.forEach(cssKey => {
          const checkbox = dropdown.querySelector('#toggle-col-' + cssKey)
          if (checkbox) {
            checkbox.checked = false
          }
        })
      }
    } catch (_) {
      // Ignore malformed localStorage data
    }

    // Save state on change — store overrides vs HTML defaults
    checkboxes.forEach(checkbox => {
      checkbox.addEventListener('change', () => {
        const overrides = {}
        checkboxes.forEach(cb => {
          const cssKey = cb.id.replace('toggle-col-', '')
          overrides[cssKey] = cb.checked
        })
        window.localStorage.setItem(storageKey, JSON.stringify(overrides))
      })
    })
  })
