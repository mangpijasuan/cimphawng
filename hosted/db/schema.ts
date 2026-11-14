import { sql } from 'drizzle-orm';
import { sqliteTable, text, integer, primaryKey, index, uniqueIndex } from 'drizzle-orm/sqlite-core';
export const accounts = sqliteTable('accounts', { address:text('address').primaryKey(), balances:text('balances').notNull(), version:integer('version').notNull().default(0), lastOp:text('last_op').notNull().default(''), createdAt:integer('created_at').notNull(), lastSeen:integer('last_seen').notNull() });
export const nonces = sqliteTable('auth_nonces', { nonce:text('nonce').primaryKey(), address:text('address').notNull(), message:text('message').notNull(), expires:integer('expires').notNull(), used:integer('used').notNull().default(0) });
export const sessions = sqliteTable('sessions', { hash:text('hash').primaryKey(), address:text('address').notNull().references(()=>accounts.address), expires:integer('expires').notNull(), createdAt:integer('created_at') },t=>[index('session_expiry').on(t.expires)]);
export const trades = sqliteTable('paper_trades', { id:text('id').primaryKey(), address:text('address').notNull().references(()=>accounts.address), data:text('data').notNull(), createdAt:integer('created_at').notNull(), archived:integer('archived').notNull().default(0) },t=>[index('trade_account').on(t.address,t.createdAt)]);
export const prices = sqliteTable('live_prices', { asset:text('asset').primaryKey(), price:text('price').notNull(), observed:integer('observed').notNull() });
export const limits = sqliteTable('request_limits', { key:text('key').primaryKey(), count:integer('count').notNull(), expires:integer('expires').notNull() });
export const leases = sqliteTable('refresh_leases', { key:text('key').primaryKey(), expires:integer('expires').notNull() });
export const metrics = sqliteTable('api_metrics', { minute:integer('minute').notNull(), status:integer('status').notNull(), count:integer('count').notNull(), duration:integer('duration').notNull() },t=>[primaryKey({columns:[t.minute,t.status]})]);

export const operations = sqliteTable('operation_receipts', { address:text('address').notNull().references(()=>accounts.address), key:text('key').notNull(), kind:text('kind').notNull(), payloadHash:text('payload_hash').notNull(), result:text('result').notNull(), createdAt:integer('created_at').notNull() },t=>[primaryKey({columns:[t.address,t.key]})]);
export const feedStatus = sqliteTable('feed_status', {asset:text('asset').primaryKey(),successAt:integer('success_at'),errorAt:integer('error_at'),errorCode:text('error_code'),successes:integer('successes').notNull().default(0),failures:integer('failures').notNull().default(0)});

export const alpacaPilotOrders = sqliteTable('alpaca_pilot_orders', {
  id: text('id').primaryKey(),
  brokerAccount: text('broker_account').notNull(),
  symbol: text('symbol').notNull(),
  limitCents: integer('limit_cents').notNull(),
  createdAt: integer('created_at').notNull(),
  expiresAt: integer('expires_at').notNull(),
  stage: text('stage').notNull(),
  finalStatus: text('final_status'),
  finalFilled: text('final_filled'),
}, t => [
  uniqueIndex('alpaca_pilot_one_working').on(t.brokerAccount).where(sql`${t.stage} = 'sending'`),
  index('alpaca_pilot_history').on(t.brokerAccount, t.createdAt),
]);
