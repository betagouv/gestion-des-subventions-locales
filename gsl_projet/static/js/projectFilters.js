// submit filters when select are changed
document.querySelectorAll(".projets-filters-layout select").forEach((elt) => {
    elt.addEventListener("change", (evt) => {
        evt.target.form.submit();
    })
});

// Close dropdowns when clicking outside
document.addEventListener('click', function (event) {
    document.querySelectorAll('.filter-dropdown').forEach(dropdown => {
        if (!dropdown.contains(event.target)) {
            dropdown.querySelector('.filter-content').style.display = 'none';
        }
    });
});

// Toggle dropdowns
document.querySelectorAll('.filter-dropdown button').forEach(button => {
    button.addEventListener('click', function (event) {
        event.stopPropagation();
        let content = this.nextElementSibling;
        if (content) {
            content.style.display = content.style.display === 'grid' ? 'none' : 'grid';
        }
    });
});