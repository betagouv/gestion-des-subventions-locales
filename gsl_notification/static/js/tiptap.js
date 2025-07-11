import { Editor } from "https://esm.sh/@tiptap/core";
import StarterKit from "https://esm.sh/@tiptap/starter-kit";
import TextAlign from "https://esm.sh/@tiptap/extension-text-align";
import Underline from "https://esm.sh/@tiptap/extension-underline";
import Mention from "https://esm.sh/@tiptap/extension-mention";

const CUSTOM_MENTION = Mention.configure({
  HTMLAttributes: {
    class: 'mention'
  },
  suggestion: {
    char: '@',
    startOfLine: false,
    items: ({ query }) => {
      const users = [
        { id: 1, label: 'Nom du bénéficiaire' },
        { id: 2, label: 'Inititulé du projet' },
        { id: 3, label: 'Nom du département' },
        { id: 4, label: 'Montant prévisionnel de la subvention' },
        { id: 5, label: 'Taux de subvention' },
      ];
      return users
        .filter(user => user.label.toLowerCase().startsWith(query.toLowerCase()))
        .slice(0, 5);
    },
    render: () => {
      let popup;
      let selectedIndex = 0;
      let items = [];
      function updateSelection(newIndex) {
            items[selectedIndex].classList.remove('selected');
            selectedIndex = newIndex;
            items[selectedIndex].classList.add('selected');
            items[selectedIndex].scrollIntoView({
              block: 'nearest',
            });
          }
      function reinitializeVariables() {
        selectedIndex = 0;
        items = [];
      }

      let selectItem;

      return {
        onStart: props => {
          reinitializeVariables();

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
              let index = items.indexOf(div);
              updateSelection(index);
            });
            popup.appendChild(div);
            items.push(div);
          });

          updateSelection(0);

          selectItem = (item) => {
              props.command({ id: item.dataset.id, label: item.textContent });

          };

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
            popup.appendChild(div);
            items.push(div);
          });
          updateSelection(0);
        },
        onKeyDown(props) {
          if (props.event.key === 'Escape') {
            popup.style.display = 'none';
            return true;
          }
          if (props.event.key === 'ArrowDown') {
            if (selectedIndex < items.length - 1) {
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
            if (items[selectedIndex]) {
              selectItem(items[selectedIndex]);
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



const EXTENSIONS = [
    StarterKit,
    TextAlign.configure({
      types: ['heading', 'paragraph'],
    }),
    Underline,
    CUSTOM_MENTION
  ]

const editor = new Editor({
  element: document.querySelector("#editor"),
  extensions: EXTENSIONS,
  onCreate({ editor }) {
    editor.commands.setContent(document.getElementById("initial_content").innerHTML);
    document.querySelector('input[name="'+CONTENT_FIELD_NAME+'"]').value = editor.getHTML();
  },
  onUpdate({ editor }) {
    document.querySelector('input[name="'+CONTENT_FIELD_NAME+'"]').value = editor.getHTML();
  }
});

// Gestion des boutons de la toolbar
document.addEventListener('DOMContentLoaded', function () {
  Array.from(document.querySelector("#toolbar").children).forEach(btn => btn.addEventListener("click", (event) => {
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
  }))


  // document.querySelector("#export-pdf").addEventListener("click", () => {
  //   const htmlContent = editor.getHTML();

  //   fetch('/programmation/export-pdf/', {
  //     method: 'POST',
  //     headers: {
  //       'Content-Type': 'application/json',
  //       'X-CSRFToken': getCookie('csrftoken'),
  //     },
  //     body: JSON.stringify({ html: htmlContent })
  //   })
  //   .then(response => response.blob())
  //   .then(blob => {
  //     const url = window.URL.createObjectURL(blob);
  //     const a = document.createElement('a');
  //     a.href = url;
  //     a.download = 'export.pdf';
  //     a.click();
  //   });
  // });
})

// function getCookie(name) {
//   let cookieValue = null;
//   if (document.cookie && document.cookie !== '') {
//     const cookies = document.cookie.split(';');
//     for (let i = 0; i < cookies.length; i++) {
//       const cookie = cookies[i].trim();
//       // Ce cookie commence-t-il par le nom recherché ?
//       if (cookie.substring(0, name.length + 1) === (name + '=')) {
//         cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//         break;
//       }
//     }
//   }
//   return cookieValue;
// }
