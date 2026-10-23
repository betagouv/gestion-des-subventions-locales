import { Controller } from 'stimulus'

const GEO_API_URL = 'https://geo.api.gouv.fr'
const byName = new Intl.Collator('fr').compare

// Declared on a <select>: fills it with the communes and intercommunalités of
// the agent's perimetre, from geo.api.gouv.fr. geo.api does not know
// arrondissements, so an arrondissement perimetre passes its communes' INSEE
// codes in `communes`.
export class CollectiviteMenu extends Controller {
  static values = { query: String, communes: Array, selected: String }

  async connect () {
    const [communes, epcis] = await Promise.all([
      this._fetch('communes', 'nom,siren,codeEpci'),
      this._fetch('epcis', 'nom,code')
    ])
    const kept = this.hasCommunesValue
      ? communes.filter(commune => this.communesValue.includes(commune.code))
      : communes
    const epciCodes = new Set(kept.map(commune => commune.codeEpci))
    this.element.append(
      this._group('Communes', kept.map(commune => [commune.siren, commune.nom])),
      this._group(
        'Intercommunalités',
        epcis.filter(epci => epciCodes.has(epci.code)).map(epci => [epci.code, epci.nom])
      )
    )
    if (this.element.querySelector(`option[value="${this.selectedValue}"]`)) {
      this.element.value = this.selectedValue
    }
  }

  async _fetch (resource, fields) {
    const response = await fetch(`${GEO_API_URL}/${resource}?${this.queryValue}&fields=${fields}`)
    if (!response.ok) throw new Error(`geo.api ${resource} : ${response.status}`)
    return response.json()
  }

  _group (label, entries) {
    const group = document.createElement('optgroup')
    group.label = label
    entries
      .sort(([, first], [, second]) => byName(first, second))
      .forEach(([siren, nom]) => group.append(new window.Option(nom, siren)))
    return group
  }
}
