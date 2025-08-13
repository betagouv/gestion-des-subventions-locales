let selectedForm = undefined;

document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('id_file');
    const submitArreteEtLettreSignesBtn = document.getElementById('submit-arrete-et-lettre-signes-form');

    if (fileInput && submitArreteEtLettreSignesBtn) {
        fileInput.addEventListener('change', function() {
            submitArreteEtLettreSignesBtn.disabled = !fileInput.files.length;
        });
    }
});
