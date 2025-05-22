export function disableAllModalButtons(modal) {
    const buttons = modal.querySelectorAll("button")
    buttons.forEach((button) => {
        button.disabled = true
    })
}


export function ensureButtonsAreEnabled(modal) {
    const buttons = modal.querySelectorAll("button")
    buttons.forEach((button) => {
        button.disabled = false
    })
}