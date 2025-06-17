document.addEventListener('DOMContentLoaded', function() {
    const showArreteSigneForm = document.getElementById('show-arrete-signe-form');
    const arreteSigneForm = document.getElementById('arrete-signe-form');
    const fileInput = document.getElementById('id_file');
    const submitBtn = document.getElementById('submit-arrete-signe-form');

    if (showArreteSigneForm && arreteSigneForm) {
        showArreteSigneForm.addEventListener('click', function(event) {
            event.preventDefault();
            arreteSigneForm.classList.remove('hidden');
        });
    }

    if (fileInput && submitBtn) {
        fileInput.addEventListener('change', function() {
            submitBtn.disabled = !fileInput.files.length;
        });
    }
});
