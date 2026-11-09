import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { attachFloatingPanel } from '../../src/shared/floating-panel.mjs';

function setup() {
  const dom = new JSDOM('<div id="host"></div>');
  const host = dom.window.document.querySelector('#host');
  const shadow = host.attachShadow({ mode: 'open' });
  shadow.innerHTML = '<div class="wrap"><div class="title">Complementador e-Contas</div><input value="7"><button data-action="start">Rodar</button><div class="status">Executando</div></div>';
  const panel = shadow.querySelector('.wrap');
  panel.getBoundingClientRect = () => ({ left: 600, top: 400, width: 310, height: 220 });
  attachFloatingPanel(host);
  const fire = (target, type, props = {}) => {
    const event = new dom.window.Event(type, { bubbles: true, cancelable: true });
    Object.assign(event, { pointerId: 1, button: 0, clientX: 620, clientY: 410 }, props);
    target.dispatchEvent(event);
  };
  return { dom, shadow, panel, fire, title: shadow.querySelector('.title') };
}

test('hide and reopen preserve controls, input and running status', () => {
  const { shadow, panel } = setup();
  const start = shadow.querySelector('[data-action="start"]');
  let starts = 0;
  start.addEventListener('click', () => starts++);
  shadow.querySelector('[data-action="hide-panel"]').click();
  assert.equal(panel.hidden, true);
  const reopen = shadow.querySelector('[data-action="show-panel"]');
  assert.equal(reopen.hidden, false);
  reopen.click();
  assert.equal(panel.hidden, false);
  assert.equal(reopen.hidden, true);
  assert.equal(shadow.querySelector('input').value, '7');
  assert.equal(shadow.querySelector('.status').textContent, 'Executando');
  assert.equal(shadow.querySelector('[data-action="start"]'), start);
  assert.equal(starts, 0);
});

test('title drags panel and clamps it inside viewport; cancellation stops movement', () => {
  const { dom, panel, title, fire } = setup();
  fire(title, 'pointerdown');
  fire(dom.window.document, 'pointermove', { clientX: 320, clientY: 210 });
  assert.equal(panel.style.left, '300px');
  assert.equal(panel.style.top, '200px');
  fire(dom.window.document, 'pointermove', { clientX: -2000, clientY: 2000 });
  assert.equal(panel.style.left, '8px');
  assert.equal(panel.style.top, '540px');
  fire(dom.window.document, 'pointercancel');
  fire(dom.window.document, 'pointermove', { clientX: 800 });
  assert.equal(panel.style.left, '8px');
});

test('non-primary pointers and form controls do not drag the panel', () => {
  const { dom, shadow, panel, title, fire } = setup();
  fire(title, 'pointerdown', { button: 2 });
  fire(dom.window.document, 'pointermove');
  assert.equal(panel.style.left, '');
  fire(shadow.querySelector('input'), 'pointerdown');
  fire(dom.window.document, 'pointermove');
  assert.equal(panel.style.left, '');
});

test('keyboard movement and resize keep panel accessible', () => {
  const { dom, panel, title } = setup();
  title.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
  assert.equal(panel.style.left, '580px');
  Object.defineProperty(dom.window, 'innerWidth', { value: 400 });
  Object.defineProperty(dom.window, 'innerHeight', { value: 300 });
  dom.window.dispatchEvent(new dom.window.Event('resize'));
  assert.equal(panel.style.left, '82px');
  assert.equal(panel.style.top, '72px');
});
