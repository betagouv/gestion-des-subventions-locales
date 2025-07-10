let selectedForm = undefined;

document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('id_file');
    const submitArreteSigneBtn = document.getElementById('submit-arrete-signe-form');

    if (fileInput && submitArreteSigneBtn) {
        fileInput.addEventListener('change', function() {
            submitArreteSigneBtn.disabled = !fileInput.files.length;
        });
    }

    let modal = document.getElementById('delete-arrete-confirmation-modal');

    document.querySelectorAll('.arrete-delete-button').forEach(button => {
        button.addEventListener('click', function(event) {
            event.preventDefault();
            selectedForm = this.closest('form');
            if (modal) {
                dsfr(modal).modal.disclose();
            }
        });
    })

    document.getElementById('confirm-delete-arrete').addEventListener('click', function() {
        if (selectedForm) {
            selectedForm.submit();
        }
    });


    function closeModal() {
        if (modal === undefined) {
            return
        }

        selectedForm.reset()
        dsfr(modal).modal.conceal()
        selectedForm.focus()
        if (formButton) {
            formButton.disabled = true;
        }
        selectedForm = undefined;
    }

    document.querySelectorAll(".close-modal").forEach((el) => {
        el.addEventListener('click', () => {
            closeModal();
        });
    });
});
