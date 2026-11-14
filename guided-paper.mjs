// A local practice broker. No network calls, broker credentials or live order path.
export const EXAMPLE = Object.freeze({
  id: 'example-etf-breakout-v1',
  symbol: 'Example ETF',
  limitCents: 5000,
  invalidationCents: 4800,
  maxShares: 10,
});
const CASH_CENTS = 100_000;
const TTL_MS = 60_000;

export function createTicket(shares, now, id) {
  if (!Number.isSafeInteger(shares) || shares < 1 || shares > EXAMPLE.maxShares) {
    throw new Error('Choose 1–10 whole shares.');
  }
  if (!Number.isSafeInteger(now) || typeof id !== 'string' || !id) throw new Error('Invalid review.');
  return Object.freeze({
    id, setupId: EXAMPLE.id, mode: 'practice', side: 'buy', type: 'limit',
    shares, limitCents: EXAMPLE.limitCents, reviewedAt: now, expiresAt: now + TTL_MS,
  });
}

export function createPracticeBroker({ load, save }, clock = Date.now) {
  function read() {
    const state = load();
    return state === null ? { orders: [] } : state;
  }
  function find(state, id) {
    const order = state.orders.find(row => row.ticket.id === id);
    if (!order) throw new Error('Practice order not found.');
    return order;
  }
  function available(state) {
    return CASH_CENTS - state.orders.reduce((sum, { ticket, filled, state }) => {
      const committed = state === 'canceled' ? filled : ticket.shares;
      return sum + committed * ticket.limitCents;
    }, 0);
  }
  function update(id, transition) {
    const snapshot = read();
    const result = find(snapshot, id);
    transition(result);
    save(snapshot);
    return result;
  }
  return {
    snapshot() {
      const state = read();
      return { ...state, availableCents: available(state) };
    },
    submit(ticket) {
      const state = read();
      const prior = state.orders.find(row => row.ticket.id === ticket.id);
      const canonical = createTicket(ticket.shares, ticket.reviewedAt, ticket.id);
      const matches = (a, b) => Object.keys(canonical).every(key => a[key] === b[key]);
      if (!matches(ticket, canonical)) throw new Error('The ticket changed. Review it again.');
      if (prior) {
        if (!matches(ticket, prior.ticket)) throw new Error('This review ID was used for a different order.');
        return prior;
      }
      const now = clock();
      if (now < ticket.reviewedAt || now >= ticket.expiresAt) throw new Error('Review expired. Preview the order again.');
      if (available(state) < ticket.limitCents * ticket.shares) throw new Error('Not enough practice buying power.');
      const order = { ticket: canonical, state: 'open', filled: 0, updatedAt: now };
      state.orders.unshift(order);
      save(state);
      return order;
    },
    requestCancel(id) {
      return update(id, order => {
        if (order.state === 'cancel_pending') return;
        if (!['open', 'partially_filled'].includes(order.state)) throw new Error('This order cannot be canceled.');
        order.state = 'cancel_pending';
        order.updatedAt = clock();
      });
    },
    advance(id) {
      return update(id, order => {
        if (order.state === 'cancel_pending') {
          order.state = 'canceled';
        } else if (order.state === 'open' || order.state === 'partially_filled') {
          order.filled = order.state === 'open' ? Math.ceil(order.ticket.shares / 2) : order.ticket.shares;
          order.state = order.filled === order.ticket.shares ? 'filled' : 'partially_filled';
        } else {
          throw new Error('This order is already complete.');
        }
        order.updatedAt = clock();
      });
    },
  };
}
