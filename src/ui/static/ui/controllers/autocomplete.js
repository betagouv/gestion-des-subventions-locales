import { Controller } from 'stimulus'

// Declared on a <select> with an id: replaces it with a combobox filtering its
// options as the user types (WAI-ARIA "combobox with listbox popup" pattern).
// The select stays the form field: it is hidden and kept in sync, so another
// controller can still fill it, select a value or disable it.
export class Autocomplete extends Controller {
  connect () {
    this.input = this._createInput()
    this.listbox = this._createListbox()
    this.clearButton = this._createClearButton()
    this.status = this._createStatus()
    this.container = document.createElement('div')
    this.container.className = 'gsl-autocomplete'
    this.container.append(this.input, this.clearButton, this.listbox, this.status)
    this.element.after(this.container)
    this.element.classList.add('gsl-autocomplete__select')

    this.label = this.element.labels[0]
    if (this.label) this.label.htmlFor = this.input.id

    this.onChange = () => this._syncValue()
    this.element.addEventListener('change', this.onChange)
    this.observer = new window.MutationObserver(() => this._sync())
    this.observer.observe(this.element, {
      childList: true, subtree: true, attributes: true, attributeFilter: ['disabled']
    })
    this._sync()
  }

  disconnect () {
    this.observer.disconnect()
    this.element.removeEventListener('change', this.onChange)
    this.container.remove()
    this.element.classList.remove('gsl-autocomplete__select')
    if (this.label) this.label.htmlFor = this.element.id
  }

  filter () {
    const query = normalize(this.input.value.trim())
    const matches = this.options.filter(({ key }) => key.includes(query))
    this._render(matches)
    this.status.textContent = statusMessage(matches.length)
    this._open()
  }

