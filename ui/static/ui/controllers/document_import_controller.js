import { Controller } from 'stimulus'

// Step 1 of the signed-document re-import wizard. Validates the dropped PDFs
// (type + cumulative size) and uploads each one directly to S3 via a presigned
// POST (bypassing Django's request-body limit) as soon as it is selected. Once
// every file has finished uploading, the "Continuer" button is enabled; clicking
// it writes the resulting S3 keys into a hidden input and submits the form that
// starts the async import job (a single, immediate, user-initiated navigation to
// step 2).
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
    'error',
    'submit',
    'keysInput',
    'removeQr',
    'removeQrInput',
    'form'
  ]

  connect () {
    // Each entry tracks one selected file through its upload lifecycle:
    // { file, key, status, progress, xhr }, status ∈
    // 'pending' | 'uploading' | 'done' | 'error'.
    this.entries = []
    this.uploadQueue = []
    this.activeUploads = 0
    this._refresh()
    this._updateSubmitState()

    this.dialog = this.element.closest('.fr-modal')

    // This controller lives on the deposit (step 1) and summary (step 3) steps,
    // both of which offer a "Fermer" affordance, so backdrop-click closing is
    // allowed here. The processing step (step 2) has no controller: it leaves
    // the attribute set to "false" by `goToProcessing` so it cannot be dismissed.
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
    let total = this.entries.reduce((sum, e) => sum + e.file.size, 0)
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
      const entry = { file, key: null, status: 'pending', progress: 0, xhr: null }
      this.entries.push(entry)
      this.uploadQueue.push(entry)
    }
    this._setError(errors.join('<br>'))
    this._refresh()
    this._renderProgress()
    this._updateSubmitState()
    this._pumpUploads()
  }

  _isDuplicate (file) {
    return this.entries.some(
      (e) => e.file.name === file.name && e.file.size === file.size
    )
  }

  removeFile (event) {
    const index = parseInt(event.params.index, 10)
    const entry = this.entries[index]
    if (!entry) return
    this.entries.splice(index, 1)
    const queueIndex = this.uploadQueue.indexOf(entry)
    if (queueIndex !== -1) {
      this.uploadQueue.splice(queueIndex, 1)
    }
    // Cancel an in-flight upload: the `.catch` in `_pumpUploads` guards on
    // `this.entries.includes(entry)`, so the abort won't surface an error.
    if (entry.status === 'uploading' && entry.xhr) {
      entry.xhr.abort()
    }
    this._refresh()
    this._renderProgress()
    this._updateSubmitState()
    this._pumpUploads()
  }

  goToProcessing (event) {
    event.preventDefault()
    if (this.entries.length === 0 || !this.entries.every((e) => e.status === 'done')) return
    this.keysInputTarget.value = JSON.stringify(this.entries.map((e) => e.key))
    this.removeQrInputTarget.value = this.removeQrTarget.checked ? 'true' : 'false'
    // Entering the processing step (no "Fermer" affordance): lock the backdrop
    // so the modal cannot be dismissed mid-import. The processing partial has
    // no controller, so this attribute on the dialog persists across the swap.
    this._setBackdropClose(false)
    // htmx is loaded as a self-initializing ES module and isn't exposed as a
    // global, so we dispatch a native submit event (which htmx listens for on
    // the hx-post form) rather than calling htmx.trigger directly.
    this.formTarget.requestSubmit()
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

  // Concurrency-limited streaming pump: feeds queued entries to S3 while
  // respecting `concurrencyValue`. Can be called repeatedly as new files arrive
  // or as in-flight uploads settle.
  _pumpUploads () {
    const limit = Math.max(1, this.concurrencyValue)
    while (this.activeUploads < limit && this.uploadQueue.length > 0) {
      const entry = this.uploadQueue.shift()
      if (!this.entries.includes(entry)) continue // removed before it started
      this.activeUploads++
      entry.status = 'uploading'
      this._refresh()
      this._updateSubmitState()
      this._renderProgress()
      this._uploadEntry(entry)
        .then(() => { entry.status = 'done' })
        .catch((error) => {
          if (!this.entries.includes(entry)) return // removed/aborted mid-flight
          entry.status = 'error'
          this._setError(`Une erreur est survenue pendant l'envoi de «&nbsp;${this._escapeHtml(entry.file.name)}&nbsp;» : ${this._escapeHtml(error.message)}`)
        })
        .finally(() => {
          this.activeUploads--
          this._refresh()
          this._updateSubmitState()
          this._renderProgress()
          this._pumpUploads()
        })
    }
  }

  async _uploadEntry (entry) {
    const presigned = await this._getPresignedPost(entry.file.name)

    const formData = new FormData()
    Object.entries(presigned.fields).forEach(([name, value]) => {
      formData.append(name, value)
    })
    formData.append('file', entry.file)

    await this._postToS3(presigned.url, formData, entry)
    entry.key = presigned.key
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

  _postToS3 (url, formData, entry) {
    return new Promise((resolve, reject) => {
      const xhr = new window.XMLHttpRequest()
      entry.xhr = xhr
      xhr.open('POST', url)
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          entry.progress = event.loaded / event.total
          this._renderFileProgress(entry)
          this._renderProgress()
        }
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          entry.progress = 1
          this._renderProgress()
          resolve()
        } else {
          reject(new Error(`S3 a renvoyé le statut ${xhr.status}`))
        }
      }
      xhr.onerror = () => reject(new Error('échec réseau'))
      xhr.onabort = () => reject(new Error('envoi annulé'))
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

  _updateSubmitState () {
    if (!this.hasSubmitTarget) return
    this.submitTarget.disabled =
      this.entries.length === 0 || !this.entries.every((e) => e.status === 'done')
  }

  _renderProgress () {
    if (!this.hasProgressTarget) return
    if (this.entries.length === 0) {
      this.progressTarget.textContent = ''
      this.progressTarget.hidden = true
      return
    }
    this.progressTarget.hidden = false
    if (this.entries.every((e) => e.status === 'done')) {
      this.progressTarget.textContent = 'Documents téléversés.'
      return
    }
    const done = this.entries.reduce(
      (sum, e) => sum + (e.status === 'done' ? 1 : e.progress),
      0
    )
    const percent = Math.round((done / this.entries.length) * 100)
    this.progressTarget.textContent = `Envoi en cours… ${percent}%`
  }

  _refresh () {
    if (this.hasFileListTarget) {
      this.fileListTarget.innerHTML = this.entries
        .map((entry, index) => {
          const safeName = this._escapeHtml(entry.file.name)
          return `<li class="fr-mb-1w">${safeName} ` +
            `<span class="fr-text--sm" data-file-hint="${index}">${this._statusHint(entry)}</span>` +
            ' <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-delete-line"' +
            ` data-action="document-import#removeFile" data-document-import-index-param="${index}">` +
            `Retirer ${safeName}</button></li>`
        })
        .join('')
    }
  }

  // Updates a single file's hint span in place (avoiding a full `_refresh()`,
  // which would rebuild the whole `<ul>` on every progress tick — flickering
  // and dropping focus from the "Retirer" buttons).
  _renderFileProgress (entry) {
    if (!this.hasFileListTarget) return
    const index = this.entries.indexOf(entry)
    if (index === -1) return
    const span = this.fileListTarget.querySelector(`[data-file-hint="${index}"]`)
    if (span) span.innerHTML = this._statusHint(entry)
  }

  _statusHint (entry) {
    switch (entry.status) {
      case 'uploading':
        return `envoi en cours… ${Math.round(entry.progress * 100)}%`
      case 'done':
        return '<span class="fr-icon-check-line" aria-label="téléversé" title="téléversé"></span>'
      case 'error':
        return '<span class="fr-icon-error-line" aria-label="échec de l\'envoi" title="échec de l\'envoi"></span>'
      default:
        return ''
    }
  }

  _escapeHtml (text) {
    const div = window.document.createElement('div')
    div.textContent = text == null ? '' : String(text)
    return div.innerHTML
  }

  _setError (message) {
    if (this.hasErrorTarget) {
      this.errorTarget.innerHTML = message
      this.errorTarget.hidden = message === ''
      // The DSFR `fr-error-text` rule is `display: flex`, which overrides the UA
      // `[hidden] { display: none }`, so it must only be present while an actual
      // error message is shown — otherwise its `::before` paints a stray icon.
      this.errorTarget.classList.toggle('fr-error-text', message !== '')
    }
  }
}
