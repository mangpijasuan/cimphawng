// Private operator pilot. This adapter has no live broker URL or order retry path.
const BASE = 'https://paper-api.alpaca.markets/v2';
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const SYMBOLS = ['SPY', 'QQQ'];
const MAX_CENTS = 100_000;
const CLOSED = new Set(['filled', 'canceled', 'expired', 'rejected']);
const ORDER_STATES = new Set([...CLOSED, 'new', 'accepted', 'pending_new', 'partially_filled', 'pending_cancel', 'done_for_day', 'accepted_for_bidding', 'held', 'suspended', 'stopped', 'calculated', 'pending_replace', 'replaced']);
const message = 'Alpaca paper status is unavailable. Try checking again.';
function fail(status, detail) { throw Object.assign(new Error(detail), {status}); }
const lookup = (db, sql, ...args) => db.prepare(sql).bind(...args).first();
const usd = cents => (cents / 100).toFixed(2);

export function paperConfig(env) {
  if (env.ALPACA_PAPER_ENABLED !== 'true') return null;
  const {ALPACA_PAPER_OWNER: owner, ALPACA_PAPER_ACCOUNT_ID: account,
    ALPACA_PAPER_KEY: key, ALPACA_PAPER_SECRET: secret} = env;
  if (!/^0x[0-9a-f]{40}$/i.test(owner || '') || !UUID.test(account || '') || !key || !secret) return null;
  return {owner: owner.toLowerCase(), account: account.toLowerCase(), key, secret};
}

