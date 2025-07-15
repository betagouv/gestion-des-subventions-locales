let selectedForm = undefined;

document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('id_file');
    const submitArreteSigneBtn = document.getElementById('submit-arrete-signe-form');

    if (fileInput && submitArreteSigneBtn) {
        fileInput.addEventListener('change', function() {
            submitArreteSigneBtn.disabled = !fileInput.files.length;
        });
    }
});
