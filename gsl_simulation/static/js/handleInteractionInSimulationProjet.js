import { handleDotationChange } from "./modules/handleDotationUpdate.js";
import { disableAllModalButtons } from "./modules/utils.js";

document.querySelectorAll(".status-radio-button").forEach((elt) => {
    elt.addEventListener("change", (ev) => {
        let target = ev.target;
        return handleStatusChange(target, target.dataset.originalValue);
      })
})

let detr_avis_commission = document.querySelector("#id_detr_avis_commission")
if (detr_avis_commission) {
    detr_avis_commission.addEventListener("change", (ev) => {
    if(ev.target) ev.target.form.submit();
  })
}

document.querySelectorAll(".form-disabled-before-value-change").forEach((elt) => {
  let button = elt.querySelector("button[type='submit']")
  if (button)(
    elt.addEventListener("change", (ev) => {
      button.disabled = false;
    })
  )
})

// Dotation Update

document.querySelector("#submit-dotation").addEventListener("click", (ev) => {
  ev.preventDefault();
  selectedElement = ev.target
  let form = document.querySelector("form#projet_form").closest("form")
  let fieldset = document.querySelector("#dotation-fieldset")
  const initalDotationValues = selectedElement.dataset.initialDotations.split(",")
  handleDotationChange(form, fieldset, initalDotationValues)
});


document.querySelectorAll("#confirm-dotation-update").forEach(elt => {
  elt.addEventListener("click", async (ev) => {
    disableAllModalButtons(elt.closest(".confirmation-modal"));
    let form = document.querySelector("form#projet_form").closest("form")
    form.submit()
    closeModal()
  })
})


// Montant update
document.addEventListener('DOMContentLoaded', function () {
  const form = document.querySelector('#simulation_projet_form');
  const assietteInput = document.querySelector('#id_assiette'); 
  const montantInput = document.querySelector('#id_montant'); 
  const tauxInput = document.querySelector('#id_taux');
  
  const coutTotal = form.dataset.coutTotal;

  const parseValue = (val) => parseFloat(val.replace(',', '.').replace(/\s/g, ''));
  const TOTAL_ELIGIBLE = assietteInput.value ? parseValue(assietteInput.value) : parseValue(coutTotal);

  // Fonction de formatage
  function formatMontant(val) {
    const n = parseValue(val);
    return isNaN(n) ? '' : n.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function formatTaux(val) {
    const n = parseValue(val);
    return isNaN(n) ? '' : n.toLocaleString('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  }

  // Format à l'initialisation
  assietteInput.value = formatMontant(assietteInput.value);
  montantInput.value = formatMontant(montantInput.value);
  tauxInput.value = formatTaux(tauxInput.value);

  // Format lors du blur
  assietteInput.addEventListener('blur', function () {
    assietteInput.value = formatMontant(assietteInput.value);
  });
  montantInput.addEventListener('blur', function () {
    montantInput.value = formatMontant(montantInput.value);
  });
  tauxInput.addEventListener('blur', function () {
    tauxInput.value = formatTaux(tauxInput.value);
  });

  // Lorsqu'on modifie l'assiette
  assietteInput.addEventListener('input', function () {
      const assiette = parseValue(assietteInput.value);
      const montant = parseValue(montantInput.value);
      if (!isNaN(assiette) && !isNaN(montant)) {
          const taux = (montant / assiette) * 100;
        tauxInput.value = taux.toLocaleString('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
      }
  });

  // Lorsqu'on modifie le montant
  montantInput.addEventListener('input', function () {
      const montant = parseValue(montantInput.value);
      if (!isNaN(montant)) {
          const taux = (montant / TOTAL_ELIGIBLE) * 100;
        tauxInput.value = taux.toLocaleString('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
      }
  });

  // Lorsqu'on modifie le taux
  tauxInput.addEventListener('input', function () {
      const taux = parseValue(tauxInput.value);
      if (!isNaN(taux)) {
          const montant = (taux / 100) * TOTAL_ELIGIBLE;
        montantInput.value = montant.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      }
  });

  form.addEventListener('submit', function (e) {
    // Nettoyage des champs avant soumission
    [montantInput, tauxInput, assietteInput].forEach(input => {
      if (input && input.value) {
        input.value = input.value.replace(/\s/g, '').replace(',', '.');
      }
    });
  });
});