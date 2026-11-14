import { createPracticeBroker, createTicket, EXAMPLE } from './guided-paper.mjs';

const $ = id => document.getElementById(id);
const storageKey = 'cimphawng-guided-practice-v1';
const broker = createPracticeBroker({
  load: () => JSON.parse(localStorage.getItem(storageKey)),
  save: value => localStorage.setItem(storageKey, JSON.stringify(value)),
});
const money = cents => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
const names = { open: 'Waiting for fill', partially_filled: 'Partly filled', filled: 'Filled',
  cancel_pending: 'Cancellation pending', canceled: 'Canceled' };
let ticket;
let busy = false;

function report(message) { $('feedback').textContent = message; }
function clearReview() {
  ticket = undefined;
  $('review').hidden = true;
}
function add(parent, tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  parent.append(node);
  return node;
}
function action(parent, name, fn) {
  const b = add(parent, 'button', name);
  b.type = 'button';
  b.addEventListener('click', () => run(fn, 'Practice order updated.'));
}
function render() {
  const { orders, availableCents } = broker.snapshot();
  $('cash').textContent = money(availableCents);
  const list = $('orders');
  list.replaceChildren();
  if (!orders.length) add(list, 'p', 'No practice orders yet.');
  for (const order of orders) {
    const row = document.createElement('article');
    row.className = 'order-row';
    list.append(row);
    add(row, 'strong', EXAMPLE.symbol + ' · ' + names[order.state]);
    const remaining = order.state === 'canceled' ? 0 : order.ticket.shares - order.filled;
    add(row, 'p', `${order.filled} of ${order.ticket.shares} filled · ${remaining} remaining · Limit ${money(order.ticket.limitCents)}`);
    if (['open', 'partially_filled', 'cancel_pending'].includes(order.state)) {
      action(row, 'Advance simulator', () => broker.advance(order.ticket.id));
    }
    if (['open', 'partially_filled'].includes(order.state)) {
      action(row, 'Request cancel', () => broker.requestCancel(order.ticket.id));
    }
  }
}

async function run(fn, success) {
  if (busy) return;
  busy = true;
  try {
    if (!navigator.locks) throw new Error('Practice orders require a browser with Web Locks support.');
    await navigator.locks.request(storageKey, () => { fn(); render(); });
    report(success);
  } catch (err) {
    report(err instanceof Error ? err.message : 'Practice order could not be updated.');
  } finally {
    busy = false;
  }
}

$('ticket-form').addEventListener('submit', event => {
  event.preventDefault();
  clearReview();
  try {
    ticket = createTicket(Number($('shares').value), Date.now(), crypto.randomUUID());
    const details = $('details');
    details.replaceChildren();
    const cost = ticket.shares * ticket.limitCents;
    const loss = ticket.shares * (ticket.limitCents - EXAMPLE.invalidationCents);
    for (const [key, value] of [
      ['Order', `Buy ${ticket.shares} shares of ${EXAMPLE.symbol}`],
      ['Limit per share', money(ticket.limitCents)],
      ['Maximum purchase cost', money(cost)],
      ['Example loss if sold at $48', money(loss)],
    ]) {
      add(details, 'dt', key); add(details, 'dd', value);
    }
    $('review').hidden = false;
    report('Review is valid for 60 seconds.');
    $('submit').focus();
  } catch (err) { report(err.message); }
});
$('shares').addEventListener('input', () => {
  if (ticket) { clearReview(); report('Quantity changed. Preview the order again.'); }
});
$('submit').addEventListener('click', () => {
  const reviewed = ticket;
  if (!reviewed) return;
  run(() => {
    if (ticket !== reviewed) throw new Error('The ticket changed. Preview the order again.');
    broker.submit(reviewed);
    clearReview();
  }, 'Paper order submitted to the simulator.');
});
window.addEventListener('storage', event => {
  if (event.key === storageKey || event.key === null) {
    try { render(); } catch { report('Practice history is unavailable.'); }
  }
});
try { render(); } catch { report('Practice history is unavailable.'); }
