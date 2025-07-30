import { Controller } from "stimulus"

export class ModeleArreteForm extends Controller {
  confirmaCancel(){
    window.addEventListener('beforeunload', e => {
        e.preventDefault();
        e.returnValue = '';
    });
  }
}