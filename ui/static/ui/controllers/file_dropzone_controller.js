import { Controller } from 'stimulus'

// Drop area feeding a file input: what the browser gives for free on a click,
// extended to a drag. Whoever cares about the files listens to the input.
export class FileDropzone extends Controller {
  static targets = ['dropzone', 'input', 'filename']

  openPicker () {
    this.inputTarget.click()
  }

  showSelection () {
    if (!this.hasFilenameTarget) return
    this.filenameTarget.textContent = Array.from(this.inputTarget.files)
      .map((file) => file.name)
      .join(', ')
  }

  onDragOver (event) {
    event.preventDefault()
    this.dropzoneTarget.classList.add('gsl-dropzone--over')
  }

  onDragLeave (event) {
    event.preventDefault()
    this.dropzoneTarget.classList.remove('gsl-dropzone--over')
  }

  onDrop (event) {
    event.preventDefault()
    this.dropzoneTarget.classList.remove('gsl-dropzone--over')
    if (!event.dataTransfer || !event.dataTransfer.files.length) return

    this.inputTarget.files = event.dataTransfer.files
    // Assigning `files` is silent, where picking a file fires "change".
    this.inputTarget.dispatchEvent(new Event('change', { bubbles: true }))
  }
}
