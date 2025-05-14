export function disableAllModalButtons(modal) {
    const buttons = modal.querySelectorAll("button")
    buttons.forEach((button) => {
        button.disabled = true
    })
}
