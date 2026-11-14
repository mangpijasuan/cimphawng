// Read-only preflight for the dedicated paper account; never calls an order route.
import {paperConfig, PAPER_API_BASE} from '../lib/alpaca-paper.mjs';

const config = paperConfig(process.env);
if (!config) {
  console.error('Paper preflight blocked: set ALPACA_PAPER_ENABLED=true and supply the owner wallet, account ID, and paper credentials.');
  process.exitCode = 2;
} else {
  try {
    const response = await fetch(PAPER_API_BASE + '/account', {
      method:'GET', redirect:'error', signal:AbortSignal.timeout(5000),
      headers:{'APCA-API-KEY-ID':config.key, 'APCA-API-SECRET-KEY':config.secret, Accept:'application/json'},
    });
    if (!response.ok) throw new Error('Alpaca Paper account lookup returned HTTP ' + response.status + '.');
    const account = await response.json().catch(() => null);
    if (typeof account?.id !== 'string' || account.id.toLowerCase() !== config.account) {
      throw new Error('The credentials do not match the configured paper account.');
    }
    if (account.status !== 'ACTIVE' || account.account_blocked !== false || account.trading_blocked !== false) {
      throw new Error('The paper account is not eligible to accept orders.');
    }
    console.log('Alpaca Paper preflight passed: configured account matches and is eligible. No order was sent.');
  } catch (error) {
    // Only report our fixed validation messages; never print a response body or credentials.
    const safe = /^(?:Alpaca Paper account lookup returned HTTP [1-5]\d\d\.|The credentials do not match the configured paper account\.|The paper account is not eligible to accept orders\.)$/;
    const detail = safe.test(error?.message) ? error.message : 'Could not reach or read the Alpaca Paper account.';
    console.error('Paper preflight failed: ' + detail);
    process.exitCode = 1;
  }
}
