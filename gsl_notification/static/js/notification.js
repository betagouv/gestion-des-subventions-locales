document.addEventListener('DOMContentLoaded', function() {
    const showArreteSigneForm = document.getElementById('show-arrete-signe-form');
    const showArreteForm = document.getElementById('show-arrete-form');
    const arreteSigneForm = document.getElementById('arrete-signe-form');
    const arreteForm = document.getElementById('arrete-form');
    const fileInput = document.getElementById('id_file');
    const submitBtn = document.getElementById('submit-arrete-signe-form');
    const cancelBtn = document.getElementById('cancel-arrete-form');

    if (showArreteSigneForm && arreteSigneForm) {
        showArreteSigneForm.addEventListener('click', function(event) {
            event.preventDefault();
            arreteSigneForm.classList.remove('hidden');
            arreteForm.classList.add('hidden');
        });
    }
    if (showArreteForm && arreteForm) {
        showArreteForm.addEventListener('click', function(event) {
            event.preventDefault();
            arreteForm.classList.remove('hidden');
            arreteSigneForm.classList.add('hidden');
        });
    }
    if (arreteForm && !showArreteForm) {
        arreteForm.classList.remove('hidden');
    }

    if (fileInput && submitBtn) {
        fileInput.addEventListener('change', function() {
            submitBtn.disabled = !fileInput.files.length;
        });
    }

    if (cancelBtn && arreteForm) {
        cancelBtn.addEventListener('click', function(event) {
            event.preventDefault();
            arreteForm.classList.add('hidden');
            arreteSigneForm.classList.add('hidden');
        });
    }
});
