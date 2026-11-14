import test from 'node:test';
import assert from 'node:assert/strict';
import { createPracticeBroker, createTicket } from '../../guided-paper.mjs';

function fixture() {
  let snapshot = null, now = 1000, lostResponse = false;
  const storage = {
    load: () => structuredClone(snapshot),
    save: value => {
      snapshot = structuredClone(value);
      if (lostResponse) { lostResponse = false; throw new Error('Response lost'); }
    },
  };
  return {
    broker: createPracticeBroker(storage, () => now),
    restart: () => createPracticeBroker(storage, () => now),
    expire: () => { now += 60_000; },
    loseResponse: () => { lostResponse = true; },
    ticket: (shares, id = 'test-order') => createTicket(shares, now, id),
  };
}
test('retries after a lost response and reload do not create another order', () => {
  const f = fixture(), ticket = f.ticket(2);
  f.loseResponse();
  assert.throws(() => f.broker.submit(ticket), /Response lost/);
  f.expire();
  assert.equal(f.restart().submit(ticket).state, 'open');
  assert.equal(f.broker.snapshot().orders.length, 1);
  assert.equal(f.broker.snapshot().availableCents, 90_000);
  assert.throws(() => f.broker.submit({ ...ticket, shares: 3 }), /different order/);
});
test('the broker rejects expired, altered and out-of-range tickets', () => {
  const f = fixture(), ticket = f.ticket(2);
  assert.throws(() => f.broker.submit({ ...ticket, limitCents: 3000 }), /changed/);
  assert.throws(() => f.broker.submit({ ...ticket, mode: 'live' }), /changed/);
  for (const n of [0, '2', NaN, 1.5, 11]) assert.throws(() => f.ticket(n), /whole shares/);
  f.expire();
  assert.throws(() => f.broker.submit(ticket), /expired/);
  assert.equal(f.broker.snapshot().orders.length, 0);
});
test('a partial fill is retained and buying power released only after cancellation confirms', () => {
  const f = fixture();
  f.broker.submit(f.ticket(3));
  assert.equal(f.broker.advance('test-order').state, 'partially_filled');
  assert.equal(f.broker.requestCancel('test-order').state, 'cancel_pending');
  assert.equal(f.broker.snapshot().availableCents, 85_000);
  assert.deepEqual(f.broker.advance('test-order').filled, 2);
  const snapshot = f.broker.snapshot();
  assert.equal(snapshot.orders[0].state, 'canceled');
  assert.equal(snapshot.availableCents, 90_000);
  assert.throws(() => f.broker.advance('test-order'), /complete/);
});
test('open orders reserve cash and a completed fill cannot be canceled', () => {
  const f = fixture();
  f.broker.submit(f.ticket(10, 'a'));
  f.broker.submit(f.ticket(10, 'b'));
  assert.throws(() => f.broker.submit(f.ticket(1, 'c')), /buying power/);
  f.broker.advance('a');
  assert.equal(f.broker.advance('a').state, 'filled');
  assert.throws(() => f.broker.requestCancel('a'), /cannot be canceled/);
});
