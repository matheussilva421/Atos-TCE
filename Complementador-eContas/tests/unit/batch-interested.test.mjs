import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { selectSingleInterested } from '../../src/form/interested-selector.mjs';

const URL_COMPLEMENT = 'https://processos.tce.rn.gov.br/#/dashboard/complementar-ato/601';

function dom(body) {
  return new JSDOM('<html><body>' + body + '</body></html>', { url: URL_COMPLEMENT });
}

function card(name, selected = false) {
  return '<button class="cartao-item' + (selected ? ' selecionada' : '') + '">'
    + '<span>' + name + '</span><small>111.111.111-11</small></button>';
}

test('interested_count_not_exactly_one_never_saves', async () => {
  const two = dom('<tce-container>' + card('Pessoa A') + card('Pessoa B') + '</tce-container>');
  const result = await selectSingleInterested(two.window.document, '601');
  assert.equal(result.ok, false);
  assert.equal(result.code, 'MULTIPLE_INTERESTED');

  const none = dom('<tce-container><div class="vazio"></div></tce-container>');
  const empty = await selectSingleInterested(none.window.document, '601');
  assert.equal(empty.ok, false);
  assert.equal(empty.code, 'NO_INTERESTED');
});

test('one_unselected_card_auto_selected', async () => {
  const page = dom('<tce-container>' + card('Pessoa A') + '</tce-container>');
  const document = page.window.document;
  const button = document.querySelector('button.cartao-item');
  button.addEventListener('click', () => button.classList.add('selecionada'));
  const result = await selectSingleInterested(document, '601');
  assert.equal(result.ok, true);
  assert.equal(result.interestedCount, 1);
  assert.equal(document.querySelectorAll('button.cartao-item.selecionada').length, 1);
  assert.equal(typeof result.interestedKey, 'string');
});

test('one_already_selected_no_reclick', async () => {
  const page = dom('<tce-container>' + card('Pessoa A', true) + '</tce-container>');
  const document = page.window.document;
  let clicks = 0;
  document.querySelector('button.cartao-item').addEventListener('click', () => { clicks += 1; });
  const result = await selectSingleInterested(document, '601');
  assert.equal(result.ok, true);
  assert.equal(clicks, 0);
});

test('wrong_process_blocks_selection', async () => {
  const page = dom('<tce-container>' + card('Pessoa A') + '</tce-container>');
  const result = await selectSingleInterested(page.window.document, '602');
  assert.equal(result.ok, false);
  assert.equal(result.code, 'WRONG_PROCESS');
});

test('card_not_loaded_is_not_zero_count', async () => {
  const page = dom('<div id="app"></div>');
  const result = await selectSingleInterested(page.window.document, '601', { timeoutMs: 20, pollMs: 5 });
  assert.equal(result.ok, false);
  assert.equal(result.code, 'CARDS_NOT_LOADED');
});
