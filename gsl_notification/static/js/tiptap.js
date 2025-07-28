import { Editor } from "https://esm.sh/@tiptap/core";
import StarterKit from "https://esm.sh/@tiptap/starter-kit";
import Highlight from "https://esm.sh/@tiptap/extension-highlight";
import TextAlign from "https://esm.sh/@tiptap/extension-text-align";
import Mention from "https://esm.sh/@tiptap/extension-mention";

const EXTENSIONS = [
    StarterKit,
    Highlight.configure({ multicolor: false }),
    TextAlign.configure({
      types: ['heading', 'paragraph'],
    }),
  ]

if (WITH_MENTION) {
  const ITEMS = JSON.parse(document.getElementById("mention-items-data").text);
  const MENTION = Mention.configure({
    HTMLAttributes: {
      class: 'mention'
    },
    suggestion: {
      char: '@',
      startOfLine: false,
      items: ({ query }) => {
        const fields = ITEMS
        return fields
          .filter(field => field.label.toLowerCase().startsWith(query.toLowerCase()))
          .slice(0, 10);
      },
      render: () => {
        let popup;
        let selectedIndex = 0;
        let originalItems = [];
        let divItems = [];
        function updateSelection(newIndex) {
              divItems[selectedIndex].classList.remove('selected');
              selectedIndex = newIndex;
              divItems[selectedIndex].classList.add('selected');
              divItems[selectedIndex].scrollIntoView({
                block: 'nearest',
              });
            }
        function reinitializeVariables() {
          selectedIndex = 0;
          divItems = [];
        }

        let selectItem;

        return {
          onStart: props => {
            originalItems = props.items;
            reinitializeVariables();

            selectItem = (item) => {
              props.command(item);
            };

            // Créer le conteneur
            popup = document.createElement('div');
            popup.className = 'mention-list';
            popup.setAttribute('tabindex', '-1'); // Rendre focusable

            // Ajouter les éléments
            props.items.forEach(item => {
              const div = document.createElement('div');
              div.className = 'mention-item';
              div.textContent = item.label;
              div.dataset.id = item.id;
              div.addEventListener('click', () => {
                props.command(item);
              });
              div.addEventListener('mouseover', () => {
                let index = divItems.indexOf(div);
                updateSelection(index);
              });
              popup.appendChild(div);
              divItems.push(div);
            });

            updateSelection(0);

            // Positionner le popup
            const rect = props.clientRect();
            if (rect) {
              popup.style.top = `${rect.bottom + window.scrollY}px`;
              popup.style.left = `${rect.left + window.scrollX}px`;
            }

            document.body.appendChild(popup);
          },
          onUpdate: props => {
            reinitializeVariables();

            while (popup.firstChild) {
              popup.removeChild(popup.firstChild);
            }
            
            props.items.forEach(item => {
              const div = document.createElement('div');
              div.className = 'mention-item';
              div.textContent = item.label;
              div.dataset.id = item.id;
              div.addEventListener('click', () => {
                props.command(item);
              });
              div.addEventListener('mouseover', () => {
                let index = divItems.indexOf(div);
                updateSelection(index);
              });
              popup.appendChild(div);
              divItems.push(div);
            });
            updateSelection(0);
          },
          onKeyDown(props) {
            if (props.event.key === 'Escape') {
              popup.style.display = 'none';
              return true;
            }
            if (props.event.key === 'ArrowDown') {
              if (selectedIndex < divItems.length - 1) {
                updateSelection(selectedIndex + 1);
              }
              return true;
            }
            if (props.event.key === 'ArrowUp') {
              if (selectedIndex > 0) {
                updateSelection(selectedIndex - 1);
              }
              return true;
            }
            if (props.event.key === 'Enter') {
              if (divItems[selectedIndex]) {
                // Astuce pour supprimer le texte tapé
                const { state, dispatch } = props.view;
                const { from, to } = props.range;
                dispatch(
                  state.tr.delete(from, to)
                );
                //
                const divItem = divItems[selectedIndex];
                const item = originalItems.find(i => i.id === Number(divItem.dataset.id));
                selectItem(item); 
              }
              return true;
            }
            return false;
          },
          onExit() {
            if (popup) {
              popup.remove();
              popup = null;
            }
          },
        };
      }
    }
  });

  EXTENSIONS.push(MENTION);
}

const editor = new Editor({
  element: document.querySelector("#editor"),
  extensions: EXTENSIONS,
  onCreate({ editor }) {
    editor.commands.setContent(document.querySelector('input[name="'+CONTENT_FIELD_NAME+'"]').value);
    document.querySelector('input[name="'+CONTENT_FIELD_NAME+'"]').value = editor.getHTML();
  },
  onUpdate({ editor }) {
    document.querySelector('input[name="'+CONTENT_FIELD_NAME+'"]').value = editor.getHTML();
  }
});

// Gestion des boutons de la toolbar
document.addEventListener('DOMContentLoaded', function () {
  const btns_groups = Array.from(document.querySelector("#toolbar").children)

  btns_groups.forEach(btn_group => Array.from(btn_group.children).forEach(btn => {
      btn.addEventListener("click", (event) => {
      if (!btn.dataset.action) return;
      switch (btn.dataset.action) {
        case "bold":
          editor.chain().focus().toggleBold().run();
          break;
        case "italic":
          editor.chain().focus().toggleItalic().run();
          break;
        case "underline":
          editor.chain().focus().toggleUnderline().run();
          break;
        case "heading":
          editor.chain().focus().toggleHeading({ level: parseInt(btn.dataset.level) }).run();
          break;
        case "bulletList":
          editor.chain().focus().toggleBulletList().run();
          break;
        case "orderedList":
          editor.chain().focus().toggleOrderedList().run();
          break;
        case "align":
          editor.chain().focus().setTextAlign(btn.dataset.align).run();
          break;
        case "undo":
          editor.chain().focus().undo().run();
          break;
        case "redo":
          editor.chain().focus().redo().run();
          break;
      }
    })
  }))
})