  keydown (event) {
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowUp':
        event.preventDefault()
        if (!this._isOpen()) this.filter()
        this._activate(this.activeIndex + (event.key === 'ArrowDown' ? 1 : -1))
        break
      case 'Enter':
        if (!this._isOpen()) return
        event.preventDefault()
        if (this.activeIndex >= 0) this._choose(this._items()[this.activeIndex])
        break
      case 'Escape':
        if (!this._isOpen()) return
        event.preventDefault()
        this._close()
        this._syncValue()
        break
      case 'Tab':
        this._close()
        break
    }
  }

  // Private

  _createInput () {
    const input = document.createElement('input')
    input.type = 'text'
    input.id = `${this.element.id}-autocomplete`
    input.className = 'fr-select'
    input.autocomplete = 'off'
    input.spellcheck = false
    input.setAttribute('role', 'combobox')
    input.setAttribute('aria-autocomplete', 'list')
    input.setAttribute('aria-expanded', 'false')
    input.setAttribute('aria-controls', `${this.element.id}-listbox`)
    input.addEventListener('input', () => {
      this._toggleClearButton()
      this.filter()
    })
    input.addEventListener('click', () => { if (!this._isOpen()) this.filter() })
    input.addEventListener('keydown', event => this.keydown(event))
    input.addEventListener('blur', () => {
      this._close()
      this._syncValue()
    })
    return input
  }

  _createListbox () {
    const listbox = document.createElement('ul')
    listbox.id = `${this.element.id}-listbox`
    listbox.className = 'gsl-autocomplete__listbox'
    listbox.hidden = true
    listbox.setAttribute('role', 'listbox')
    // Keeps the focus in the input, so that choosing does not blur it.
    listbox.addEventListener('mousedown', event => event.preventDefault())
    listbox.addEventListener('click', event => {
      const item = event.target.closest('[role="option"]')
      if (item) this._choose(item)
    })
    return listbox
  }

  _createClearButton () {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-close-line gsl-autocomplete__clear'
    button.title = 'Effacer la saisie'
    button.textContent = 'Effacer la saisie'
    button.hidden = true
    button.addEventListener('click', () => this._clear())
    return button
  }

  _createStatus () {
    const status = document.createElement('span')
    status.className = 'fr-sr-only'
    status.setAttribute('role', 'status')
    return status
  }

  _sync () {
    this.options = [...this.element.querySelectorAll('option')]
      .filter(option => option.value)
      .map(option => ({
        option,
        key: normalize(option.text),
        group: option.parentElement.tagName === 'OPTGROUP' ? option.parentElement.label : null
      }))
    const placeholder = this.element.querySelector('option[value=""]')
    this.input.placeholder = placeholder ? placeholder.text.trim() : ''
    this.input.disabled = this.element.disabled
    this._syncValue()
  }

  _syncValue () {
    const selected = this.element.selectedOptions[0]
    this.input.value = selected && selected.value ? selected.text : ''
    this._toggleClearButton()
  }

  _toggleClearButton () {
    this.clearButton.hidden = !this.input.value || this.input.disabled
  }

  _clear () {
    this.element.value = ''
    this.element.dispatchEvent(new Event('change', { bubbles: true }))
    this.input.focus()
  }

  _render (matches) {
    this.listbox.replaceChildren()
    this.activeIndex = -1
    if (!matches.length) {
      const empty = document.createElement('li')
      empty.className = 'gsl-autocomplete__empty'
      empty.setAttribute('role', 'presentation')
      empty.textContent = 'Aucun résultat'
      this.listbox.append(empty)
      return
    }
    let list = this.listbox
    let currentGroup = null
    matches.forEach(({ option, group }, index) => {
      if (group !== currentGroup) {
        currentGroup = group
        list = group ? this._appendGroup(group) : this.listbox
      }
      list.append(this._createItem(option, index))
    })
  }

  _appendGroup (label) {
    const labelId = `${this.element.id}-group-${this.listbox.childElementCount}`
    const title = document.createElement('span')
    title.id = labelId
    title.className = 'gsl-autocomplete__group-label'
    title.textContent = label
    const group = document.createElement('ul')
    group.setAttribute('role', 'group')
    group.setAttribute('aria-labelledby', labelId)
    const wrapper = document.createElement('li')
    wrapper.setAttribute('role', 'presentation')
    wrapper.append(title, group)
    this.listbox.append(wrapper)
    return group
  }

  _createItem (option, index) {
    const item = document.createElement('li')
    item.id = `${this.element.id}-option-${index}`
    item.className = 'gsl-autocomplete__option'
    item.dataset.value = option.value
    item.textContent = option.text
    item.setAttribute('role', 'option')
    item.setAttribute('aria-selected', 'false')
    return item
  }

  _activate (index) {
    const items = this._items()
    if (!items.length) return
    this.activeIndex = (index + items.length) % items.length
    items.forEach((item, i) => item.setAttribute('aria-selected', i === this.activeIndex))
    const active = items[this.activeIndex]
    this.input.setAttribute('aria-activedescendant', active.id)
    active.scrollIntoView({ block: 'nearest' })
  }

  _choose (item) {
    this.element.value = item.dataset.value
    this.element.dispatchEvent(new Event('change', { bubbles: true }))
    this._close()
  }

  _open () {
    this.listbox.hidden = false
    this.input.setAttribute('aria-expanded', 'true')
  }

  _close () {
    this.listbox.hidden = true
    this.input.setAttribute('aria-expanded', 'false')
    this.input.removeAttribute('aria-activedescendant')
    this.activeIndex = -1
  }

  _isOpen () {
    return !this.listbox.hidden
  }

  _items () {
    return [...this.listbox.querySelectorAll('[role="option"]')]
  }
}

// Case, accent and punctuation insensitive: "st-eveque" matches "St-Évêque".
function normalize (text) {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .replace(/[-'’]/g, ' ')
    .toLowerCase()
}

function statusMessage (count) {
  if (count === 0) return 'Aucun résultat'
  if (count === 1) return '1 résultat'
  return `${count} résultats`
}
