import { Editor } from "https://esm.sh/@tiptap/core";
import StarterKit from "https://esm.sh/@tiptap/starter-kit";

const editor = new Editor({
  element: document.querySelector("#editor"),
  extensions: [StarterKit],
  content: "<p>Mon arrêté</p>",
  onCreate({ editor }) {
    const json = editor.getJSON();
    document.querySelector('input[name="content"]').value =
      JSON.stringify(json);
  },
  onUpdate({ editor }) {
    const json = editor.getJSON();
    document.querySelector('input[name="content"]').value =
      JSON.stringify(json);
  },
});

// Gestion des boutons de la toolbar
// document.addEventListener('DOMContentLoaded', function () {
  // Array.from(document.querySelector("#toolbar").children).forEach(btn => btn.addEventListener("click", (event) => {
  //   if (!btn.dataset.action) return;
  //   switch (btn.dataset.action) {
  //     case "bold":
  //       editor.chain().focus().toggleBold().run();
  //       break;
  //     case "italic":
  //       editor.chain().focus().toggleItalic().run();
  //       break;
  //     case "undo":
  //       editor.chain().focus().undo().run();
  //       break;
  //     case "redo":
  //       editor.chain().focus().redo().run();
  //       break;
  //   }
  // }))


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
// })

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
