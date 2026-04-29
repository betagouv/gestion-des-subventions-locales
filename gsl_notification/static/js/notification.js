let selectedForm = undefined // eslint-disable-line

document.addEventListener('DOMContentLoaded', function () {
  const fileInput = document.getElementById('id_file')
  const submitLettreEtArreteSignesBtn = document.getElementById('submit-lettre-et-arrete-signes-form')

  if (fileInput && submitLettreEtArreteSignesBtn) {
    fileInput.addEventListener('change', function () {
      submitLettreEtArreteSignesBtn.disabled = !fileInput.files.length
    })
  }
})
