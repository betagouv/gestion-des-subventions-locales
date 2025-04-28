// submit filters when select are changed
document.querySelectorAll(".projets-filters-layout select").forEach((elt) => {
    elt.addEventListener("change", (evt) => {
        evt.target.form.submit();
    })
});
