import { Controller } from 'stimulus'

// Step 1 of the signed-document re-import wizard. Validates the dropped PDFs
// (type + cumulative size), uploads each one directly to S3 via a presigned
// POST (bypassing Django's request-body limit), shows aggregate progress, then
// writes the resulting S3 keys into a hidden input and submits the form that
// starts the async import job.
export class DocumentImport extends Controller {
  static values = {
    presignedUrl: String,
    maxSizeMo: Number,
    concurrency: { type: Number, default: 3 },
    reloadOnConceal: { type: Boolean, default: false }
  }

  static targets = [
    'dropzone',
    'fileInput',
    'fileList',
    'progress',
    'submit',
    'keysInput',
    'removeQr',
    'removeQrInput',
    'form'
  ]

  connect () {
    this.files = []
    this._refresh()

    this.dialog = this.element.closest('.fr-modal')

    // This controller lives on the deposit (step 1) and summary (step 3) steps,
    // both of which offer a "Fermer" affordance, so backdrop-click closing is
    // allowed here. The processing step (step 2) has no controller: it leaves
    // the attribute set to "false" by `submitFiles` so it cannot be dismissed.
    this._setBackdropClose(true)

    // The summary step (step 3) re-uses this controller solely to reload the
    // programmation list once the user closes the modal, so the freshly
    // re-attached documents show up. DSFR fires `dsfr.conceal` on the dialog
    // (with a dot in the name, so it can't be a Stimulus data-action).
    if (this.reloadOnConcealValue && this.dialog) {
      this._reloadOnConceal = () => window.location.reload()
      this.dialog.addEventListener('dsfr.conceal', this._reloadOnConceal)
    }
  }

  disconnect () {
    if (this.dialog && this._reloadOnConceal) {
      this.dialog.removeEventListener('dsfr.conceal', this._reloadOnConceal)
    }
  }

  openPicker () {
    this.fileInputTarget.click()
  }

  onFileChange (event) {
    this.addFiles(event.target.files)
    // Allow re-selecting the same file after a removal.
    event.target.value = ''
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
    if (event.dataTransfer && event.dataTransfer.files) {
      this.addFiles(event.dataTransfer.files)
    }
  }

  addFiles (fileList) {
    const maxBytes = this.maxSizeMoValue * 1024 * 1024
    let total = this.files.reduce((sum, f) => sum + f.size, 0)
    // Accumulate one message per rejected file so a batch with several invalid
    // files surfaces every reason at once, not just the last one.
    const errors = []
    for (const file of Array.from(fileList)) {
      const safeName = this._escapeHtml(file.name)
      if (!this._isPdf(file)) {
        errors.push(`«&nbsp;${safeName}&nbsp;» n'est pas un PDF et a été ignoré.`)
        continue
      }
      if (this._isDuplicate(file)) {
        errors.push(`«&nbsp;${safeName}&nbsp;» est déjà sélectionné et a été ignoré.`)
        continue
      }
      if (total + file.size > maxBytes) {
        errors.push(`La taille totale dépasse ${this.maxSizeMoValue} Mo. «&nbsp;${safeName}&nbsp;» a été ignoré.`)
        continue
      }
      total += file.size
      this.files.push(file)
    }
    this._setError(errors.join('<br>'))
    this._refresh()
  }

  _isDuplicate (file) {
    return this.files.some((f) => f.name === file.name && f.size === file.size)
  }

  removeFile (event) {
    const index = parseInt(event.params.index, 10)
    this.files.splice(index, 1)
    this._refresh()
  }

