// Sticky table headers: keep the <thead> of `.gsl-projet-table` glued to the
// viewport top while the user scrolls the page vertically. The DSFR
// `fr-table__container` is itself a horizontal scroll context (overflow-x:
// auto), which would normally bound `position: sticky`. Instead, we translate
// the real <thead> with a rAF-coalesced window scroll listener so it tracks
// the viewport without leaving its own overflow box.

const bindings = new WeakMap()

function initStickyTables (root) {
  const scope = root || document
  const tables = scope.querySelectorAll
    ? scope.querySelectorAll('.gsl-projet-table')
    : []
  tables.forEach((el) => {
    const realTable = el.querySelector('.fr-table__content > table')
    const realThead = realTable && realTable.querySelector('thead')
    if (!realTable || !realThead) return

    const previous = bindings.get(el)
    if (previous) previous.disconnect()

    let raf = 0
    const update = () => {
      const rect = realTable.getBoundingClientRect()
      const theadHeight = realThead.getBoundingClientRect().height
      const offset = -rect.top
      const maxOffset = Math.max(0, rect.height - theadHeight)
      const clamped = Math.max(0, Math.min(offset, maxOffset))
      realThead.style.transform = `translateY(${clamped}px)`
    }

    const schedule = () => {
      if (raf) return
      raf = window.requestAnimationFrame(() => {
        raf = 0
        update()
      })
    }

    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule, { passive: true })
    const ro = new window.ResizeObserver(schedule)
    ro.observe(realTable)

    const disconnect = () => {
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      ro.disconnect()
      if (raf) {
        window.cancelAnimationFrame(raf)
        raf = 0
      }
      realThead.style.transform = ''
    }

    bindings.set(el, { disconnect })
    update()
  })
}

document.body.addEventListener('htmx:afterSwap', (e) => {
  const scope = e.target.closest('.gsl-projet-table') || e.target
  initStickyTables(scope)
})

initStickyTables()
