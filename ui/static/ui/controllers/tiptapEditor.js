import { Editor, Highlight, Mention, StarterKit, TextAlign } from 'tiptap'
import { Controller } from 'stimulus'

const EXTENSIONS = [
  StarterKit,
  TextAlign.configure({
    types: ['heading', 'paragraph']
  }),
  Highlight.configure({ multicolor: false })
]

export class TipTapEditor extends Controller {
  static values = {
    withMention: {
      type: Boolean,
      default: false
    },
    mentions: {
      type: Array,
      default: []
    },
    contentFieldName: String
  }

  static targets = ['editor', 'toolbarButton', 'mentionDropdown']

  connect () {
    this._setToolbar()
    this._setEditor()
    if (this.withMention) {
      this.boundClickOutside = this.clickOutside.bind(this)
      document.addEventListener('click', this.boundClickOutside)
    }
  }

  disconnect () {
    if (this.boundClickOutside) {
      document.removeEventListener('click', this.boundClickOutside)
    }
  }

  insertMention (event) {
    if (!this.editor) return

    const mentionId = event.target.dataset.id
    const mentionLabel = event.target.innerHTML

    this.editor.commands.insertContentAt(
      this.editor.state.selection.anchor, // position actuelle du curseur
      {
        type: 'mention',
        attrs: {
          id: mentionId,
          label: mentionLabel
        }
      }
    )
    this.mentionDropdownTarget.removeAttribute('open')
  }

  clickOutside (event) {
    if (!this.element.contains(event.target)) {
      this.mentionDropdownTarget.removeAttribute('open')
    }
  }

  // Private

  _setEditor () {
    if (!this.hasEditorTarget) {
      console.warn('No tiptap editor target !')
    }

    const contentInput = document.querySelector(`input[name="${this.contentFieldNameValue}"]`)

    this.editor = new Editor({
      element: this.editorTarget,
      extensions: this._getExtensions(),
      parseOptions: {
        preserveWhitespace: 'full'
      },
      onCreate ({ editor }) {
        editor.commands.setContent(contentInput.value)
        contentInput.value = editor.getHTML()
      },
      onUpdate ({ editor }) {
        contentInput.value = editor.getHTML()
      }
    })
  }

  _setToolbar () {
    if (!this.hasToolbarButtonTarget) {
      console.warn('No tiptap editor target !')
    }

    this.toolbarButtonTargets.forEach(btn => this._setButtonAction(btn))
  };

  _setButtonAction (btn) {
    btn.addEventListener('click', (event) => {
      if (!btn.dataset.action) return
      switch (btn.dataset.action) {
        case 'bold':
          this.editor.chain().focus().toggleBold().run()
          break
        case 'italic':
          this.editor.chain().focus().toggleItalic().run()
          break
        case 'underline':
          this.editor.chain().focus().toggleUnderline().run()
          break
        case 'highlight':
          this.editor.chain().focus().toggleHighlight().run()
          break
        case 'heading':
          this.editor.chain().focus().toggleHeading({ level: parseInt(btn.dataset.level) }).run()
          break
        case 'bulletList':
          this.editor.chain().focus().toggleBulletList().run()
          break
        case 'orderedList':
          this.editor.chain().focus().toggleOrderedList().run()
          break
        case 'align':
          this.editor.chain().focus().setTextAlign(btn.dataset.align).run()
          break
        case 'undo':
          this.editor.chain().focus().undo().run()
          break
        case 'redo':
          this.editor.chain().focus().redo().run()
          break
      }
    })
  }

  _getExtensions () {
    if (!this.withMentionValue) return EXTENSIONS
    return [...EXTENSIONS, this._getMentionExtension()]
  }

  _getMentionExtension () {
    const MENTION = Mention.configure({
      HTMLAttributes: {
        class: 'mention'
      },
      suggestion: {
        char: '@',
        startOfLine: false,
        items: ({ query }) => {
          const fields = this.mentionsValue
          return fields
            .filter(field => field.label.toLowerCase().startsWith(query.toLowerCase()))
            .slice(0, 10)
        },
        render: () => {
          let popup
          let selectedIndex = 0
          let originalItems = []
          let divItems = []
          function updateSelection (newIndex) {
            divItems[selectedIndex].classList.remove('selected')
            selectedIndex = newIndex
            divItems[selectedIndex].classList.add('selected')
            divItems[selectedIndex].scrollIntoView({
              block: 'nearest'
            })
          }
          function reinitializeVariables () {
            selectedIndex = 0
            divItems = []
          }

          let selectItem

          return {
            onStart: props => {
              originalItems = props.items
              reinitializeVariables()

              selectItem = (item) => {
                props.command(item)
              }

              // Créer le conteneur
              popup = document.createElement('div')
              popup.className = 'mention-list'
              popup.setAttribute('tabindex', '-1') // Rendre focusable

              // Ajouter les éléments
              props.items.forEach(item => {
                const div = document.createElement('div')
                div.className = 'mention-item'
                div.textContent = item.label
                div.dataset.id = item.id
                div.addEventListener('click', () => {
                  props.command(item)
                })
                div.addEventListener('mouseover', () => {
                  const index = divItems.indexOf(div)
                  updateSelection(index)
                })
                popup.appendChild(div)
                divItems.push(div)
              })

              updateSelection(0)

              // Positionner le popup
              const rect = props.clientRect()
              if (rect) {
                popup.style.top = `${rect.bottom + window.scrollY}px`
                popup.style.left = `${rect.left + window.scrollX}px`
              }

              document.body.appendChild(popup)
            },
            onUpdate: props => {
              reinitializeVariables()

              while (popup.firstChild) {
                popup.removeChild(popup.firstChild)
              }

              props.items.forEach(item => {
                const div = document.createElement('div')
                div.className = 'mention-item'
                div.textContent = item.label
                div.dataset.id = item.id
                div.addEventListener('click', () => {
                  props.command(item)
                })
                div.addEventListener('mouseover', () => {
                  const index = divItems.indexOf(div)
                  updateSelection(index)
                })
                popup.appendChild(div)
                divItems.push(div)
              })
              updateSelection(0)
            },
            onKeyDown (props) {
              if (props.event.key === 'Escape') {
                popup.style.display = 'none'
                return true
              }
              if (props.event.key === 'ArrowDown') {
                if (selectedIndex < divItems.length - 1) {
                  updateSelection(selectedIndex + 1)
                }
                return true
              }
              if (props.event.key === 'ArrowUp') {
                if (selectedIndex > 0) {
                  updateSelection(selectedIndex - 1)
                }
                return true
              }
              if (props.event.key === 'Enter') {
                if (divItems[selectedIndex]) {
                  // Astuce pour supprimer le texte tapé
                  const { state, dispatch } = props.view
                  const { from, to } = props.range
                  dispatch(
                    state.tr.delete(from, to - 1)
                  )

                  const divItem = divItems[selectedIndex]
                  const item = originalItems.find(i => i.id === Number(divItem.dataset.id))
                  selectItem(item)
                }
                return true
              }
              return false
            },
            onExit () {
              if (popup) {
                popup.remove()
                popup = null
              }
            }
          }
        }
      }
    })

    return MENTION
  }
}