  async submitFiles (event) {
    event.preventDefault()
    if (this.files.length === 0 || this.uploading) return

    this.uploading = true
    this._setError('')
    this.submitTarget.disabled = true
    this.progressTarget.hidden = false

    this.progressByIndex = new Array(this.files.length).fill(0)
    try {
      const keys = await this._uploadAll()
      this.keysInputTarget.value = JSON.stringify(keys)
      this.removeQrInputTarget.value = this.removeQrTarget.checked ? 'true' : 'false'
      // Entering the processing step (no "Fermer" affordance): lock the backdrop
      // so the modal cannot be dismissed mid-import. The processing partial has
      // no controller, so this attribute on the dialog persists across the swap.
      this._setBackdropClose(false)
      // htmx is loaded as a self-initializing ES module and isn't exposed as a
      // global, so we dispatch a native submit event (which htmx listens for on
      // the hx-post form) rather than calling htmx.trigger directly.
      this.formTarget.requestSubmit()
    } catch (error) {
      this.uploading = false
      this.submitTarget.disabled = false
      this._setBackdropClose(true)
      this._setError(`Une erreur est survenue pendant l'envoi : ${this._escapeHtml(error.message)}`)
    }
  }

  // DSFR reads `data-fr-concealing-backdrop` live on each backdrop click
  // (`"false" !== getAttribute(...)`), so toggling it at runtime is enough to
  // enable/disable closing the modal by clicking outside it.
  _setBackdropClose (allowed) {
    if (!this.dialog) return
    if (allowed) {
      this.dialog.removeAttribute('data-fr-concealing-backdrop')
    } else {
      this.dialog.setAttribute('data-fr-concealing-backdrop', 'false')
    }
  }

  async _uploadAll () {
    const keys = new Array(this.files.length)
    const queue = this.files.map((file, index) => ({ file, index }))
    const limit = Math.max(1, this.concurrencyValue)

    const worker = async () => {
      while (queue.length > 0) {
        const { file, index } = queue.shift()
        keys[index] = await this._uploadOne(file, index)
      }
    }

    await Promise.all(Array.from({ length: limit }, () => worker()))
    return keys
  }

  async _uploadOne (file, index) {
    const presigned = await this._getPresignedPost(file.name)

    const formData = new FormData()
    Object.entries(presigned.fields).forEach(([name, value]) => {
      formData.append(name, value)
    })
    formData.append('file', file)

    await this._postToS3(presigned.url, formData, index)
    return presigned.key
  }

  async _getPresignedPost (filename) {
    const body = new FormData()
    body.append('filename', filename)
    const response = await fetch(this.presignedUrlValue, {
      method: 'POST',
      headers: { 'X-CSRFToken': this._csrfToken() },
      body
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.error || 'préparation du téléversement impossible')
    }
    return response.json()
  }

  _postToS3 (url, formData, index) {
    return new Promise((resolve, reject) => {
      const xhr = new window.XMLHttpRequest()
      xhr.open('POST', url)
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          this.progressByIndex[index] = event.loaded / event.total
          this._renderProgress()
        }
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          this.progressByIndex[index] = 1
          this._renderProgress()
          resolve()
        } else {
          reject(new Error(`S3 a renvoyé le statut ${xhr.status}`))
        }
      }
      xhr.onerror = () => reject(new Error('échec réseau'))
      xhr.send(formData)
    })
  }

  _isPdf (file) {
    return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
  }

  _csrfToken () {
    const input = this.formTarget.querySelector('[name=csrfmiddlewaretoken]')
    return input ? input.value : ''
  }

  _renderProgress () {
    const done = this.progressByIndex.reduce((sum, p) => sum + p, 0)
    const percent = Math.round((done / this.files.length) * 100)
    this.progressTarget.textContent = `Envoi en cours… ${percent}%`
  }

  _refresh () {
    if (this.hasFileListTarget) {
      this.fileListTarget.innerHTML = this.files
        .map((file, index) => {
          const safeName = this._escapeHtml(file.name)
          return `<li class="fr-mb-1w">${safeName}` +
            ' <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-delete-line"' +
            ` data-action="document-import#removeFile" data-document-import-index-param="${index}">` +
            `Retirer ${safeName}</button></li>`
        })
        .join('')
    }
    if (this.hasSubmitTarget) {
      this.submitTarget.disabled = this.files.length === 0
    }
  }

  _escapeHtml (text) {
    const div = window.document.createElement('div')
    div.textContent = text == null ? '' : String(text)
    return div.innerHTML
  }

  _setError (message) {
    if (this.hasProgressTarget) {
      this.progressTarget.innerHTML = message
      this.progressTarget.hidden = message === ''
    }
  }
}
