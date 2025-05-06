// Make notice closable again
document.querySelectorAll(".fr-notice button.fr-btn--close").forEach((elt) => {
  elt.addEventListener("click", (evt) => {
    const notice = elt.parentNode.parentNode.parentNode
    notice.parentNode.removeChild(notice)
  })
})