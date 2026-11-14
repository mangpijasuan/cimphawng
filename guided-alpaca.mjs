const $ = id => document.getElementById(id);
const base = '/api/alpaca-paper';
const states = {checking:'Checking with Alpaca', pending_cancel:'Cancellation pending',
  partially_filled:'Partly filled', filled:'Filled', canceled:'Canceled', rejected:'Rejected',
  expired:'Expired', new:'Waiting for fill', accepted:'Accepted', pending_new:'Awaiting acceptance'};
let reviewed, busy = false;
const orders = new Map();
function node(parent, tag, text) {
  const el = document.createElement(tag);
  el.textContent = text;
  parent.append(el);
  return el;
}
function feedback(text) { $('pilot-feedback').textContent = text; }
function clearReview() { reviewed = undefined; $('pilot-review').hidden = true; }
async function request(route, data) {
  const response = await fetch(base + route, data === undefined
    ? {cache: 'no-store'}
    : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || 'Alpaca paper is unavailable.');
  }
  return response.json();
}
function button(parent, label, action) {
  const el = node(parent, 'button', label);
  el.type = 'button';
  el.addEventListener('click', () => run(action));
}
function remember(order) {
  // A temporary reconciliation failure must not erase an already confirmed terminal state.
  if (orders.get(order.id)?.stage !== 'closed') orders.set(order.id, order);
}
function render() {
  const list = $('pilot-orders');
  list.replaceChildren();
  if (!orders.size) node(list, 'p', 'No Alpaca paper orders yet.');
  for (const order of [...orders.values()].reverse()) {
    const row = node(list, 'article', '');
    row.className = 'order-row';
    node(row, 'strong', order.symbol + ' · ' + (states[order.status] || order.status.replaceAll('_', ' ')));
    node(row, 'p', 'Buy 1 share · Limit $' + order.limit_price +
      (order.filled_qty == null ? '' : ' · Filled ' + order.filled_qty + ' of 1 share'));
    if (order.stage === 'sending') {
      const path = '/orders/' + order.id;
      button(row, 'Check status', async () => {
        const current = await request(path);
        remember(current);
        feedback(current.status === 'checking' ? 'Alpaca has not confirmed this order. Check again before placing another.' : 'Paper order status updated.');
      });
      if (order.status !== 'pending_cancel') button(row, 'Request cancellation', async () => {
        const current = await request(path + '/cancel', {});
        remember(current);
        feedback(current.stage === 'closed' ? 'Alpaca reported the final order status.' :
          current.cancel_acknowledged ? 'Cancellation requested. Check status for confirmation.' :
          'Cancellation is not confirmed. Check the order status.');
      });
    }
  }
}
async function run(task) {
  if (busy) return;
  busy = true;
  try { await task(); render(); }
  catch (error) { feedback(error?.message || 'Alpaca paper is unavailable.'); }
  finally { busy = false; }
}
async function status() {
  const result = await request('');
  if (result.mode !== 'alpaca-paper') return;
  const select = $('pilot-symbol');
  if (select.options.length === 0) for (const symbol of result.symbols) node(select, 'option', symbol).value = symbol;
  const prior = new Map(orders);
  orders.clear();
  for (const order of result.orders.reverse()) {
    const previous = prior.get(order.id);
    remember(order.status === 'checking' && previous?.stage === 'sending' ? previous : order);
  }
  render();
  $('alpaca-pilot').hidden = false;
}
$('pilot-form').addEventListener('input', () => {
  if (reviewed) { clearReview(); feedback('Order changed. Review it again.'); }
});
$('pilot-form').addEventListener('submit', event => {
  event.preventDefault();
  run(async () => {
    clearReview();
    const fields = () => ({symbol:$('pilot-symbol').value, limit_price:$('pilot-price').value.trim()});
    const input = fields();
    const ticket = await request('/review', input);
    if (JSON.stringify(input) !== JSON.stringify(fields())) return feedback('Order changed. Review it again.');
    reviewed = ticket;
    $('pilot-ticket').textContent = 'Alpaca Paper · Buy 1 share of ' + ticket.symbol +
      ' · Day limit $' + ticket.limit_price + ' · Maximum share cost $' + ticket.limit_price + ' before fees.';
    $('pilot-review').hidden = false;
    feedback('This review is valid for 60 seconds.');
    $('pilot-submit').focus();
  });
});
$('pilot-submit').addEventListener('click', () => run(async () => {
  if (!reviewed) return;
  const ticket = reviewed;
  try {
    const order = await request('/orders/' + ticket.id + '/submit', {});
    remember(order);
    clearReview();
    feedback(order.status === 'checking' ? 'Submission outcome is unknown. Check status; do not place a new order.' :
      'Alpaca confirmed the paper order status.');
  } catch (error) {
    feedback(error.message + ' If submission was interrupted, refresh paper orders before creating a new ticket.');
  }
}));
$('pilot-refresh').addEventListener('click', () => run(async () => { await status(); feedback('Paper orders refreshed.'); }));
// A static preview, a signed-out visitor, and other wallets never see the private panel.
status().catch(() => {});