export async function paperPilot({request, path, db, config, clock, fetcher, read, json}) {
  const write = request.method === 'POST';
  const route = path.slice('/api/alpaca-paper'.length);
  async function call(method, suffix, data) {
    let response;
    try {
      response = await fetcher(BASE + suffix, {
        method, redirect: 'error', signal: AbortSignal.timeout(5000),
        headers: {'APCA-API-KEY-ID': config.key, 'APCA-API-SECRET-KEY': config.secret,
          Accept: 'application/json', ...(data ? {'Content-Type': 'application/json'} : {})},
        ...(data ? {body: JSON.stringify(data)} : {}),
      });
    } catch { fail(502, message); }
    return response;
  }
  async function parse(response) {
    if (!response.ok) fail(502, message);
    try { return await response.json(); } catch { fail(502, message); }
  }
  async function verifyAccount(forOrder = false) {
    const account = await parse(await call('GET', '/account'));
    if (account?.id?.toLowerCase?.() !== config.account) fail(503, 'Configured Alpaca paper account does not match.');
    if (forOrder && (account.status !== 'ACTIVE' || account.trading_blocked !== false || account.account_blocked !== false)) {
      fail(409, 'The paper account cannot accept orders.');
    }
  }
  function present(row) {
    return {id: row.id, symbol: row.symbol, quantity: 1, limit_price: usd(row.limit_cents),
      side: 'buy', time_in_force: 'day', expires_at: row.expires_at, stage: row.stage,
      status: row.stage === 'closed' ? row.final_status : row.stage === 'sending' ? 'checking' : 'review',
      filled_qty: row.stage === 'closed' ? row.final_filled : null};
  }
  async function normalize(row, raw) {
    if (!raw || raw.client_order_id !== row.id || !UUID.test(raw.id || '') ||
        raw.symbol !== row.symbol || raw.side !== 'buy' || raw.type !== 'limit' ||
        raw.time_in_force !== 'day' || raw.extended_hours !== false || Number(raw.qty) !== 1 ||
        Number(raw.limit_price) !== Number(usd(row.limit_cents)) || !ORDER_STATES.has(raw.status) ||
        typeof raw.filled_qty !== 'string' || !/^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(raw.filled_qty) ||
        (raw.status === 'filled' && Number(raw.filled_qty) !== 1)) fail(502, message);
    const status = raw.status;
    if (CLOSED.has(status)) {
      await db.prepare("UPDATE alpaca_pilot_orders SET stage='closed',final_status=?,final_filled=? WHERE id=? AND broker_account=? AND stage='sending'")
        .bind(status, raw.filled_qty, row.id, config.account).run();
    }
    return {...present(row), stage: CLOSED.has(status) ? 'closed' : 'sending',
      status, filled_qty: raw.filled_qty};
  }
  async function reconcile(row) {
    return call('GET', '/orders:by_client_order_id?client_order_id=' + row.id);
  }
  const uncertain = row => json({...present({...row, stage:'sending'}), status: 'checking'}, 202);

  if (!write && route === '') {
    const {results} = await db.prepare("SELECT * FROM alpaca_pilot_orders WHERE broker_account=? AND stage!='review' ORDER BY (stage='sending') DESC,created_at DESC LIMIT 20")
      .bind(config.account).all();
    return json({enabled: true, mode:'alpaca-paper', symbols: SYMBOLS, max_limit: usd(MAX_CENTS), orders: results.map(present)});
  }
  if (write && route === '/review') {
    const input = await read(request);
    if (Object.keys(input).length !== 2 || !SYMBOLS.includes(input.symbol) ||
        typeof input.limit_price !== 'string' || !/^(?:0|[1-9]\d{0,3})(?:\.\d{1,2})?$/.test(input.limit_price)) {
      fail(400, 'Choose an allowed ETF and enter a price in dollars and cents.');
    }
    const [whole, frac = ''] = input.limit_price.split('.');
    const cents = Number(whole) * 100 + Number(frac.padEnd(2, '0'));
    if (cents < 100 || cents > MAX_CENTS) fail(400, 'Choose a limit from $1 to $1,000.');
    const time = clock(), id = crypto.randomUUID(), expiry = time + 60_000;
    await db.batch([
      db.prepare("DELETE FROM alpaca_pilot_orders WHERE broker_account=? AND stage='review' AND expires_at<=?").bind(config.account, time),
      db.prepare("INSERT INTO alpaca_pilot_orders(id,broker_account,symbol,limit_cents,created_at,expires_at,stage) VALUES(?,?,?,?,?,?,'review')")
        .bind(id, config.account, input.symbol, cents, time, expiry),
    ]);
    return json(present({id, symbol: input.symbol, limit_cents: cents, expires_at: expiry, stage:'review'}), 201);
  }

  const match = route.match(/^\/orders\/([\da-f-]+)(?:\/(submit|cancel))?$/);
  if (!match || !UUID.test(match[1]) || write !== Boolean(match[2])) fail(404, 'Unknown paper order route.');
  const [, id, action] = match;
  const get = () => lookup(db, 'SELECT * FROM alpaca_pilot_orders WHERE id=? AND broker_account=?', id, config.account);
  let row = await get();
  if (!row) fail(404, 'Paper order not found.');
  if (write && Object.keys(await read(request)).length) fail(400, 'Only the reviewed ticket can be submitted.');
  if (row.stage === 'closed') return json(present(row));
  if (row.stage === 'review') {
    if (action !== 'submit') fail(409, 'This order has not been sent.');
    if (row.expires_at <= clock()) fail(409, 'Review expired. Preview the order again.');
    await verifyAccount(true);
    // Commit the dispatch claim before contacting Alpaca. Unknown outcomes only reconcile.
    const claimed = await lookup(db, `UPDATE alpaca_pilot_orders SET stage='sending'
      WHERE id=? AND broker_account=? AND stage='review' AND expires_at>?
      AND NOT EXISTS (SELECT 1 FROM alpaca_pilot_orders WHERE broker_account=? AND stage='sending')
      RETURNING id`, id, config.account, clock(), config.account);
    row = await get();
    if (!claimed) {
      if (!row || row.stage === 'review') fail(409, 'Review expired or another paper order still needs to be resolved.');
      if (row.stage === 'closed') return json(present(row));
      return uncertain(row);
    }
    try {
      const response = await call('POST', '/orders', {client_order_id:id, symbol:row.symbol,
        qty:'1', side:'buy', type:'limit', time_in_force:'day', limit_price:usd(row.limit_cents), extended_hours:false});
      return json(await normalize(row, await parse(response)));
    } catch { return uncertain(row); }
  }

  await verifyAccount();
  const response = await reconcile(row);
  if (response.status === 404) return uncertain(row);
  const raw = await parse(response);
  const order = await normalize(row, raw);
  if (action !== 'cancel' || order.stage === 'closed' || order.status === 'pending_cancel') return json(order);
  const result = await call('DELETE', '/orders/' + raw.id);
  if (result.status !== 204 && result.status !== 422 && result.status !== 404) fail(502, message);
  const latest = await reconcile(row);
  if (latest.status === 404) return uncertain(row);
  return json({...await normalize(row, await parse(latest)), cancel_acknowledged: result.status === 204});
}
