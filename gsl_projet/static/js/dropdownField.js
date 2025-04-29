// TODO put it back to the

// Toggle dropdowns
document.querySelectorAll('.filter-dropdown button').forEach(button => {
  button.addEventListener('click', function (event) {
      event.stopPropagation();
      let content = this.nextElementSibling;
      if (content) {
          let isContentDisplayed = content.style.display === 'grid'
          content.style.display = isContentDisplayed ? 'none' : 'grid';
      }
  });
});

// Close dropdowns when clicking outside
document.addEventListener('click', function (event) {
  document.querySelectorAll('.filter-dropdown').forEach(dropdown => {
      if (!dropdown.contains(event.target)) {
          dropdown.querySelector('.filter-content').style.display = 'none';
      }

  });
});
