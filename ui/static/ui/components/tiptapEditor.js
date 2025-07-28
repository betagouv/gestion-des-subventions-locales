import { Editor } from "https://esm.sh/@tiptap/core";
import StarterKit from "https://esm.sh/@tiptap/starter-kit";
import TextAlign from "https://esm.sh/@tiptap/extension-text-align";
import Mention from "https://esm.sh/@tiptap/extension-mention";
import { Controller } from "stimulus"


const EXTENSIONS = [
    StarterKit,
    TextAlign.configure({
      types: ['heading', 'paragraph'],
    }),
  ]

export class TipTapEditor extends Controller {
  static values = {
    withMention:{
      type: Boolean,
      default: false,
    },
    mentions:{
      type: Array,
      default: []
    },
    contentFieldName: String
  }
  static targets = ["editor", "toolbarButton"]

  // TODO handle mention

  connect(){
    this._setToolbar()
    this._setEditor();
    console.log("Tiptap Editor connected !")
    console.log("this.contentFieldNameValue", this.contentFieldNameValue)
  }

  // Private

  _setEditor(){
    console.log("this.hasEditorTarget", this.hasEditorTarget)
    console.log("this.editorTarget", this.editorTarget)
    if(!this.hasEditorTarget){
      console.warn("No tiptap editor target !")
    }

    const contentInput = document.querySelector(`input[name="${this.contentFieldNameValue}"]`);

    this.editor = new Editor({
      element: this.editorTarget,
      extensions: EXTENSIONS,
      onCreate({ editor }) {
        editor.commands.setContent(contentInput.value);
        contentInput.value = editor.getHTML();
      },
      onUpdate({ editor }) {
        contentInput.value = editor.getHTML();
      }
    });
  
  }
  
  _setToolbar(){
    console.log('setToolbar')
    console.log(this.hasToolbarButtonTarget)
    console.log(this.toolbarButtonTargets)
    if(!this.hasToolbarButtonTarget){
      console.warn("No tiptap editor target !")
    }

    this.toolbarButtonTargets.forEach(btn => this._setButtonAction(btn))
  };

  _setButtonAction(btn) {
    btn.addEventListener("click", (event) => {
      if (!btn.dataset.action) return;
      switch (btn.dataset.action) {
        case "bold":
          this.editor.chain().focus().toggleBold().run();
          break;
        case "italic":
          this.editor.chain().focus().toggleItalic().run();
          break;
        case "underline":
          this.editor.chain().focus().toggleUnderline().run();
          break;
        case "heading":
          this.editor.chain().focus().toggleHeading({ level: parseInt(btn.dataset.level) }).run();
          break;
        case "bulletList":
          this.editor.chain().focus().toggleBulletList().run();
          break;
        case "orderedList":
          this.editor.chain().focus().toggleOrderedList().run();
          break;
        case "align":
          this.editor.chain().focus().setTextAlign(btn.dataset.align).run();
          break;
        case "undo":
          this.editor.chain().focus().undo().run();
          break;
        case "redo":
          this.editor.chain().focus().redo().run();
          break;
      }
    })
  }
}
