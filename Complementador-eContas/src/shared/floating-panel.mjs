// Presentation only: hiding or moving a panel never changes automation state.
export function attachFloatingPanel(host) {
  const shadow = host.shadowRoot;
  const panel = shadow.querySelector('.wrap');
  const title = shadow.querySelector('.title');
  const doc = host.ownerDocument;
  const view = doc.defaultView;
  const style = doc.createElement('style');
  style.textContent = `
    .wrap{box-sizing:border-box;max-width:calc(100vw - 16px);max-height:calc(100vh - 16px);overflow:auto}
    .wrap[hidden],.panel-launcher[hidden]{display:none!important}
    .title{padding-right:78px;min-height:26px;cursor:grab;touch-action:none;user-select:none}
    .title:focus-visible{outline:2px solid #0b6e4f;outline-offset:2px}
    .title[data-dragging]{cursor:grabbing}
    button.panel-hide{position:absolute;top:8px;right:8px;width:auto;min-height:28px;padding:5px 7px;font-size:11px;background:#fff;color:#334e68;border:1px solid #bcccdc}
    button.panel-launcher{position:fixed;right:16px;bottom:16px;z-index:2147483647;width:auto;max-width:calc(100vw - 16px);box-sizing:border-box;max-height:calc(100vh - 16px);overflow:auto;box-shadow:0 4px 16px #0003}
  `;
  shadow.appendChild(style);
  const hide = doc.createElement('button');
  hide.type = 'button';
  hide.className = 'panel-hide';
  hide.dataset.action = 'hide-panel';
  hide.textContent = 'Esconder';
  hide.setAttribute('aria-label', 'Esconder Complementador e-Contas');
  panel.appendChild(hide);
  const show = doc.createElement('button');
  show.type = 'button';
  show.className = 'panel-launcher';
  show.dataset.action = 'show-panel';
  show.textContent = 'Mostrar Complementador e-Contas';
  show.hidden = true;
  show.setAttribute('aria-expanded', 'false');
  shadow.appendChild(show);

  let position = null;
  let drag = null;
  function move(left, top) {
    const rect = panel.getBoundingClientRect();
    position = {
      left: Math.max(8, Math.min(left, view.innerWidth - rect.width - 8)),
      top: Math.max(8, Math.min(top, view.innerHeight - rect.height - 8)),
    };
    Object.assign(panel.style, { left: position.left + 'px', top: position.top + 'px', right: 'auto', bottom: 'auto' });
  }
  function constrain() {
    if (position && !panel.hidden && host.isConnected) move(position.left, position.top);
  }
  hide.addEventListener('click', () => {
    endDrag();
    panel.hidden = true;
    show.hidden = false;
    show.focus();
  });
  show.addEventListener('click', () => {
    panel.hidden = false;
    show.hidden = true;
    constrain();
    title.focus();
  });

  title.tabIndex = 0;
  title.title = 'Arraste para mover ou use as setas do teclado';
  title.setAttribute('aria-label', title.textContent + '. Arraste para mover ou use as setas do teclado.');
  title.addEventListener('keydown', (event) => {
    const offsets = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
    const offset = offsets[event.key];
    if (!offset) return;
    event.preventDefault();
    const rect = position || panel.getBoundingClientRect();
    move(rect.left + offset[0], rect.top + offset[1]);
  });
  function onMove(event) {
    if (!drag || event.pointerId !== drag.id) return;
    move(drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y);
  }
  function endDrag(event) {
    if (!drag || (event && event.pointerId !== drag.id)) return;
    drag = null;
    title.removeAttribute('data-dragging');
    doc.removeEventListener('pointermove', onMove);
    doc.removeEventListener('pointerup', endDrag);
    doc.removeEventListener('pointercancel', endDrag);
  }
  title.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || event.isPrimary === false || drag) return;
    event.preventDefault();
    const rect = panel.getBoundingClientRect();
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top };
    title.setAttribute('data-dragging', '');
    title.setPointerCapture?.(event.pointerId);
    doc.addEventListener('pointermove', onMove);
    doc.addEventListener('pointerup', endDrag);
    doc.addEventListener('pointercancel', endDrag);
  });
  title.addEventListener('lostpointercapture', endDrag);
  view.addEventListener('resize', constrain);
  // Diagnostics and batch summaries can change the panel size after a drag.
  if (view.ResizeObserver) new view.ResizeObserver(constrain).observe(panel);
}
